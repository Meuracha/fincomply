"""
FinComply API v1.0
FastAPI serving layer for RAG pipeline.
"""
import time
import uuid
import logging
import subprocess
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException, UploadFile, File, Query, Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel

from ingestion.config import config
from ingestion.embedder import BGEEmbedder
from retrieval.searcher import HybridSearcher
from retrieval.reranker import CohereReranker
from retrieval.generator import GroqGenerator
from monitoring.langfuse_client import FinComplyTracer
from serving.auth import (
    LoginRequest, TokenResponse,
    authenticate_user, create_access_token,
    get_current_user, require_admin,
    ACCESS_TOKEN_EXPIRE_HOURS,
)

logger = logging.getLogger(__name__)

# ─── Global State ─────────────────────────────────────────────
app_state = {
    "embedder": None,
    "searcher": None,
    "reranker": None,
    "generator": None,
    "tracer": None,
}


def get_pg():
    return psycopg2.connect(config.postgres_dsn)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Loading embedding model (BAAI/bge-m3)...")
    app_state["embedder"] = BGEEmbedder(model_name=config.embedding_model)

    logger.info("Initializing hybrid searcher...")
    app_state["searcher"] = HybridSearcher(
        host=config.qdrant_host,
        port=config.qdrant_port,
        collection_name=config.collection_name,
    )

    logger.info("Initializing Cohere reranker...")
    app_state["reranker"] = CohereReranker(api_key=config.cohere_api_key)

    logger.info("Initializing Groq generator...")
    app_state["generator"] = GroqGenerator(api_key=config.groq_api_key)

    logger.info("Initializing LangFuse tracer...")
    app_state["tracer"] = FinComplyTracer(
        public_key=config.langfuse_public_key,
        secret_key=config.langfuse_secret_key,
        base_url=config.langfuse_base_url,
    )

    logger.info("Startup complete")
    yield
    logger.info("Shutdown")


# ─── App ──────────────────────────────────────────────────────
app = FastAPI(
    title="FinComply API",
    version="1.0.0",
    description="Financial Compliance Intelligence Platform — RAG Pipeline",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
Instrumentator().instrument(app).expose(app)


# ─── Schemas ──────────────────────────────────────────────────
class QueryRequest(BaseModel):
    query: str
    top_k: int = 5


class QueryResponse(BaseModel):
    query_id: str
    query: str
    answer: str
    sources: List[dict]
    latency_ms: int
    model: str


class FeedbackRequest(BaseModel):
    rating: int       # 1 = thumbs up, -1 = thumbs down
    comment: Optional[str] = ""


# ─── Endpoints ────────────────────────────────────────────────
@app.get("/health")
def health():
    qdrant_ok = False
    pg_ok = False

    try:
        app_state["searcher"].client.get_collections()
        qdrant_ok = True
    except Exception:
        pass

    try:
        conn = get_pg()
        conn.close()
        pg_ok = True
    except Exception:
        pass

    status = "ok" if (qdrant_ok and pg_ok and app_state["embedder"]) else "degraded"
    return {
        "status": status,
        "qdrant": qdrant_ok,
        "postgres": pg_ok,
        "model_loaded": app_state["embedder"] is not None,
    }


@app.get("/")
def root():
    return {"message": "FinComply API v1.0 — Financial Compliance Intelligence Platform"}


# ─── Auth endpoints ────────────────────────────────────────────
@app.post("/auth/login", response_model=TokenResponse)
def login(req: LoginRequest):
    """Authenticate user and return JWT token."""
    user = authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
        )
    token = create_access_token({"sub": user["username"], "role": user["role"]})
    logger.info(f"Login: {user['username']} ({user['role']})")
    return TokenResponse(
        access_token=token,
        username=user["username"],
        role=user["role"],
        expires_in=ACCESS_TOKEN_EXPIRE_HOURS * 3600,
    )


@app.get("/auth/me")
def me(user: dict = Depends(get_current_user)):
    """Return current user info."""
    return user


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest, user: dict = Depends(get_current_user)):
    start = time.time()
    query_id = str(uuid.uuid4())

    if not app_state["embedder"]:
        raise HTTPException(status_code=503, detail="Model not loaded")

    # 1. Embed query (dense + sparse)
    dense_vec, sparse_vec = app_state["embedder"].embed_query(req.query)

    # 2. Hybrid search — top 20 candidates
    candidates = app_state["searcher"].search(
        dense_vector=dense_vec,
        sparse_vector=sparse_vec,
        top_k=20,
    )

    if not candidates:
        raise HTTPException(status_code=404, detail="No relevant documents found")

    # 3. Rerank — top 5
    reranked = app_state["reranker"].rerank(
        query=req.query,
        candidates=candidates,
        top_k=req.top_k,
    )

    # 4. Generate answer
    result = app_state["generator"].generate(
        query=req.query,
        context_chunks=reranked,
    )

    latency_ms = int((time.time() - start) * 1000)

    # 5. Log to PostgreSQL
    try:
        conn = get_pg()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO query_logs (id, query_text, answer, sources, latency_ms)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (query_id, req.query, result["answer"],
             psycopg2.extras.Json(result["sources"]), latency_ms),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logger.warning(f"Failed to log query: {e}")

    # 6. Trace to LangFuse
    app_state["tracer"].trace_query(
        query_id=query_id,
        query=req.query,
        retrieved_chunks=candidates,
        reranked_chunks=reranked,
        answer=result["answer"],
        sources=result["sources"],
        latency_ms=latency_ms,
        model=result["model"],
    )

    return QueryResponse(
        query_id=query_id,
        query=req.query,
        answer=result["answer"],
        sources=result["sources"],
        latency_ms=latency_ms,
        model=result["model"],
    )


@app.post("/feedback/{query_id}")
def feedback(query_id: str, req: FeedbackRequest, user: dict = Depends(get_current_user)):
    if req.rating not in (1, -1):
        raise HTTPException(status_code=400, detail="Rating must be 1 or -1")

    try:
        conn = get_pg()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO feedback (query_id, rating, comment) VALUES (%s, %s, %s)",
            (query_id, req.rating, req.comment),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Score in LangFuse
    app_state["tracer"].score_feedback(query_id, req.rating, req.comment or "")

    return {"query_id": query_id, "rating": req.rating, "recorded": True}


@app.get("/query/history")
def query_history(limit: int = 50, offset: int = 0, user: dict = Depends(get_current_user)):
    conn = get_pg()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT q.id, q.query_text, q.answer, q.latency_ms, q.created_at,
                   f.rating
            FROM query_logs q
            LEFT JOIN feedback f ON q.id = f.query_id
            ORDER BY q.created_at DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
    finally:
        conn.close()
    return rows


@app.get("/documents")
def list_documents(user: dict = Depends(get_current_user)):
    conn = get_pg()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT * FROM documents WHERE status = 'indexed' ORDER BY indexed_at DESC"
        )
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
    finally:
        conn.close()
    return rows


@app.delete("/documents/{filename}")
def delete_document(filename: str, user: dict = Depends(require_admin)):
    # Remove from Qdrant
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    app_state["searcher"].client.delete(
        collection_name=config.collection_name,
        points_selector=Filter(
            must=[FieldCondition(key="filename", match=MatchValue(value=filename))]
        ),
    )

    # Update PostgreSQL
    conn = get_pg()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE documents SET status = 'deleted' WHERE filename = %s",
            (filename,),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()

    # Remove file from disk
    file_path = Path("/app/data/raw") / filename
    if file_path.exists():
        file_path.unlink()

    return {"filename": filename, "deleted": True}


# ─── Upload PDF ────────────────────────────────────────────────
@app.post("/documents/upload")
async def upload_document(file: UploadFile = File(...), user: dict = Depends(require_admin)):
    """Upload a PDF document to the raw data directory."""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    upload_dir = Path("/app/data/raw")
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / file.filename

    if dest.exists():
        raise HTTPException(status_code=409, detail=f"File already exists: {file.filename}")

    content = await file.read()
    dest.write_bytes(content)

    logger.info(f"Uploaded: {file.filename} ({len(content):,} bytes)")
    return {
        "filename": file.filename,
        "size_bytes": len(content),
        "path": str(dest),
        "message": "Upload successful. Click 'Re-index' to process the document.",
    }


# ─── Background job tracking ──────────────────────────────────
import threading
_jobs: dict = {}  # {job_id: {status, message, started_at, finished_at}}


def _run_ingest_job(job_id: str):
    """Run ingestion in background thread."""
    import subprocess
    _jobs[job_id]["status"] = "running"
    _jobs[job_id]["message"] = "Ingestion started..."
    try:
        result = subprocess.run(
            ["python", "-m", "flows.ingest_flow"],
            capture_output=True, text=True, timeout=1200,
        )
        if result.returncode == 0:
            _jobs[job_id]["status"] = "completed"
            _jobs[job_id]["message"] = "Ingestion completed successfully"
        else:
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["message"] = result.stderr[:300] or "Ingestion failed"
    except Exception as e:
        _jobs[job_id]["status"] = "failed"
        _jobs[job_id]["message"] = str(e)
    _jobs[job_id]["finished_at"] = time.time()


# ─── Re-index (async background) ──────────────────────────────
@app.post("/ingest")
async def trigger_ingest(user: dict = Depends(require_admin)):
    """Trigger ingestion pipeline in background. Returns job_id to poll status."""
    # Check if already running
    for job in _jobs.values():
        if job["status"] == "running":
            return {"job_id": None, "status": "running", "message": "Ingestion already in progress"}

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "pending", "message": "Starting...", "started_at": time.time(), "finished_at": None}

    thread = threading.Thread(target=_run_ingest_job, args=(job_id,), daemon=True)
    thread.start()

    return {"job_id": job_id, "status": "started", "message": "Ingestion started in background"}


@app.get("/ingest/status/{job_id}")
def ingest_status(job_id: str, user: dict = Depends(get_current_user)):
    """Poll ingestion job status."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job_id,
        "status": job["status"],
        "message": job["message"],
        "elapsed": round(time.time() - job["started_at"], 1) if job["started_at"] else 0,
    }


# ─── Search query history ──────────────────────────────────────
@app.get("/query/search")
def search_history(q: str = Query(..., min_length=1), limit: int = 20, user: dict = Depends(get_current_user)):
    """Search through query history by keyword."""
    conn = get_pg()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT q.id, q.query_text, q.answer, q.latency_ms, q.created_at,
                   f.rating
            FROM query_logs q
            LEFT JOIN feedback f ON q.id = f.query_id
            WHERE q.query_text ILIKE %s
            ORDER BY q.created_at DESC
            LIMIT %s
            """,
            (f"%{q}%", limit),
        )
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
    finally:
        conn.close()
    return rows


# ─── Export query as PDF ───────────────────────────────────────
@app.get("/query/{query_id}/export")
def export_query(query_id: str, user: dict = Depends(get_current_user)):
    """Export a query result as a simple HTML report (downloadable)."""
    conn = get_pg()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT * FROM query_logs WHERE id = %s",
            (query_id,),
        )
        row = cur.fetchone()
        cur.close()
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Query not found")

    sources = row.get("sources") or []
    sources_html = ""
    for i, src in enumerate(sources, 1):
        sources_html += f"""
        <div class="source">
            <div class="source-header">[{i:02d}] {src.get('filename','—')} — Page {src.get('page_num','—')} | {src.get('source','—')}</div>
            <div class="source-body">{src.get('text','')[:400]}...</div>
        </div>"""

    created_at = str(row.get("created_at", ""))[:19]
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>FinComply Report — {created_at}</title>
<style>
  body {{ font-family: 'Segoe UI', sans-serif; max-width: 800px; margin: 40px auto; color: #1e293b; line-height: 1.7; }}
  .header {{ border-bottom: 3px solid #38bdf8; padding-bottom: 16px; margin-bottom: 24px; }}
  .brand {{ font-size: 24px; font-weight: 700; color: #0ea5e9; }}
  .meta {{ font-size: 12px; color: #64748b; margin-top: 4px; font-family: monospace; }}
  .section-title {{ font-size: 11px; font-weight: 600; color: #94a3b8; letter-spacing: 2px; text-transform: uppercase; margin: 24px 0 8px; }}
  .query-box {{ background: #f0f9ff; border-left: 4px solid #38bdf8; padding: 16px 20px; border-radius: 4px; font-size: 16px; font-weight: 500; }}
  .answer-box {{ background: #f8fafc; border: 1px solid #e2e8f0; padding: 20px; border-radius: 8px; font-size: 14px; }}
  .stats {{ display: flex; gap: 24px; margin: 16px 0; }}
  .stat {{ background: #f1f5f9; padding: 12px 16px; border-radius: 6px; text-align: center; }}
  .stat-val {{ font-size: 20px; font-weight: 700; color: #0ea5e9; font-family: monospace; }}
  .stat-lbl {{ font-size: 10px; color: #94a3b8; text-transform: uppercase; letter-spacing: 1px; }}
  .source {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; margin-bottom: 10px; overflow: hidden; }}
  .source-header {{ background: #e0f2fe; padding: 10px 14px; font-size: 12px; font-weight: 600; font-family: monospace; color: #0369a1; }}
  .source-body {{ padding: 12px 14px; font-size: 13px; color: #475569; }}
  .footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid #e2e8f0; font-size: 11px; color: #94a3b8; text-align: center; }}
</style>
</head>
<body>
<div class="header">
  <div class="brand">⚖ FinComply</div>
  <div class="meta">Financial Compliance Intelligence Platform | Report generated: {created_at}</div>
</div>

<div class="section-title">Query</div>
<div class="query-box">{row.get('query_text','')}</div>

<div class="stats">
  <div class="stat"><div class="stat-val">{row.get('latency_ms','—')}ms</div><div class="stat-lbl">Latency</div></div>
  <div class="stat"><div class="stat-val">{len(sources)}</div><div class="stat-lbl">Sources</div></div>
  <div class="stat"><div class="stat-val">{query_id[:8]}…</div><div class="stat-lbl">Query ID</div></div>
</div>

<div class="section-title">Answer</div>
<div class="answer-box">{row.get('answer','')}</div>

<div class="section-title">Sources [{len(sources)}]</div>
{sources_html}

<div class="footer">Generated by FinComply — Financial Compliance Intelligence Platform</div>
</body>
</html>"""

    return StreamingResponse(
        iter([html]),
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="fincomply-report-{query_id[:8]}.html"'},
    )
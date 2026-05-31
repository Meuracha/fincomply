"""
FinComply Embedding Service v2.0
Production-grade embedding microservice with:
- Redis caching (avoid re-embedding identical queries)
- Request batching (group concurrent requests for efficiency)
- Health check with model warmup
- Prometheus metrics
"""

import asyncio
import hashlib
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from FlagEmbedding import BGEM3FlagModel
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_NAME = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))  # 1 hour
BATCH_MAX_SIZE = int(os.getenv("BATCH_MAX_SIZE", "16"))
BATCH_WAIT_MS = int(os.getenv("BATCH_WAIT_MS", "20"))  # wait 20ms to collect batch

app_state = {
    "model": None,
    "redis": None,
    "batch_queue": None,
    "batch_processor": None,
}


# ─── Batch Processor ──────────────────────────────────────────
class BatchRequest:
    def __init__(self, texts: List[str]):
        self.texts = texts
        self.future: asyncio.Future = asyncio.get_event_loop().create_future()


class BatchProcessor:
    """Collects concurrent embedding requests and processes them together."""

    def __init__(self, model, max_size: int = 16, wait_ms: int = 20):
        self.model = model
        self.max_size = max_size
        self.wait_ms = wait_ms / 1000
        self.queue: asyncio.Queue = asyncio.Queue()
        self._running = False

    async def start(self):
        self._running = True
        asyncio.create_task(self._process_loop())

    async def stop(self):
        self._running = False

    async def embed(self, texts: List[str]) -> List[Dict]:
        req = BatchRequest(texts)
        await self.queue.put(req)
        return await req.future

    async def _process_loop(self):
        while self._running:
            batch_requests: List[BatchRequest] = []
            all_texts: List[str] = []

            # Wait for first request
            try:
                first = await asyncio.wait_for(self.queue.get(), timeout=0.1)
                batch_requests.append(first)
                all_texts.extend(first.texts)
            except asyncio.TimeoutError:
                continue

            # Collect more requests within wait window
            deadline = time.time() + self.wait_ms
            while time.time() < deadline and len(all_texts) < self.max_size:
                try:
                    req = self.queue.get_nowait()
                    batch_requests.append(req)
                    all_texts.extend(req.texts)
                except asyncio.QueueEmpty:
                    await asyncio.sleep(0.001)

            # Process batch
            try:
                logger.info(f"Processing batch: {len(all_texts)} texts from {len(batch_requests)} requests")
                output = await asyncio.get_event_loop().run_in_executor(None, self._encode, all_texts)

                # Distribute results back to each request
                idx = 0
                for req in batch_requests:
                    n = len(req.texts)
                    result = []
                    for i in range(n):
                        result.append(
                            {
                                "dense": output["dense_vecs"][idx + i].tolist(),
                                "sparse": {str(k): float(v) for k, v in output["lexical_weights"][idx + i].items()},
                            }
                        )
                    req.future.set_result(result)
                    idx += n

            except Exception as e:
                for req in batch_requests:
                    if not req.future.done():
                        req.future.set_exception(e)

    def _encode(self, texts: List[str]) -> dict:
        return self.model.encode(
            texts,
            batch_size=8,
            max_length=512,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )


# ─── Cache helpers ────────────────────────────────────────────
def _cache_key(text: str) -> str:
    return f"embed:{hashlib.sha256(text.encode()).hexdigest()}"


async def _get_cached(redis, text: str) -> Optional[Dict]:
    if not redis:
        return None
    try:
        val = await redis.get(_cache_key(text))
        if val:
            return json.loads(val)
    except Exception as e:
        logger.warning(f"Cache get failed: {e}")
    return None


async def _set_cached(redis, text: str, embedding: Dict):
    if not redis:
        return
    try:
        await redis.set(_cache_key(text), json.dumps(embedding), ex=CACHE_TTL)
    except Exception as e:
        logger.warning(f"Cache set failed: {e}")


# ─── Lifespan ─────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load model
    logger.info(f"Loading embedding model: {MODEL_NAME}")
    model = BGEM3FlagModel(MODEL_NAME, use_fp16=False)
    logger.info("Model loaded — warming up...")

    # Warmup
    model.encode(["warmup"], return_dense=True, return_sparse=True, return_colbert_vecs=False)
    logger.info("Model warmed up")

    # Start batch processor
    processor = BatchProcessor(model, max_size=BATCH_MAX_SIZE, wait_ms=BATCH_WAIT_MS)
    await processor.start()

    # Connect to Redis
    redis = None
    try:
        redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
        await redis.ping()
        logger.info(f"Redis connected: {REDIS_URL}")
    except Exception as e:
        logger.warning(f"Redis unavailable — caching disabled: {e}")
        redis = None

    app_state["model"] = model
    app_state["redis"] = redis
    app_state["batch_processor"] = processor

    logger.info("Embedding service ready")
    yield

    await processor.stop()
    if redis:
        await redis.aclose()
    logger.info("Shutdown complete")


# ─── App ──────────────────────────────────────────────────────
app = FastAPI(
    title="FinComply Embedding Service",
    version="2.0.0",
    description="Production-grade embedding microservice with caching and batching",
    lifespan=lifespan,
)

Instrumentator().instrument(app).expose(app)


# ─── Schemas ──────────────────────────────────────────────────
class QueryEmbedRequest(BaseModel):
    text: str


class QueryEmbedResponse(BaseModel):
    dense: List[float]
    sparse: Dict[str, float]
    cached: bool = False


class ChunkEmbedRequest(BaseModel):
    texts: List[str]


class ChunkEmbedResponse(BaseModel):
    embeddings: List[Dict]
    cached_count: int = 0


# ─── Endpoints ────────────────────────────────────────────────
@app.get("/health")
async def health():
    redis_ok = False
    if app_state["redis"]:
        try:
            await app_state["redis"].ping()
            redis_ok = True
        except Exception:
            pass

    return {
        "status": "ok" if app_state["model"] else "loading",
        "model_loaded": app_state["model"] is not None,
        "model": MODEL_NAME,
        "redis": redis_ok,
        "cache_ttl": CACHE_TTL,
        "batch_max_size": BATCH_MAX_SIZE,
    }


@app.get("/")
def root():
    return {
        "message": "FinComply Embedding Service v2.0",
        "model": MODEL_NAME,
        "features": ["caching", "batching", "hybrid-search"],
    }


@app.post("/embed/query", response_model=QueryEmbedResponse)
async def embed_query(req: QueryEmbedRequest):
    if not app_state["model"]:
        raise HTTPException(status_code=503, detail="Model not loaded")

    # Check cache first
    cached = await _get_cached(app_state["redis"], req.text)
    if cached:
        return QueryEmbedResponse(
            dense=cached["dense"],
            sparse=cached["sparse"],
            cached=True,
        )

    # Embed via batch processor
    results = await app_state["batch_processor"].embed([req.text])
    embedding = results[0]

    # Store in cache
    await _set_cached(app_state["redis"], req.text, embedding)

    return QueryEmbedResponse(
        dense=embedding["dense"],
        sparse=embedding["sparse"],
        cached=False,
    )


@app.post("/embed/chunks", response_model=ChunkEmbedResponse)
async def embed_chunks(req: ChunkEmbedRequest):
    if not app_state["model"]:
        raise HTTPException(status_code=503, detail="Model not loaded")

    if not req.texts:
        return ChunkEmbedResponse(embeddings=[], cached_count=0)

    # Check cache for each text
    embeddings = [None] * len(req.texts)
    uncached_indices = []
    uncached_texts = []
    cached_count = 0

    for i, text in enumerate(req.texts):
        cached = await _get_cached(app_state["redis"], text)
        if cached:
            embeddings[i] = cached
            cached_count += 1
        else:
            uncached_indices.append(i)
            uncached_texts.append(text)

    # Embed uncached texts
    if uncached_texts:
        results = await app_state["batch_processor"].embed(uncached_texts)
        for i, idx in enumerate(uncached_indices):
            embeddings[idx] = results[i]
            await _set_cached(app_state["redis"], uncached_texts[i], results[i])

    return ChunkEmbedResponse(
        embeddings=embeddings,
        cached_count=cached_count,
    )

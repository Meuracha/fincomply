"""
Prefect ingestion flow: PDF/DOCX → Chunk → Embed → Index to Qdrant → Log to PostgreSQL
"""

from pathlib import Path

from prefect import flow, get_run_logger, task

from ingestion.chunker import SemanticChunker
from ingestion.config import config
from ingestion.embedder import BGEFullEmbedder
from ingestion.indexer import QdrantIndexer
from ingestion.loaders.docx_loader import DOCXLoader
from ingestion.loaders.pdf_loader import PDFLoader

# Source mapping based on filename keywords
SOURCE_MAPPING = {
    "fatf": "FATF",
    "bot": "BOT",
    "sec": "SEC",
    "aml": "FATF",
    "basel": "BASEL",
}


def detect_source(filename: str) -> str:
    filename_lower = filename.lower()
    for keyword, source in SOURCE_MAPPING.items():
        if keyword in filename_lower:
            return source
    return "UNKNOWN"


@task(retries=2, retry_delay_seconds=30)
def load_document(path: str):
    logger = get_run_logger()
    path = Path(path)
    source = detect_source(path.name)

    if path.suffix.lower() == ".pdf":
        loader = PDFLoader()
    elif path.suffix.lower() == ".docx":
        loader = DOCXLoader()
    else:
        raise ValueError(f"Unsupported file type: {path.suffix}")

    doc = loader.load(str(path), source=source)
    logger.info(f"Loaded: {doc.filename} ({doc.page_count} pages, source={source})")
    return doc


@task
def chunk_document(document):
    logger = get_run_logger()
    chunker = SemanticChunker(
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
    )
    chunks = chunker.chunk(document)
    logger.info(f"Chunked {document.filename}: {len(chunks)} chunks")
    return chunks


@task(retries=5, retry_delay_seconds=30)
def embed_chunks(chunks):
    logger = get_run_logger()
    embedder = BGEFullEmbedder(model_name="BAAI/bge-m3")
    embedded = embedder.embed_chunks(chunks)
    logger.info(f"Embedded {len(embedded)} chunks")
    return embedded


@task(retries=2)
def index_to_qdrant(embedded_chunks, document):
    logger = get_run_logger()
    indexer = QdrantIndexer(
        host=config.qdrant_host,
        port=config.qdrant_port,
        collection_name=config.collection_name,
    )
    count = indexer.upsert(embedded_chunks)
    logger.info(f"Indexed {count} chunks for {document.filename}")
    return count


@task
def log_to_postgres(document, chunk_count: int):
    """Log document metadata to PostgreSQL."""
    import psycopg2

    logger = get_run_logger()

    try:
        conn = psycopg2.connect(config.postgres_dsn)
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO documents (filename, source, page_count, chunk_count, status)
            VALUES (%s, %s, %s, %s, 'indexed')
            ON CONFLICT DO NOTHING
            """,
            (document.filename, document.source, document.page_count, chunk_count),
        )
        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"Logged document to PostgreSQL: {document.filename}")
    except Exception as e:
        logger.warning(f"Failed to log to PostgreSQL: {e}")


@flow(name="fincomply-ingest", log_prints=True)
def ingest_flow(data_dir: str = "/app/data/raw"):
    """
    Main ingestion flow.
    Scans data_dir for PDF/DOCX files and indexes them to Qdrant.
    """
    logger = get_run_logger()
    data_path = Path(data_dir)

    files = list(data_path.glob("*.pdf")) + list(data_path.glob("*.docx"))
    if not files:
        logger.warning(f"No documents found in {data_dir}")
        return

    logger.info(f"Found {len(files)} documents to ingest")

    for file_path in files:
        logger.info(f"Processing: {file_path.name}")
        try:
            document = load_document(str(file_path))
            chunks = chunk_document(document)
            embedded = embed_chunks(chunks)
            count = index_to_qdrant(embedded, document)
            log_to_postgres(document, count)
            logger.info(f"✓ Completed: {file_path.name}")
        except Exception as e:
            logger.error(f"✗ Failed: {file_path.name} — {e}")
            continue

    logger.info("Ingestion flow completed")


if __name__ == "__main__":
    ingest_flow()

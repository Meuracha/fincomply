"""
Prefect refresh flow — re-embeds all documents when embedding model is updated.
Runs weekly or triggered manually.
"""

from pathlib import Path

from prefect import flow, get_run_logger, task

from ingestion.chunker import SemanticChunker
from ingestion.config import config
from ingestion.embedder import BGEFullEmbedder as BGEEmbedder
from ingestion.indexer import QdrantIndexer
from ingestion.loaders.docx_loader import DOCXLoader
from ingestion.loaders.pdf_loader import PDFLoader


@task(retries=2)
def clear_collection():
    """Delete all vectors from Qdrant collection for full re-index."""
    logger = get_run_logger()
    from qdrant_client import QdrantClient

    client = QdrantClient(host=config.qdrant_host, port=config.qdrant_port)
    existing = [c.name for c in client.get_collections().collections]

    if config.collection_name in existing:
        client.delete_collection(config.collection_name)
        logger.info(f"Deleted collection: {config.collection_name}")
    else:
        logger.info("Collection does not exist — skipping delete")


@task
def get_all_documents(data_dir: str) -> list:
    """Scan data directory for all PDF/DOCX files."""
    logger = get_run_logger()
    data_path = Path(data_dir)
    files = list(data_path.glob("*.pdf")) + list(data_path.glob("*.docx"))
    logger.info(f"Found {len(files)} documents to re-index")
    return [str(f) for f in files]


@task(retries=1)
def reindex_document(path: str, embedder: BGEEmbedder, indexer: QdrantIndexer):
    """Re-embed and re-index a single document."""
    logger = get_run_logger()
    path = Path(path)

    # Detect source from filename
    source = "UNKNOWN"
    for keyword, src in {"fatf": "FATF", "bot": "BOT", "sec": "SEC"}.items():
        if keyword in path.name.lower():
            source = src
            break

    # Load
    if path.suffix.lower() == ".pdf":
        doc = PDFLoader().load(str(path), source=source)
    else:
        doc = DOCXLoader().load(str(path), source=source)

    # Chunk + Embed + Index
    chunks = SemanticChunker(
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
    ).chunk(doc)

    embedded = embedder.embed_chunks(chunks)
    count = indexer.upsert(embedded)

    logger.info(f"Re-indexed {path.name}: {count} chunks")
    return count


@flow(
    name="fincomply-refresh",
    log_prints=True,
)
def refresh_flow(data_dir: str = "/app/data/raw"):
    """
    Weekly refresh flow — clears Qdrant and re-indexes all documents.
    Triggered automatically every Sunday at 02:00 UTC,
    or manually when embedding model is updated.
    """
    logger = get_run_logger()
    logger.info("Starting refresh flow...")

    # Step 1: Clear existing vectors
    clear_collection()

    # Step 2: Load all document paths
    file_paths = get_all_documents(data_dir)
    if not file_paths:
        logger.warning("No documents found — refresh aborted")
        return

    # Step 3: Re-initialize embedder and indexer (picks up new model version)
    embedder = BGEFullEmbedder(model_name=config.embedding_model)
    indexer = QdrantIndexer(
        host=config.qdrant_host,
        port=config.qdrant_port,
        collection_name=config.collection_name,
    )

    # Step 4: Re-index all documents
    total = 0
    failed = 0
    for path in file_paths:
        try:
            count = reindex_document(path, embedder, indexer)
            total += count
        except Exception as e:
            logger.error(f"Failed to re-index {path}: {e}")
            failed += 1

    logger.info(f"Refresh complete: {total} chunks indexed, {failed} documents failed")


if __name__ == "__main__":
    refresh_flow()

"""
Embedding client — calls the dedicated Embedding Service via HTTP.
Both API and Ingestion containers use this same client.
Embedding Service runs bge-m3 with dense + sparse (hybrid search support).
"""

import logging
import os
from typing import List, Tuple

import requests

logger = logging.getLogger(__name__)

EMBEDDING_SERVICE_URL = os.getenv("EMBEDDING_SERVICE_URL", "http://embedding:8001")


class BGEEmbedder:
    """HTTP client for the Embedding Service."""

    def __init__(self, model_name: str = "BAAI/bge-m3"):
        self.base_url = EMBEDDING_SERVICE_URL
        self.model_name = model_name
        logger.info(f"Embedding client initialized → {self.base_url}")

    def embed_query(self, query: str) -> Tuple[List[float], dict]:
        """Embed a single query — returns (dense, sparse)."""
        response = requests.post(
            f"{self.base_url}/embed/query",
            json={"text": query},
            timeout=120,  # 2 min for query embedding
        )
        response.raise_for_status()
        data = response.json()
        # sparse keys are strings from JSON, convert to int
        sparse = {int(k): v for k, v in data["sparse"].items()}
        return data["dense"], sparse

    def embed_chunks(self, chunks) -> List[dict]:
        """Embed multiple chunks — returns list with dense + sparse."""
        texts = [chunk.text for chunk in chunks]
        batch_size = 20  # send 20 chunks at a time to avoid timeout

        logger.info(f"Embedding {len(texts)} chunks via service (batch_size={batch_size})...")

        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            response = requests.post(
                f"{self.base_url}/embed/chunks",
                json={"texts": batch_texts},
                timeout=300,
            )
            response.raise_for_status()
            all_embeddings.extend(response.json()["embeddings"])
            logger.info(f"Embedded {min(i + batch_size, len(texts))}/{len(texts)} chunks")

        results = []
        for i, chunk in enumerate(chunks):
            sparse = {int(k): v for k, v in all_embeddings[i]["sparse"].items()}
            results.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "text": chunk.text,
                    "filename": chunk.filename,
                    "source": chunk.source,
                    "page_num": chunk.page_num,
                    "chunk_index": chunk.chunk_index,
                    "dense_vector": all_embeddings[i]["dense"],
                    "sparse_vector": sparse,
                }
            )

        logger.info(f"Embedded {len(results)} chunks")
        return results


# Keep BGEFullEmbedder as alias for backward compatibility
BGEFullEmbedder = BGEEmbedder

"""
Hybrid search: dense vector (bge-m3) + sparse (BM25-like) via Qdrant RRF fusion.
"""

import logging
from typing import List

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Fusion,
    FusionQuery,
    Prefetch,
    SparseVector,
)

logger = logging.getLogger(__name__)


class HybridSearcher:
    def __init__(self, host: str, port: int, collection_name: str):
        self.client = QdrantClient(host=host, port=port)
        self.collection_name = collection_name

    def search(
        self,
        dense_vector: List[float],
        sparse_vector: dict,
        top_k: int = 20,
    ) -> List[dict]:
        """
        Hybrid search using Qdrant's built-in RRF fusion.
        Combines dense cosine similarity + sparse lexical matching.
        """
        sparse_indices = list(sparse_vector.keys())
        sparse_values = list(sparse_vector.values())

        results = self.client.query_points(
            collection_name=self.collection_name,
            prefetch=[
                Prefetch(
                    query=dense_vector,
                    using="dense",
                    limit=top_k,
                ),
                Prefetch(
                    query=SparseVector(
                        indices=sparse_indices,
                        values=sparse_values,
                    ),
                    using="sparse",
                    limit=top_k,
                ),
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            limit=top_k,
        )

        return [
            {
                "chunk_id": str(point.id),
                "text": point.payload.get("text", ""),
                "filename": point.payload.get("filename", ""),
                "source": point.payload.get("source", ""),
                "page_num": point.payload.get("page_num", 0),
                "score": point.score,
            }
            for point in results.points
        ]
        
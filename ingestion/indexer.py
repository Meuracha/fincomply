"""
Qdrant indexer — upserts embedded chunks to vector database.
Uses named vectors for hybrid search (dense + sparse).
"""
import logging
from typing import List

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    SparseVectorParams,
    SparseIndexParams,
    PointStruct,
    SparseVector,
)

logger = logging.getLogger(__name__)

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"
EMBEDDING_DIM = 1024  # bge-m3 dimension


class QdrantIndexer:
    def __init__(self, host: str, port: int, collection_name: str):
        self.client = QdrantClient(host=host, port=port)
        self.collection_name = collection_name
        self._ensure_collection()

    def _ensure_collection(self):
        existing = [c.name for c in self.client.get_collections().collections]
        if self.collection_name not in existing:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    DENSE_VECTOR_NAME: VectorParams(
                        size=EMBEDDING_DIM,
                        distance=Distance.COSINE,
                    )
                },
                sparse_vectors_config={
                    SPARSE_VECTOR_NAME: SparseVectorParams(
                        index=SparseIndexParams(on_disk=False)
                    )
                },
            )
            logger.info(f"Created collection: {self.collection_name}")
        else:
            logger.info(f"Collection exists: {self.collection_name}")

    def upsert(self, embedded_chunks: List[dict]) -> int:
        points = []
        for chunk in embedded_chunks:
            sparse = chunk["sparse_vector"]
            points.append(
                PointStruct(
                    id=chunk["chunk_id"],
                    vector={
                        DENSE_VECTOR_NAME: chunk["dense_vector"],
                        SPARSE_VECTOR_NAME: SparseVector(
                            indices=list(sparse.keys()),
                            values=list(sparse.values()),
                        ),
                    },
                    payload={
                        "text": chunk["text"],
                        "filename": chunk["filename"],
                        "source": chunk["source"],
                        "page_num": chunk["page_num"],
                        "chunk_index": chunk["chunk_index"],
                    },
                )
            )

        batch_size = 100
        for i in range(0, len(points), batch_size):
            self.client.upsert(
                collection_name=self.collection_name,
                points=points[i: i + batch_size],
            )

        logger.info(f"Upserted {len(points)} chunks to Qdrant")
        return len(points)

    def delete_by_filename(self, filename: str) -> int:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        result = self.client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="filename", match=MatchValue(value=filename))]
            ),
        )
        logger.info(f"Deleted chunks for: {filename}")
        return result.status
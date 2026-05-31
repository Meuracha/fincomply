"""
Cohere Rerank — re-scores top-K candidates for higher precision.
Reduces top-20 hybrid search results to top-5 most relevant chunks.
"""
import logging
from typing import List

import cohere

logger = logging.getLogger(__name__)


class CohereReranker:
    def __init__(self, api_key: str, model: str = "rerank-english-v3.0"):
        self.client = cohere.Client(api_key)
        self.model = model

    def rerank(
        self,
        query: str,
        candidates: List[dict],
        top_k: int = 5,
    ) -> List[dict]:
        """
        Rerank candidates using Cohere cross-encoder.
        Returns top_k most relevant chunks with updated scores.
        """
        if not candidates:
            return []

        documents = [c["text"] for c in candidates]

        response = self.client.rerank(
            model=self.model,
            query=query,
            documents=documents,
            top_n=top_k,
        )

        reranked = []
        for result in response.results:
            candidate = candidates[result.index]
            reranked.append({
                **candidate,
                "rerank_score": result.relevance_score,
            })

        logger.info(f"Reranked {len(candidates)} → {len(reranked)} chunks")
        return reranked

"""
LangFuse observability — traces every RAG query end-to-end.
Tracks: retrieval, reranking, generation, feedback, latency.
"""

import logging
from typing import List, Optional

from langfuse import Langfuse

logger = logging.getLogger(__name__)


class FinComplyTracer:
    def __init__(self, public_key: str, secret_key: str, base_url: str):
        if public_key and secret_key:
            self.langfuse = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=base_url,
            )
            self.enabled = True
        else:
            self.langfuse = None
            self.enabled = False
            logger.warning("LangFuse not configured — observability disabled")

    def trace_query(
        self,
        query_id: str,
        query: str,
        retrieved_chunks: List[dict],
        reranked_chunks: List[dict],
        answer: str,
        sources: List[dict],
        latency_ms: int,
        model: str,
    ) -> Optional[str]:
        """Trace a full RAG query pipeline."""
        if not self.enabled:
            return None

        try:
            trace = self.langfuse.trace(
                id=query_id,
                name="rag-query",
                input={"query": query},
                output={"answer": answer},
                metadata={
                    "latency_ms": latency_ms,
                    "retrieved_count": len(retrieved_chunks),
                    "reranked_count": len(reranked_chunks),
                    "model": model,
                },
            )

            # Span: retrieval
            trace.span(
                name="hybrid-search",
                input={"query": query},
                output={"chunks": len(retrieved_chunks)},
            )

            # Span: reranking
            trace.span(
                name="cohere-rerank",
                input={"candidates": len(retrieved_chunks)},
                output={"reranked": len(reranked_chunks)},
            )

            # Generation span
            trace.generation(
                name="groq-generation",
                model=model,
                input=query,
                output=answer,
            )

            self.langfuse.flush()
            return trace.id

        except Exception as e:
            logger.warning(f"LangFuse trace failed: {e}")
            return None

    def score_feedback(self, trace_id: str, rating: int, comment: str = ""):
        """Record user feedback (1=positive, -1=negative)."""
        if not self.enabled or not trace_id:
            return
        try:
            self.langfuse.score(
                trace_id=trace_id,
                name="user-feedback",
                value=rating,
                comment=comment,
            )
            self.langfuse.flush()
        except Exception as e:
            logger.warning(f"LangFuse score failed: {e}")

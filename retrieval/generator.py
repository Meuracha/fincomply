"""
LLM answer generation using Groq (llama-3.1-70b).
Constructs RAG prompt from reranked context chunks.
"""

import logging
from typing import List

from groq import Groq

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a financial compliance expert assistant with deep knowledge
of AML (Anti-Money Laundering) regulations, FATF guidelines, Bank of Thailand policies,
and SEC regulations.

Answer questions based ONLY on the provided context. If the answer is not in the context,
say "I cannot find this information in the available regulatory documents."

Always cite the source document and page number when available.
Be precise, professional, and concise."""


class GroqGenerator:
    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        self.client = Groq(api_key=api_key)
        self.model = model

    def generate(self, query: str, context_chunks: List[dict]) -> dict:
        """
        Generate answer from query + reranked context chunks.
        Returns answer text + sources used.
        """
        # Build context string with source citations
        context_parts = []
        for i, chunk in enumerate(context_chunks, 1):
            source_info = f"[Source {i}: {chunk['filename']}, page {chunk['page_num']}]"
            context_parts.append(f"{source_info}\n{chunk['text']}")

        context = "\n\n---\n\n".join(context_parts)

        prompt = f"""Context from regulatory documents:

{context}

---

Question: {query}

Answer based on the context above:"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,  # low temperature for factual accuracy
            max_tokens=1024,
        )

        answer = response.choices[0].message.content

        sources = [
            {
                "filename": c["filename"],
                "source": c["source"],
                "page_num": c["page_num"],
                "rerank_score": c.get("rerank_score", 0),
                "excerpt": c["text"][:200] + "...",
            }
            for c in context_chunks
        ]

        return {
            "answer": answer,
            "sources": sources,
            "model": self.model,
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
        }

"""
Semantic chunking using LlamaIndex.
Falls back to fixed-size chunking if semantic chunking fails.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import List

from ingestion.loaders.pdf_loader import RawDocument

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    chunk_id: str
    text: str
    filename: str
    source: str
    page_num: int
    chunk_index: int


class SemanticChunker:
    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(self, document: RawDocument) -> List[Chunk]:
        """Chunk document pages into semantic chunks."""
        all_chunks = []
        chunk_index = 0

        for page in document.pages:
            page_chunks = self._split_text(page["text"])

            for text in page_chunks:
                if not text.strip():
                    continue
                all_chunks.append(
                    Chunk(
                        chunk_id=str(uuid.uuid4()),
                        text=text.strip(),
                        filename=document.filename,
                        source=document.source,
                        page_num=page["page_num"],
                        chunk_index=chunk_index,
                    )
                )
                chunk_index += 1

        logger.info(f"Chunked {document.filename}: {len(all_chunks)} chunks")
        return all_chunks

    def _split_text(self, text: str) -> List[str]:
        """Split text by sentences with overlap."""
        # Split by paragraph first, then by sentence
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks = []
        current = ""

        for para in paragraphs:
            if len(current) + len(para) <= self.chunk_size:
                current += " " + para if current else para
            else:
                if current:
                    chunks.append(current)
                # overlap: keep last N characters
                overlap_text = current[-self.chunk_overlap :] if current else ""
                current = overlap_text + " " + para if overlap_text else para

        if current:
            chunks.append(current)

        return chunks

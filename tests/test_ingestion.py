"""
Unit tests for ingestion pipeline.
"""
import pytest
from unittest.mock import MagicMock, patch
from ingestion.chunker import SemanticChunker
from ingestion.loaders.pdf_loader import RawDocument, clean_thai_text


def make_document(text: str) -> RawDocument:
    return RawDocument(
        filename="test.pdf",
        source="FATF",
        page_count=1,
        pages=[{"page_num": 1, "text": text}],
    )


class TestSemanticChunker:
    def test_basic_chunking(self):
        chunker = SemanticChunker(chunk_size=100, chunk_overlap=20)
        doc = make_document("This is a test document. " * 20)
        chunks = chunker.chunk(doc)
        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.text
            assert chunk.filename == "test.pdf"
            assert chunk.source == "FATF"

    def test_empty_document(self):
        chunker = SemanticChunker()
        doc = make_document("")
        chunks = chunker.chunk(doc)
        assert len(chunks) == 0

    def test_chunk_ids_unique(self):
        chunker = SemanticChunker(chunk_size=50, chunk_overlap=10)
        doc = make_document("Paragraph one content here. " * 10)
        chunks = chunker.chunk(doc)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_metadata_preserved(self):
        chunker = SemanticChunker()
        doc = make_document("FATF recommends that countries implement risk-based approaches.")
        chunks = chunker.chunk(doc)
        assert all(c.source == "FATF" for c in chunks)
        assert all(c.filename == "test.pdf" for c in chunks)


class TestThaiTextCleaning:
    def test_sara_am_fix(self):
        """Test that sara am split artifacts are fixed."""
        text = "ส านักงาน ปปง"
        result = clean_thai_text(text)
        assert "สำนักงาน" in result

    def test_sara_a_fix(self):
        """Test that sara a encoded as sara am is corrected."""
        text = "รำยงำน"
        result = clean_thai_text(text)
        assert "รายงาน" in result

    def test_whitespace_normalization(self):
        """Test that excessive whitespace is removed."""
        text = "hello   world\n\n\n\ntest"
        result = clean_thai_text(text)
        assert "   " not in result
        assert "\n\n\n" not in result

    def test_empty_text(self):
        result = clean_thai_text("")
        assert result == ""

    def test_none_text(self):
        result = clean_thai_text(None)
        assert result is None

    def test_normal_thai_preserved(self):
        """Test that normal Thai text is not corrupted."""
        text = "ธุรกรรมที่มีเหตุอันควรสงสัย"
        result = clean_thai_text(text)
        assert "ธุรกรรม" in result
        assert "สงสัย" in result
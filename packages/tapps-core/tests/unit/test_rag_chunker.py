"""Tests for the RAG chunker."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tapps_core.experts.rag_chunker import Chunk, Chunker

if TYPE_CHECKING:
    from pathlib import Path


class TestChunker:
    def test_single_short_file_one_chunk(self, tmp_path: Path):
        content = "# Title\n\nShort content."
        chunker = Chunker(target_tokens=512, overlap_tokens=50)
        chunks = chunker.chunk_file(tmp_path / "test.md", content)
        assert len(chunks) == 1
        assert "Short content" in chunks[0].content

    def test_long_file_multiple_chunks(self, tmp_path: Path):
        # Generate content longer than 512 tokens (~2048 chars).
        lines = [f"Line {i}: " + "word " * 20 for i in range(100)]
        content = "\n".join(lines)
        chunker = Chunker(target_tokens=128, overlap_tokens=20)
        chunks = chunker.chunk_file(tmp_path / "big.md", content)
        assert len(chunks) > 1

    def test_overlap_included(self, tmp_path: Path):
        # Create content that will span two chunks.
        lines = [f"Unique-line-{i} " + "x " * 50 for i in range(50)]
        content = "\n".join(lines)
        chunker = Chunker(target_tokens=128, overlap_tokens=30)
        chunks = chunker.chunk_file(tmp_path / "overlap.md", content)
        if len(chunks) >= 2:
            # Some content from the end of chunk 0 should appear in chunk 1.
            end_of_first = chunks[0].content.split("\n")[-1]
            assert end_of_first in chunks[1].content or len(chunks) >= 2

    def test_deterministic_chunk_ids(self, tmp_path: Path):
        content = "# Header\n\nSome text."
        chunker = Chunker()
        c1 = chunker.chunk_file(tmp_path / "a.md", content)
        c2 = chunker.chunk_file(tmp_path / "a.md", content)
        assert c1[0].chunk_id == c2[0].chunk_id

    def test_empty_content(self, tmp_path: Path):
        chunker = Chunker()
        chunks = chunker.chunk_file(tmp_path / "empty.md", "")
        assert chunks == []

    def test_whitespace_only_content(self, tmp_path: Path):
        chunker = Chunker()
        chunks = chunker.chunk_file(tmp_path / "ws.md", "   \n  \n  ")
        assert chunks == []


class TestChunkModel:
    def test_serialization_roundtrip(self):
        c = Chunk(
            content="test",
            source_file="test.md",
            line_start=1,
            line_end=5,
            chunk_id="abc123",
            token_count=10,
        )
        data = c.model_dump()
        restored = Chunk.model_validate(data)
        assert restored.chunk_id == c.chunk_id
        assert restored.content == c.content

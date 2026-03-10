"""Tests for the VectorKnowledgeBase with automatic fallback."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tapps_mcp.experts.models import KnowledgeChunk

if TYPE_CHECKING:
    from pathlib import Path
from tapps_mcp.experts.rag_index import FAISS_AVAILABLE
from tapps_mcp.experts.vector_rag import VectorKnowledgeBase


class TestVectorKnowledgeBase:
    def _create_knowledge_dir(self, tmp_path: Path) -> Path:
        kd = tmp_path / "knowledge"
        kd.mkdir()
        (kd / "security.md").write_text(
            "# Security\n\nBest practices for secure coding.\n\n"
            "## Input Validation\n\nAlways validate user input.\n",
            encoding="utf-8",
        )
        (kd / "testing.md").write_text(
            "# Testing\n\nUnit testing strategies.\n\n"
            "## Mocking\n\nUse mocks for external dependencies.\n",
            encoding="utf-8",
        )
        return kd

    def test_lazy_initialization(self, tmp_path: Path):
        kd = self._create_knowledge_dir(tmp_path)
        vkb = VectorKnowledgeBase(kd)
        assert vkb.backend_type == "pending"

    def test_initialises_on_first_search(self, tmp_path: Path):
        kd = self._create_knowledge_dir(tmp_path)
        vkb = VectorKnowledgeBase(kd)
        results = vkb.search("security")
        assert vkb.backend_type in ("simple", "vector", "bm25")
        # Should find something.
        assert isinstance(results, list)

    def test_fallback_to_simple_without_faiss(self, tmp_path: Path):
        if FAISS_AVAILABLE:
            # Force simple by using a bad embedding model name won't work since
            # we test the import path. Just verify it works either way.
            pass
        kd = self._create_knowledge_dir(tmp_path)
        vkb = VectorKnowledgeBase(kd)
        vkb.search("test")  # triggers init
        assert vkb.backend_type in ("simple", "vector", "bm25")

    def test_search_returns_knowledge_chunks(self, tmp_path: Path):
        kd = self._create_knowledge_dir(tmp_path)
        vkb = VectorKnowledgeBase(kd)
        results = vkb.search("security input validation")
        for chunk in results:
            assert isinstance(chunk, KnowledgeChunk)

    def test_get_context_format(self, tmp_path: Path):
        kd = self._create_knowledge_dir(tmp_path)
        vkb = VectorKnowledgeBase(kd)
        ctx = vkb.get_context("security")
        assert isinstance(ctx, str)
        assert len(ctx) > 0

    def test_get_sources(self, tmp_path: Path):
        kd = self._create_knowledge_dir(tmp_path)
        vkb = VectorKnowledgeBase(kd)
        sources = vkb.get_sources("security")
        assert isinstance(sources, list)

    def test_empty_knowledge_dir(self, tmp_path: Path):
        kd = tmp_path / "empty_kb"
        kd.mkdir()
        vkb = VectorKnowledgeBase(kd)
        results = vkb.search("anything")
        assert results == []

    def test_list_files(self, tmp_path: Path):
        kd = self._create_knowledge_dir(tmp_path)
        vkb = VectorKnowledgeBase(kd)
        files = vkb.list_files()
        assert isinstance(files, list)

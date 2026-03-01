"""Tests for the FAISS-based RAG vector index."""

from __future__ import annotations

import pytest

from tapps_core.experts.rag_chunker import Chunk
from tapps_core.experts.rag_index import FAISS_AVAILABLE, IndexMetadata, VectorIndex


class TestIndexMetadata:
    def test_schema_version_default(self):
        m = IndexMetadata(model_name="test", embedding_dim=128, chunk_count=10)
        assert m.schema_version == "1.0"

    def test_serialization_roundtrip(self):
        m = IndexMetadata(
            model_name="all-MiniLM-L6-v2",
            embedding_dim=384,
            chunk_count=50,
            source_files=["a.md", "b.md"],
            source_fingerprint="abc123",
        )
        data = m.model_dump()
        restored = IndexMetadata.model_validate(data)
        assert restored.model_name == m.model_name
        assert restored.chunk_count == 50


@pytest.mark.skipif(not FAISS_AVAILABLE, reason="faiss-cpu not installed")
class TestVectorIndex:
    def _make_chunks(self) -> list[Chunk]:
        return [
            Chunk(
                content="Python security best practices for web applications",
                source_file="security.md",
                line_start=1,
                line_end=5,
                chunk_id="chunk-1",
                token_count=10,
            ),
            Chunk(
                content="Testing strategies for Django REST framework",
                source_file="testing.md",
                line_start=1,
                line_end=5,
                chunk_id="chunk-2",
                token_count=10,
            ),
        ]

    def test_build_requires_embedder(self):
        vi = VectorIndex(embedder=None)
        with pytest.raises(ValueError, match="embedder"):
            vi.build(self._make_chunks())

    def test_build_requires_chunks(self):
        from tapps_core.experts.rag_embedder import create_embedder

        embedder = create_embedder()
        if embedder is None:
            pytest.skip("no embedder available")
        vi = VectorIndex(embedder=embedder)
        with pytest.raises(ValueError, match="chunk"):
            vi.build([])

    def test_build_and_search(self):
        from tapps_core.experts.rag_embedder import create_embedder

        embedder = create_embedder()
        if embedder is None:
            pytest.skip("no embedder available")

        vi = VectorIndex(embedder=embedder)
        vi.build(self._make_chunks())
        assert vi.chunk_count == 2

        results = vi.search("security web app", top_k=2, similarity_threshold=0.0)
        assert len(results) > 0
        assert results[0][1] >= 0.0  # similarity score

    def test_save_and_load_roundtrip(self, tmp_path):
        from tapps_core.experts.rag_embedder import create_embedder

        embedder = create_embedder()
        if embedder is None:
            pytest.skip("no embedder available")

        vi = VectorIndex(embedder=embedder)
        vi.build(self._make_chunks())
        vi.save(tmp_path / "index")

        loaded = VectorIndex.load(tmp_path / "index", embedder=embedder)
        assert loaded.is_valid()
        assert loaded.chunk_count == 2


class TestVectorIndexWithoutFAISS:
    def test_raises_without_faiss(self):
        if FAISS_AVAILABLE:
            pytest.skip("faiss-cpu is installed")
        with pytest.raises(ImportError, match="faiss"):
            VectorIndex()

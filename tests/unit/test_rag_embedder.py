"""Tests for the RAG embedder."""

from __future__ import annotations

import pytest

from tapps_mcp.experts.rag_embedder import (
    SENTENCE_TRANSFORMERS_AVAILABLE,
    Embedder,
    SentenceTransformerEmbedder,
    create_embedder,
)


class TestEmbedderABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            Embedder()  # type: ignore[abstract]


class TestCreateEmbedder:
    def test_returns_none_without_dependency(self):
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            pytest.skip("sentence-transformers is installed")
        result = create_embedder()
        assert result is None


@pytest.mark.skipif(
    not SENTENCE_TRANSFORMERS_AVAILABLE,
    reason="sentence-transformers not installed",
)
class TestSentenceTransformerEmbedder:
    def test_embedding_dimension(self):
        embedder = SentenceTransformerEmbedder()
        dim = embedder.get_embedding_dim()
        assert dim > 0

    def test_embed_produces_correct_shape(self):
        embedder = SentenceTransformerEmbedder()
        texts = ["hello world", "test embedding"]
        result = embedder.embed(texts)
        assert len(result) == 2
        assert len(result[0]) == embedder.get_embedding_dim()

    def test_model_name(self):
        embedder = SentenceTransformerEmbedder()
        assert embedder.get_model_name() == "all-MiniLM-L6-v2"

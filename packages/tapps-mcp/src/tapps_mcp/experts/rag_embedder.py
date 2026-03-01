"""Backward-compatible re-export."""
from __future__ import annotations

from tapps_core.experts.rag_embedder import Embedder as Embedder
from tapps_core.experts.rag_embedder import (
    SENTENCE_TRANSFORMERS_AVAILABLE as SENTENCE_TRANSFORMERS_AVAILABLE,
)
from tapps_core.experts.rag_embedder import (
    SentenceTransformerEmbedder as SentenceTransformerEmbedder,
)
from tapps_core.experts.rag_embedder import create_embedder as create_embedder

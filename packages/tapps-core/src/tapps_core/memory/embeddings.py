"""Backward-compatible re-export from tapps-brain."""

from tapps_brain.embeddings import EmbeddingProvider as EmbeddingProvider
from tapps_brain.embeddings import NoopProvider as NoopProvider
from tapps_brain.embeddings import (
    SentenceTransformerProvider as SentenceTransformerProvider,
)
from tapps_brain.embeddings import (
    get_embedding_provider as get_embedding_provider,
)

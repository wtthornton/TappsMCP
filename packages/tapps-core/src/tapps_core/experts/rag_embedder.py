"""Embedding interface and optional sentence-transformers implementation.

The ``sentence-transformers`` and ``numpy`` packages are optional.  When
unavailable, :func:`create_embedder` returns ``None`` and callers should
fall back to keyword-based search.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import structlog

logger = structlog.get_logger(__name__)

# Optional dependency check.
try:
    from sentence_transformers import SentenceTransformer

    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

_DEFAULT_MODEL = "all-MiniLM-L6-v2"


class Embedder(ABC):
    """Abstract base class for text embedding."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts and return vectors."""
        ...

    @abstractmethod
    def get_embedding_dim(self) -> int:
        """Return the dimensionality of embeddings."""
        ...

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the model identifier."""
        ...


class SentenceTransformerEmbedder(Embedder):
    """Embedder backed by ``sentence-transformers``."""

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            msg = (
                "sentence-transformers is required for vector RAG. "
                "Install with: pip install tapps-mcp[rag]"
            )
            raise ImportError(msg)

        self._model_name = model_name
        self._model = SentenceTransformer(model_name)
        self._dim: int = self._model.get_sentence_embedding_dimension()

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed *texts* using the sentence-transformers model."""
        embeddings = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [e.tolist() for e in embeddings]

    def get_embedding_dim(self) -> int:
        return self._dim

    def get_model_name(self) -> str:
        return self._model_name


def create_embedder(model_name: str | None = None) -> Embedder | None:
    """Factory: return an :class:`Embedder`, or ``None`` if unavailable.

    This never raises -- callers should check for ``None`` and fall back
    to keyword-based RAG.
    """
    if not SENTENCE_TRANSFORMERS_AVAILABLE:
        logger.debug("sentence_transformers_unavailable", msg="falling back to keyword RAG")
        return None

    try:
        return SentenceTransformerEmbedder(model_name or _DEFAULT_MODEL)
    except (ImportError, OSError, RuntimeError, ValueError) as e:
        logger.warning("embedder_creation_failed", error=str(e))
        return None

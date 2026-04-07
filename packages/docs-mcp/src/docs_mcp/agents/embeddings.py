"""Embedding backend abstraction for DocsMCP agent matching.

Provides a pluggable interface for computing text embeddings, with
a local sentence-transformers implementation and a stub for testing.
Includes disk-based caching keyed by content hash.
"""

from __future__ import annotations

import hashlib
import json
import math
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import structlog

logger: Any = structlog.get_logger(__name__)


class EmbeddingBackend(ABC):
    """Abstract base class for embedding computation."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Compute embedding vectors for a batch of texts.

        Args:
            texts: List of strings to embed.

        Returns:
            List of embedding vectors (same length as texts).
        """

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Dimensionality of the embedding vectors."""


class StubEmbeddingBackend(EmbeddingBackend):
    """Test backend that returns deterministic hash-based vectors.

    Produces consistent vectors for the same input text, enabling
    reproducible tests without a real embedding model.
    """

    def __init__(self, dimension: int = 384) -> None:
        self._dimension = dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate deterministic pseudo-embeddings from text hashes."""
        results: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).hexdigest()
            # Convert hex chars to float values in [-1, 1]
            values: list[float] = []
            for i in range(self._dimension):
                hex_idx = i % len(digest)
                raw = int(digest[hex_idx], 16) / 15.0  # [0, 1]
                values.append(raw * 2 - 1)  # [-1, 1]
            # Normalize to unit vector
            norm = math.sqrt(sum(v * v for v in values))
            if norm > 0:
                values = [v / norm for v in values]
            results.append(values)
        return results

    @property
    def dimension(self) -> int:
        return self._dimension


class LocalEmbeddingBackend(EmbeddingBackend):
    """Embedding backend using sentence-transformers (local CPU inference).

    Uses ``all-MiniLM-L6-v2`` by default (~80MB, ~5ms per embedding).
    Requires ``sentence-transformers`` to be installed.
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
    ) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            msg = (
                "sentence-transformers is required for local embeddings. "
                "Install with: uv add 'docs-mcp[agents]'"
            )
            raise ImportError(msg) from exc

        self._model: Any = SentenceTransformer(model_name)
        self._dimension: int = self._model.get_sentence_embedding_dimension()
        logger.info(
            "embedding_model_loaded",
            model=model_name,
            dimension=self._dimension,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Compute embeddings using the local sentence-transformers model."""
        embeddings = self._model.encode(texts, normalize_embeddings=True)
        return [vec.tolist() for vec in embeddings]

    @property
    def dimension(self) -> int:
        return self._dimension


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Assumes vectors are already normalized (unit vectors), in which case
    cosine similarity equals the dot product.
    """
    if len(vec_a) != len(vec_b):
        return 0.0

    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=True))
    # Clamp to [-1, 1] to handle floating-point drift
    return max(-1.0, min(1.0, dot))


class EmbeddingCache:
    """Disk-based cache for embedding vectors keyed by content hash.

    Stores vectors as JSON files in the cache directory. Cache keys
    are SHA256 hashes of the input text, so stale entries are
    automatically ignored when content changes.
    """

    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _key_path(self, text: str) -> Path:
        """Compute the cache file path for a given text."""
        digest = hashlib.sha256(text.encode()).hexdigest()
        return self._cache_dir / f"{digest}.json"

    def get(self, text: str) -> list[float] | None:
        """Retrieve a cached embedding vector, or None if not cached."""
        path = self._key_path(text)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, OSError):
            pass
        return None

    def put(self, text: str, vector: list[float]) -> None:
        """Store an embedding vector in the cache."""
        path = self._key_path(text)
        try:
            path.write_text(json.dumps(vector), encoding="utf-8")
        except OSError:
            logger.debug("embedding_cache_write_error", path=str(path))

    def get_or_compute(
        self,
        texts: list[str],
        backend: EmbeddingBackend,
    ) -> list[list[float]]:
        """Retrieve cached embeddings or compute and cache missing ones.

        Batches uncached texts for efficient computation.
        """
        results: list[list[float] | None] = []
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        for i, text in enumerate(texts):
            cached = self.get(text)
            if cached is not None:
                results.append(cached)
            else:
                results.append(None)
                uncached_indices.append(i)
                uncached_texts.append(text)

        if uncached_texts:
            computed = backend.embed(uncached_texts)
            for idx, vector in zip(uncached_indices, computed, strict=True):
                results[idx] = vector
                self.put(texts[idx], vector)

        return [r for r in results if r is not None]

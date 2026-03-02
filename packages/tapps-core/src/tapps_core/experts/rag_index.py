"""FAISS-based vector index for RAG knowledge retrieval.

The ``faiss-cpu`` and ``numpy`` packages are optional.  When unavailable,
:class:`VectorIndex` will raise :class:`ImportError` on construction.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path  # noqa: TC003
from typing import Any

import structlog
from pydantic import BaseModel, Field

from tapps_core.config.feature_flags import feature_flags as _ff
from tapps_core.experts.rag_chunker import Chunk
from tapps_core.experts.rag_embedder import Embedder  # noqa: TC001

logger = structlog.get_logger(__name__)

# Optional dependency check — delegates to centralized feature flags.
FAISS_AVAILABLE = _ff.faiss

if FAISS_AVAILABLE:
    import faiss
    import numpy as np


class IndexMetadata(BaseModel):
    """Metadata stored alongside a FAISS index on disk."""

    schema_version: str = Field(default="1.0", description="Index format version.")
    model_name: str = Field(description="Embedding model name.")
    embedding_dim: int = Field(description="Embedding dimensionality.")
    chunk_count: int = Field(ge=0, description="Number of indexed chunks.")
    chunk_params: dict[str, Any] = Field(
        default_factory=dict, description="Chunker parameters used."
    )
    source_files: list[str] = Field(default_factory=list, description="Source files included.")
    source_fingerprint: str = Field(
        default="", description="Hash of source file set for invalidation."
    )


class VectorIndex:
    """FAISS flat-L2 index over document chunks.

    Requires ``faiss-cpu`` and ``numpy``.
    """

    def __init__(self, embedder: Embedder | None = None) -> None:
        if not FAISS_AVAILABLE:
            msg = "faiss-cpu is required for vector RAG. Install with: pip install tapps-mcp[rag]"
            raise ImportError(msg)

        self._embedder = embedder
        self._index: Any = None  # faiss.Index
        self._chunks: list[Chunk] = []
        self._metadata: IndexMetadata | None = None

    @property
    def chunk_count(self) -> int:
        """Number of chunks in the index."""
        return len(self._chunks)

    def build(
        self,
        chunks: list[Chunk],
        chunk_params: dict[str, Any] | None = None,
    ) -> None:
        """Build the FAISS index from *chunks*.

        Raises:
            ValueError: If no embedder or chunks are provided.
        """
        if self._embedder is None:
            msg = "An embedder is required to build the index"
            raise ValueError(msg)
        if not chunks:
            msg = "At least one chunk is required to build the index"
            raise ValueError(msg)

        texts = [c.content for c in chunks]
        embeddings = self._embedder.embed(texts)

        dim = self._embedder.get_embedding_dim()
        arr = np.array(embeddings, dtype=np.float32)

        self._index = faiss.IndexFlatL2(dim)
        self._index.add(arr)
        self._chunks = list(chunks)

        source_files = sorted({c.source_file for c in chunks})
        self._metadata = IndexMetadata(
            model_name=self._embedder.get_model_name(),
            embedding_dim=dim,
            chunk_count=len(chunks),
            chunk_params=chunk_params or {},
            source_files=source_files,
            source_fingerprint=_fingerprint(source_files),
        )

    def search(
        self,
        query_text: str,
        top_k: int = 5,
        similarity_threshold: float = 0.7,
    ) -> list[tuple[Chunk, float]]:
        """Search the index for *query_text*.

        Returns a list of ``(chunk, similarity)`` tuples sorted by
        descending similarity, filtered by *similarity_threshold*.
        """
        if self._index is None or self._embedder is None:
            return []

        query_vec = self._embedder.embed([query_text])
        arr = np.array(query_vec, dtype=np.float32)

        k = min(top_k, len(self._chunks))
        if k == 0:
            return []

        distances, indices = self._index.search(arr, k)

        results: list[tuple[Chunk, float]] = []
        for dist, idx in zip(distances[0], indices[0], strict=True):
            if idx < 0 or idx >= len(self._chunks):
                continue
            # FAISS IndexFlatL2 returns squared L2 distance.
            # For normalized vectors: similarity = 1 - dist/2.
            similarity = max(0.0, 1.0 - float(dist) / 2.0)
            if similarity >= similarity_threshold:
                results.append((self._chunks[idx], round(similarity, 4)))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def save(self, index_dir: Path) -> None:
        """Persist the index to *index_dir*."""
        if self._index is None or self._metadata is None:
            msg = "No index to save - call build() first"
            raise ValueError(msg)

        index_dir.mkdir(parents=True, exist_ok=True)

        faiss.write_index(self._index, str(index_dir / "index.faiss"))

        chunks_data = [c.model_dump() for c in self._chunks]
        (index_dir / "chunks.json").write_text(
            json.dumps(chunks_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (index_dir / "metadata.json").write_text(
            json.dumps(self._metadata.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, index_dir: Path, embedder: Embedder | None = None) -> VectorIndex:
        """Load a previously saved index from *index_dir*."""
        if not FAISS_AVAILABLE:
            msg = "faiss-cpu is required to load a vector index"
            raise ImportError(msg)

        vi = cls(embedder=embedder)

        index_path = index_dir / "index.faiss"
        if not index_path.exists():
            msg = f"Index file not found: {index_path}"
            raise FileNotFoundError(msg)

        vi._index = faiss.read_index(str(index_path))

        chunks_path = index_dir / "chunks.json"
        if chunks_path.exists():
            raw = json.loads(chunks_path.read_text(encoding="utf-8"))
            vi._chunks = [Chunk.model_validate(c) for c in raw]

        meta_path = index_dir / "metadata.json"
        if meta_path.exists():
            raw_meta = json.loads(meta_path.read_text(encoding="utf-8"))
            vi._metadata = IndexMetadata.model_validate(raw_meta)

        return vi

    def is_valid(self) -> bool:
        """Check whether the loaded index has valid metadata."""
        return self._metadata is not None and self._metadata.schema_version == "1.0"


def _fingerprint(source_files: list[str]) -> str:
    """Compute a SHA-256 fingerprint of the sorted source file set."""
    content = "\n".join(sorted(source_files))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

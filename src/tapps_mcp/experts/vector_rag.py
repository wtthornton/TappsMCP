"""Vector RAG knowledge base with automatic FAISS fallback.

Provides the same interface as :class:`SimpleKnowledgeBase`.  When
``faiss-cpu`` is installed, uses semantic search via embeddings.  When
absent, transparently falls back to keyword-based
:class:`SimpleKnowledgeBase`.  Zero configuration required.
"""

from __future__ import annotations

import threading
from pathlib import Path

import structlog

from tapps_mcp.experts.models import KnowledgeChunk
from tapps_mcp.experts.rag import SimpleKnowledgeBase

logger = structlog.get_logger(__name__)


class VectorKnowledgeBase:
    """Knowledge base with optional vector search and automatic fallback.

    On first search, attempts to initialise the vector backend.  If FAISS
    or sentence-transformers are unavailable, silently delegates to
    :class:`SimpleKnowledgeBase`.
    """

    def __init__(
        self,
        knowledge_dir: Path,
        domain: str | None = None,
        *,
        chunk_size: int = 512,
        overlap: int = 50,
        embedding_model: str = "all-MiniLM-L6-v2",
        similarity_threshold: float = 0.7,
        index_dir: Path | None = None,
    ) -> None:
        self._knowledge_dir = knowledge_dir
        self._domain = domain
        self._chunk_size = chunk_size
        self._overlap = overlap
        self._embedding_model = embedding_model
        self._similarity_threshold = similarity_threshold
        self._index_dir = index_dir
        self._initialised = False
        self._init_lock = threading.Lock()
        self._backend_type = "pending"

        # Backends (set during _initialise).
        self._simple: SimpleKnowledgeBase | None = None
        self._vector_index: object | None = None  # VectorIndex when available

    @property
    def backend_type(self) -> str:
        """Return ``"vector"``, ``"simple"``, or ``"pending"``."""
        return self._backend_type

    # ------------------------------------------------------------------
    # Public API (same interface as SimpleKnowledgeBase)
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        max_results: int = 5,
        context_lines: int = 10,
    ) -> list[KnowledgeChunk]:
        """Search the knowledge base for *query*."""
        self._ensure_initialised()

        if self._backend_type == "vector" and self._vector_index is not None:
            return self._vector_search(query, max_results)

        if self._simple is not None:
            return self._simple.search(query, max_results, context_lines)

        return []

    def get_context(self, query: str, max_length: int = 2000) -> str:
        """Return formatted context for *query*."""
        self._ensure_initialised()

        if self._simple is not None:
            return self._simple.get_context(query, max_length)

        chunks = self.search(query)
        if not chunks:
            return "No relevant knowledge found in knowledge base."

        parts: list[str] = []
        length = 0
        for chunk in chunks:
            text = f"[From: {chunk.source_file}] (score: {chunk.score:.2f})\n{chunk.content}\n"
            if length + len(text) > max_length:
                break
            parts.append(text)
            length += len(text)

        return "\n---\n".join(parts) if parts else "No relevant knowledge found in knowledge base."

    def get_sources(self, query: str, max_results: int = 5) -> list[str]:
        """Return source file paths for *query*."""
        chunks = self.search(query, max_results)
        seen: set[str] = set()
        sources: list[str] = []
        for chunk in chunks:
            if chunk.source_file not in seen:
                seen.add(chunk.source_file)
                sources.append(chunk.source_file)
        return sources

    def list_files(self) -> list[str]:
        """Return all loaded knowledge file paths."""
        self._ensure_initialised()
        if self._simple is not None:
            return self._simple.list_files()
        return []

    # ------------------------------------------------------------------
    # Initialisation (lazy)
    # ------------------------------------------------------------------

    def _ensure_initialised(self) -> None:
        """Initialise the backend on first use (thread-safe)."""
        if self._initialised:
            return
        with self._init_lock:
            if self._initialised:
                return
            self._initialise()
            self._initialised = True

    def _initialise(self) -> None:
        """Try vector backend, fall back to simple."""
        # Always create the simple backend as fallback.
        self._simple = SimpleKnowledgeBase(self._knowledge_dir, self._domain)

        try:
            self._try_vector_backend()
        except (ImportError, OSError, RuntimeError, ValueError) as e:
            logger.debug(
                "vector_rag_fallback_to_simple",
                reason="FAISS or embedder unavailable",
                error=str(e),
            )
            self._backend_type = "simple"

    def _try_vector_backend(self) -> None:
        """Attempt to set up the FAISS vector backend."""
        from tapps_mcp.experts.rag_embedder import create_embedder

        embedder = create_embedder(self._embedding_model)
        if embedder is None:
            self._backend_type = "simple"
            return

        from tapps_mcp.experts.rag_chunker import Chunker
        from tapps_mcp.experts.rag_index import VectorIndex

        # Determine index directory.
        if self._index_dir is not None:
            idx_dir = self._index_dir
        else:
            domain_slug = self._domain or "general"
            idx_dir = self._knowledge_dir.parent / ".tapps-mcp" / "rag_index" / domain_slug

        # Try loading existing index.
        try:
            vi = VectorIndex.load(idx_dir, embedder)
            if vi.is_valid() and vi.chunk_count > 0:
                self._vector_index = vi
                self._backend_type = "vector"
                logger.info(
                    "vector_rag_loaded",
                    domain=self._domain,
                    chunks=vi.chunk_count,
                )
                return
        except (FileNotFoundError, ImportError):
            pass

        # Build new index from knowledge files.
        if not self._simple or self._simple.file_count == 0:
            self._backend_type = "simple"
            return

        chunker = Chunker(target_tokens=self._chunk_size, overlap_tokens=self._overlap)
        all_chunks = []
        for file_path, content in self._simple.files.items():
            all_chunks.extend(chunker.chunk_file(file_path, content))

        if not all_chunks:
            self._backend_type = "simple"
            return

        vi = VectorIndex(embedder)
        vi.build(all_chunks, {"chunk_size": self._chunk_size, "overlap": self._overlap})
        vi.save(idx_dir)

        self._vector_index = vi
        self._backend_type = "vector"
        logger.info(
            "vector_rag_built",
            domain=self._domain,
            chunks=len(all_chunks),
        )

    # ------------------------------------------------------------------
    # Vector search
    # ------------------------------------------------------------------

    def _vector_search(
        self,
        query: str,
        max_results: int,
    ) -> list[KnowledgeChunk]:
        """Search using the vector index and return KnowledgeChunk objects."""
        from tapps_mcp.experts.rag_index import VectorIndex  # noqa: TC001

        vi: VectorIndex = self._vector_index  # type: ignore[assignment]
        threshold = self._similarity_threshold
        results = vi.search(query, top_k=max_results, similarity_threshold=threshold)

        chunks: list[KnowledgeChunk] = []
        for chunk, similarity in results:
            # Convert source_file to relative path if possible.
            try:
                rel = str(Path(chunk.source_file).relative_to(self._knowledge_dir))
            except ValueError:
                rel = chunk.source_file

            chunks.append(
                KnowledgeChunk(
                    content=chunk.content,
                    source_file=rel,
                    line_start=chunk.line_start,
                    line_end=chunk.line_end,
                    score=similarity,
                )
            )

        return chunks

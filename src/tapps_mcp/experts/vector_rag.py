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
        *,
        relevance_threshold: float = 0.3,
    ) -> list[KnowledgeChunk]:
        """Search the knowledge base for *query*.

        When both vector and simple backends are available, performs hybrid
        retrieval: queries both, fuses results with weighted scoring, and
        returns the top-N after deduplication. Chunks below *relevance_threshold*
        are filtered out.
        """
        self._ensure_initialised()

        if self._backend_type == "vector" and self._vector_index is not None:
            vector_results = self._vector_search(query, max_results * 2)
            vector_filtered = [c for c in vector_results if c.score >= relevance_threshold]
            if self._simple is not None and self._simple.file_count > 0:
                keyword_results = self._simple.search(
                    query, max_results * 2, context_lines,
                    relevance_threshold=relevance_threshold,
                )
                fused = self._hybrid_fuse(
                    vector_filtered, keyword_results, max_results * 2
                )
                filtered = [c for c in fused if c.score >= relevance_threshold]
                return filtered[:max_results]
            return vector_filtered[:max_results]

        if self._simple is not None:
            return self._simple.search(
                query, max_results, context_lines,
                relevance_threshold=relevance_threshold,
            )

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
    # Hybrid fusion + rerank
    # ------------------------------------------------------------------

    @staticmethod
    def _hybrid_fuse(
        vector_results: list[KnowledgeChunk],
        keyword_results: list[KnowledgeChunk],
        max_results: int,
        *,
        vector_weight: float = 0.6,
        keyword_weight: float = 0.3,
        structural_weight: float = 0.1,
    ) -> list[KnowledgeChunk]:
        """Fuse vector and keyword results with weighted scoring and dedup.

        Each chunk gets a fusion score:
          fusion = vector_weight * vector_score + keyword_weight * keyword_score
                 + structural_weight * structural_boost

        Structural boost rewards chunks that appear in both result sets.
        """
        # Index keyword results by (source_file, line_start) for dedup.
        kw_index: dict[tuple[str, int], KnowledgeChunk] = {}
        for c in keyword_results:
            key = (c.source_file, c.line_start)
            if key not in kw_index or c.score > kw_index[key].score:
                kw_index[key] = c

        fused: dict[tuple[str, int], float] = {}
        chunk_map: dict[tuple[str, int], KnowledgeChunk] = {}
        source_map: dict[tuple[str, int], str] = {}  # track which backend(s)

        for c in vector_results:
            key = (c.source_file, c.line_start)
            fused[key] = vector_weight * c.score
            chunk_map[key] = c
            source_map[key] = "vector"

        for key, c in kw_index.items():
            kw_contribution = keyword_weight * c.score
            if key in fused:
                # Appears in both: add keyword score + structural bonus.
                fused[key] += kw_contribution + structural_weight
                source_map[key] = "hybrid"
            else:
                fused[key] = kw_contribution
                chunk_map[key] = c
                source_map[key] = "keyword"

        # Sort by fused score and take top-N.
        ranked = sorted(fused.items(), key=lambda x: x[1], reverse=True)[:max_results]

        results: list[KnowledgeChunk] = []
        for key, score in ranked:
            c = chunk_map[key]
            results.append(
                KnowledgeChunk(
                    content=c.content,
                    source_file=c.source_file,
                    line_start=c.line_start,
                    line_end=c.line_end,
                    score=round(min(score, 1.0), 4),
                )
            )

        return results

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

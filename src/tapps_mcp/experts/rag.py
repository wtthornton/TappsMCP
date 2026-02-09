"""Simple file-based RAG system for expert knowledge retrieval.

Provides keyword search over markdown files in a ``knowledge/`` directory.
No vector database required — uses TF-based scoring with markdown-aware
chunking, deduplication, and prioritisation.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import structlog

from tapps_mcp.experts.models import KnowledgeChunk

if TYPE_CHECKING:
    from pathlib import Path

logger = structlog.get_logger(__name__)

# Maximum file size for knowledge files (10 MB).
_MAX_RAG_FILE_SIZE = 10 * 1024 * 1024

# Words to ignore during keyword extraction.
_STOP_WORDS: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "as",
        "is",
        "was",
        "are",
        "were",
        "be",
        "been",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "should",
        "could",
        "may",
        "might",
        "must",
        "can",
        "this",
        "that",
        "these",
        "those",
        "you",
        "he",
        "she",
        "it",
        "we",
        "they",
        "what",
        "how",
        "why",
        "when",
        "where",
        "which",
        "who",
    }
)


class SimpleKnowledgeBase:
    """File-based knowledge base with keyword search.

    Features:
    - Recursive markdown-file loading.
    - Stop-word aware keyword extraction.
    - Markdown-aware chunk boundaries (headers).
    - Deduplication and length-based prioritisation.
    """

    def __init__(self, knowledge_dir: Path, domain: str | None = None) -> None:
        self.knowledge_dir = knowledge_dir
        self.domain = domain
        self.files: dict[Path, str] = {}
        self._load_files()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_files(self) -> None:
        """Load all ``*.md`` files from the knowledge directory."""
        if not self.knowledge_dir.exists():
            return

        for md_file in self.knowledge_dir.rglob("*.md"):
            if self.domain:
                domain_lower = self.domain.lower()
                if (
                    domain_lower not in md_file.stem.lower()
                    and domain_lower not in str(md_file).lower()
                ):
                    continue

            try:
                if md_file.stat().st_size > _MAX_RAG_FILE_SIZE:
                    logger.warning(
                        "knowledge_file_too_large",
                        file=str(md_file),
                        size=md_file.stat().st_size,
                    )
                    continue
                self.files[md_file] = md_file.read_text(encoding="utf-8")
            except Exception:
                logger.debug("knowledge_file_read_failed", file=str(md_file), exc_info=True)

    @property
    def file_count(self) -> int:
        """Number of loaded knowledge files."""
        return len(self.files)

    def list_files(self) -> list[str]:
        """Return relative paths of all loaded knowledge files."""
        result: list[str] = []
        for f in self.files:
            try:
                result.append(str(f.relative_to(self.knowledge_dir)))
            except ValueError:
                result.append(str(f))
        return result

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        max_results: int = 5,
        context_lines: int = 10,
    ) -> list[KnowledgeChunk]:
        """Search knowledge base for relevant chunks.

        Args:
            query: Search query (natural language or keywords).
            max_results: Maximum number of chunks to return.
            context_lines: Lines of context around keyword matches.

        Returns:
            List of :class:`KnowledgeChunk` sorted by relevance (desc).
        """
        keywords = _extract_keywords(query)
        if not keywords:
            return []

        chunks: list[KnowledgeChunk] = []
        for file_path, content in self.files.items():
            chunks.extend(self._extract_chunks(file_path, content, keywords, context_lines))

        chunks.sort(key=lambda c: c.score, reverse=True)
        return chunks[:max_results]

    def get_context(self, query: str, max_length: int = 2000) -> str:
        """Return a formatted context string for *query*.

        Chunks are deduplicated, prioritised, and concatenated up to
        *max_length* characters.
        """
        raw_chunks = self.search(query, max_results=10)
        if not raw_chunks:
            return "No relevant knowledge found in knowledge base."

        unique = _deduplicate(raw_chunks)
        prioritised = _prioritise(unique)

        parts: list[str] = []
        length = 0
        seen_sources: set[str] = set()

        for chunk in prioritised:
            source_key = chunk.source_file
            if source_key in seen_sources:
                continue

            text = f"[From: {chunk.source_file}] (score: {chunk.score:.2f})\n{chunk.content}\n"

            if length + len(text) > max_length:
                remaining = max_length - length
                _min_useful = 200
                if remaining > _min_useful:
                    parts.append(text[:remaining] + "...")
                break

            parts.append(text)
            length += len(text)
            seen_sources.add(source_key)

        return "\n---\n".join(parts) if parts else "No relevant knowledge found in knowledge base."

    def get_sources(self, query: str, max_results: int = 5) -> list[str]:
        """Return source-file relative paths for *query*."""
        chunks = self.search(query, max_results=max_results)
        seen: set[str] = set()
        sources: list[str] = []
        for chunk in chunks:
            if chunk.source_file not in seen:
                seen.add(chunk.source_file)
                sources.append(chunk.source_file)
        return sources

    # ------------------------------------------------------------------
    # Chunk extraction (private)
    # ------------------------------------------------------------------

    def _extract_chunks(
        self,
        file_path: Path,
        content: str,
        keywords: set[str],
        context_lines: int,
    ) -> list[KnowledgeChunk]:
        """Extract relevant chunks from a single file."""
        lines = content.split("\n")
        line_scores: dict[int, float] = {}

        for i, line in enumerate(lines):
            line_lower = line.lower()
            base = sum(1.0 for kw in keywords if kw in line_lower)
            if base == 0:
                continue

            # Boost headers.
            if line.strip().startswith("#"):
                level = len(line) - len(line.lstrip("#"))
                base *= 2.0 - level * 0.2

            # Boost code blocks.
            if line.strip().startswith("```"):
                base *= 1.4

            # Boost list items.
            stripped = line.strip()
            if stripped.startswith("- ") or stripped.startswith("* "):
                base *= 1.2

            line_scores[i] = base

        if not line_scores:
            return []

        # Group consecutive scoring lines into chunks.
        chunks: list[KnowledgeChunk] = []
        sorted_indices = sorted(line_scores)
        chunk_start = sorted_indices[0]
        chunk_end = sorted_indices[0]

        for idx in sorted_indices[1:]:
            if idx - chunk_end <= context_lines:
                chunk_end = idx
            else:
                chunk = self._build_chunk(
                    file_path,
                    lines,
                    chunk_start,
                    chunk_end,
                    context_lines,
                    keywords,
                )
                if chunk:
                    chunks.append(chunk)
                chunk_start = idx
                chunk_end = idx

        # Final group.
        chunk = self._build_chunk(file_path, lines, chunk_start, chunk_end, context_lines, keywords)
        if chunk:
            chunks.append(chunk)

        return chunks

    def _build_chunk(
        self,
        file_path: Path,
        lines: list[str],
        start: int,
        end: int,
        context_lines: int,
        keywords: set[str],
    ) -> KnowledgeChunk | None:
        actual_start = max(0, start - context_lines)
        actual_end = min(len(lines), end + context_lines + 1)

        # Align to nearest prior header.
        for i in range(actual_start, start):
            if lines[i].strip().startswith("#"):
                actual_start = i
                break

        text = "\n".join(lines[actual_start:actual_end]).strip()
        if not text:
            return None

        text_lower = text.lower()
        hits = sum(1.0 for kw in keywords if kw in text_lower)
        score = hits / len(keywords) if keywords else 0.0

        try:
            rel = str(file_path.relative_to(self.knowledge_dir))
        except ValueError:
            rel = str(file_path)

        return KnowledgeChunk(
            content=text,
            source_file=rel,
            line_start=actual_start + 1,
            line_end=actual_end,
            score=round(score, 4),
        )


# -----------------------------------------------------------------------
# Module-level helpers
# -----------------------------------------------------------------------


def _extract_keywords(query: str) -> set[str]:
    """Normalise *query* into a set of keywords."""
    clean = re.sub(r"[^\w\s-]", " ", query.lower())
    _min_keyword_len = 2
    return {w for w in clean.split() if len(w) > _min_keyword_len and w not in _STOP_WORDS}


def _deduplicate(
    chunks: list[KnowledgeChunk],
    threshold: float = 0.8,
) -> list[KnowledgeChunk]:
    """Remove chunks whose content overlaps above *threshold* (Jaccard)."""
    if not chunks:
        return chunks

    unique: list[KnowledgeChunk] = [chunks[0]]
    for chunk in chunks[1:]:
        c_words = set(chunk.content.lower().split())
        duplicate = False
        for existing in unique:
            e_words = set(existing.content.lower().split())
            if not c_words or not e_words:
                continue
            # Substring containment or Jaccard overlap.
            c_text = chunk.content.lower().strip()
            e_text = existing.content.lower().strip()
            if c_text in e_text or e_text in c_text:
                duplicate = True
                break
            jaccard = len(c_words & e_words) / len(c_words | e_words)
            if jaccard > threshold:
                duplicate = True
                break
        if not duplicate:
            unique.append(chunk)
    return unique


def _prioritise(chunks: list[KnowledgeChunk]) -> list[KnowledgeChunk]:
    """Sort *chunks* by score (desc) with a slight preference for shorter chunks."""

    def _key(c: KnowledgeChunk) -> tuple[float, float]:
        length_score = 1.0 / max(len(c.content) / 500, 1.0)
        return (-c.score, -length_score)

    return sorted(chunks, key=_key)

"""Ranked memory retrieval with composite scoring.

Upgrades memory search from simple keyword matching to scored,
ranked retrieval combining text relevance with memory-specific
signals (confidence, recency, access frequency).

Uses BM25 (Okapi) for text relevance scoring with automatic
index building and invalidation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, Field

from tapps_core.memory.bm25 import BM25Scorer
from tapps_core.memory.decay import DecayConfig, calculate_decayed_confidence, is_stale
from tapps_core.memory.models import MemoryEntry  # noqa: TC001

if TYPE_CHECKING:
    from tapps_core.memory.store import MemoryStore

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

_MAX_RESULTS = 50
_DEFAULT_RESULTS = 10
_MIN_CONFIDENCE_FLOOR = 0.1

# BM25 relevance normalization constant: score / (score + K)
# Chosen so that a BM25 score of 5.0 maps to ~0.5 normalized.
_BM25_NORM_K = 5.0


class ScoredMemory(BaseModel):
    """A memory entry with retrieval scoring metadata."""

    entry: MemoryEntry
    score: float = Field(ge=0.0, description="Composite retrieval score.")
    effective_confidence: float = Field(
        ge=0.0, le=1.0, description="Time-decayed confidence."
    )
    bm25_relevance: float = Field(ge=0.0, description="Normalized text relevance.")
    stale: bool = Field(default=False, description="Whether the memory is stale.")


# ---------------------------------------------------------------------------
# Scoring weights
# ---------------------------------------------------------------------------

_W_RELEVANCE = 0.40
_W_CONFIDENCE = 0.30
_W_RECENCY = 0.15
_W_FREQUENCY = 0.15

_FREQUENCY_CAP = 20.0

# Marker text for consolidated source entries
_CONSOLIDATED_MARKER = "consolidated into"


def _is_consolidated_source(entry: MemoryEntry) -> bool:
    """Check if an entry is a source of a consolidated entry.

    Source entries are marked with contradicted=True and a
    contradiction_reason containing "consolidated into".

    Args:
        entry: The memory entry to check.

    Returns:
        True if this entry was consolidated into another entry.
    """
    if not entry.contradicted:
        return False
    reason = entry.contradiction_reason or ""
    return _CONSOLIDATED_MARKER in reason.lower()


# ---------------------------------------------------------------------------
# MemoryRetriever
# ---------------------------------------------------------------------------


class MemoryRetriever:
    """Ranked retrieval engine for memory entries."""

    def __init__(self, config: DecayConfig | None = None) -> None:
        self._config = config or DecayConfig()
        self._bm25 = BM25Scorer()
        self._bm25_entries: list[MemoryEntry] = []
        self._bm25_corpus_size: int = 0
        self._bm25_fingerprint: int = 0

    def search(
        self,
        query: str,
        store: MemoryStore,
        *,
        limit: int = _DEFAULT_RESULTS,
        include_contradicted: bool = False,
        include_sources: bool = False,
        min_confidence: float = _MIN_CONFIDENCE_FLOOR,
    ) -> list[ScoredMemory]:
        """Search memories with ranked scoring.

        Uses the store's FTS5-backed search for candidate retrieval,
        then applies composite scoring with confidence, recency, and
        frequency signals.

        Args:
            query: Search query string.
            store: Memory store to search.
            limit: Max results (default 10, max 50).
            include_contradicted: Include contradicted memories.
            include_sources: Include source entries of consolidated memories
                (Epic 58, Story 58.5). When False (default), entries that were
                consolidated into other entries are filtered out. When True,
                source entries are included alongside consolidated entries.
            min_confidence: Minimum confidence filter.

        Returns:
            Scored memories sorted by composite score (descending).
        """
        if not query or not query.strip():
            return []

        limit = max(1, min(limit, _MAX_RESULTS))
        now = datetime.now(tz=UTC)

        # Get candidates via store search (FTS5-backed) + fallback
        candidates = self._get_candidates(query, store)

        # Score and filter
        scored: list[ScoredMemory] = []
        for entry, relevance_raw in candidates:
            # Filter source entries of consolidated memories (Epic 58.5)
            if not include_sources and _is_consolidated_source(entry):
                continue

            # Filter contradicted entries (sources already handled above)
            is_included_source = include_sources and _is_consolidated_source(entry)
            if entry.contradicted and not include_contradicted and not is_included_source:
                continue

            # Calculate effective confidence
            eff_conf = calculate_decayed_confidence(entry, self._config, now=now)

            # Filter low confidence
            if eff_conf < min_confidence:
                continue

            stale_flag = is_stale(entry, self._config, now=now)

            # Compute composite score
            relevance_norm = self._normalize_relevance(relevance_raw)
            recency = self._recency_score(entry, now)
            frequency = self._frequency_score(entry)

            composite = (
                _W_RELEVANCE * relevance_norm
                + _W_CONFIDENCE * eff_conf
                + _W_RECENCY * recency
                + _W_FREQUENCY * frequency
            )

            # Bonus for exact key match
            if entry.key == query.lower().replace(" ", "-"):
                composite += 0.1

            scored.append(
                ScoredMemory(
                    entry=entry,
                    score=round(composite, 4),
                    effective_confidence=round(eff_conf, 4),
                    bm25_relevance=round(relevance_norm, 4),
                    stale=stale_flag,
                )
            )

        # Sort by score descending
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:limit]

    # -----------------------------------------------------------------------
    # BM25 index management
    # -----------------------------------------------------------------------

    @staticmethod
    def _entry_to_document(entry: MemoryEntry) -> str:
        """Convert a memory entry to a BM25-indexable document string."""
        return f"{entry.key} {entry.value} {' '.join(entry.tags)}"

    @staticmethod
    def _corpus_fingerprint(entries: list[MemoryEntry]) -> int:
        """Compute a fingerprint that changes when any entry is added, removed, or updated."""
        return hash(tuple((e.key, e.updated_at if e.updated_at else "") for e in entries))

    def _ensure_bm25_index(self, entries: list[MemoryEntry]) -> None:
        """Build or rebuild the BM25 index when the corpus changes."""
        fingerprint = self._corpus_fingerprint(entries)
        if len(entries) == self._bm25_corpus_size and fingerprint == self._bm25_fingerprint:
            return
        documents = [self._entry_to_document(e) for e in entries]
        self._bm25.build_index(documents)
        self._bm25_entries = list(entries)
        self._bm25_corpus_size = len(entries)
        self._bm25_fingerprint = fingerprint
        logger.debug("bm25_index_rebuilt", corpus_size=self._bm25_corpus_size)

    # -----------------------------------------------------------------------
    # Candidate retrieval
    # -----------------------------------------------------------------------

    def _get_candidates(
        self,
        query: str,
        store: MemoryStore,
    ) -> list[tuple[MemoryEntry, float]]:
        """Retrieve candidate entries and compute BM25 relevance scores.

        Tries the store's FTS5-backed search first for candidate
        filtering, then scores them using BM25. Falls back to full
        in-memory BM25 scan if FTS5 returns no results, and to word
        overlap if BM25 scoring fails entirely.
        """
        # Try FTS5 via store.search() for candidate filtering
        try:
            fts_results = store.search(query)
            if fts_results:
                return self._bm25_score_entries(query, fts_results, store)
        except Exception:
            logger.debug("fts5_search_failed", query=query)

        # Fallback: full corpus BM25 scan
        return self._bm25_full_scan(query, store)

    def _bm25_score_entries(
        self,
        query: str,
        entries: list[MemoryEntry],
        store: MemoryStore,
    ) -> list[tuple[MemoryEntry, float]]:
        """Score a set of entries using BM25.

        Builds the BM25 index over the full corpus (for proper IDF),
        then looks up scores for the given entries.
        """
        try:
            all_entries = store.list_all()
            self._ensure_bm25_index(all_entries)

            # Build a lookup: entry key -> index in corpus
            key_to_idx = {e.key: i for i, e in enumerate(self._bm25_entries)}
            all_scores = self._bm25.score(query)

            results: list[tuple[MemoryEntry, float]] = []
            for entry in entries:
                idx = key_to_idx.get(entry.key)
                if idx is not None and idx < len(all_scores):
                    results.append((entry, all_scores[idx]))
                else:
                    # Entry not in index (new entry?), use word overlap
                    results.append(
                        (entry, self._word_overlap_score(query, entry))
                    )
            return results
        except Exception:
            logger.debug("bm25_scoring_failed_using_word_overlap", query=query)
            return [
                (entry, self._word_overlap_score(query, entry))
                for entry in entries
            ]

    def _bm25_full_scan(
        self,
        query: str,
        store: MemoryStore,
    ) -> list[tuple[MemoryEntry, float]]:
        """Full corpus BM25 scan as fallback.

        Falls back to word overlap if BM25 fails.
        """
        all_entries = store.list_all()
        if not all_entries:
            return []

        try:
            self._ensure_bm25_index(all_entries)
            scores = self._bm25.score(query)
            return [
                (entry, score)
                for entry, score in zip(all_entries, scores)
                if score > 0
            ]
        except Exception:
            logger.debug("bm25_full_scan_failed_using_word_overlap", query=query)
            return self._like_search(query, store)

    def _like_search(
        self,
        query: str,
        store: MemoryStore,
    ) -> list[tuple[MemoryEntry, float]]:
        """Fallback LIKE-based search with simple word overlap scoring."""
        query_words = set(query.lower().split())
        if not query_words:
            return []

        all_entries = store.list_all()
        results: list[tuple[MemoryEntry, float]] = []

        for entry in all_entries:
            relevance = self._word_overlap_score(query, entry)
            if relevance > 0:
                results.append((entry, relevance))

        return results

    # -----------------------------------------------------------------------
    # Scoring helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _word_overlap_score(query: str, entry: MemoryEntry) -> float:
        """Compute word overlap between query and entry text."""
        query_words = set(query.lower().split())
        if not query_words:
            return 0.0
        entry_text = f"{entry.key} {entry.value} {' '.join(entry.tags)}".lower()
        entry_words = set(entry_text.split())
        overlap = len(query_words & entry_words)
        return overlap / len(query_words)

    @staticmethod
    def _normalize_relevance(raw_score: float) -> float:
        """Normalize relevance score to 0.0-1.0 range.

        Uses sigmoid normalization: ``score / (score + K)`` where
        K=5.0, tuned for BM25 scores (typical range 0-15+).
        A BM25 score of 5.0 maps to 0.5 normalized.
        """
        if raw_score <= 0:
            return 0.0
        return raw_score / (raw_score + _BM25_NORM_K)

    @staticmethod
    def _recency_score(entry: MemoryEntry, now: datetime) -> float:
        """Compute recency score: ``1.0 / (1.0 + days_since_updated)``."""
        try:
            updated = datetime.fromisoformat(entry.updated_at)
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=UTC)
        except (ValueError, TypeError):
            return 0.5
        days = max((now - updated).total_seconds() / 86400.0, 0.0)
        return 1.0 / (1.0 + days)

    @staticmethod
    def _frequency_score(entry: MemoryEntry) -> float:
        """Compute access frequency score: ``min(1.0, access_count / 20)``."""
        return min(1.0, entry.access_count / _FREQUENCY_CAP)

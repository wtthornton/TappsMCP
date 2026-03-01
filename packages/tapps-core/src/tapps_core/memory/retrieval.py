"""Ranked memory retrieval with composite scoring.

Upgrades memory search from simple keyword matching to scored,
ranked retrieval combining text relevance with memory-specific
signals (confidence, recency, access frequency).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, Field

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


# ---------------------------------------------------------------------------
# MemoryRetriever
# ---------------------------------------------------------------------------


class MemoryRetriever:
    """Ranked retrieval engine for memory entries."""

    def __init__(self, config: DecayConfig | None = None) -> None:
        self._config = config or DecayConfig()

    def search(
        self,
        query: str,
        store: MemoryStore,
        *,
        limit: int = _DEFAULT_RESULTS,
        include_contradicted: bool = False,
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
            # Filter contradicted
            if entry.contradicted and not include_contradicted:
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
    # Candidate retrieval
    # -----------------------------------------------------------------------

    def _get_candidates(
        self,
        query: str,
        store: MemoryStore,
    ) -> list[tuple[MemoryEntry, float]]:
        """Retrieve candidate entries and compute relevance scores.

        Tries the store's FTS5-backed search first. If that returns
        results, computes word overlap for relevance scoring. Falls
        back to full in-memory scan if FTS5 search returns no results.
        """
        # Try FTS5 via store.search()
        try:
            fts_results = store.search(query)
            if fts_results:
                return [
                    (entry, self._word_overlap_score(query, entry))
                    for entry in fts_results
                ]
        except Exception:
            logger.debug("fts5_search_failed", query=query)

        # Fallback: in-memory word overlap search
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

        Uses a sigmoid-like normalization: ``score / (score + 1)``.
        """
        if raw_score <= 0:
            return 0.0
        return raw_score / (raw_score + 1.0)

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

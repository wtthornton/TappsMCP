"""Tests for ranked memory retrieval (Epic 25, Story 25.1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from tapps_mcp.memory.decay import DecayConfig
from tapps_mcp.memory.models import (
    MemoryEntry,
    MemoryScope,
    MemorySource,
    MemoryTier,
)
from tapps_mcp.memory.retrieval import MemoryRetriever, ScoredMemory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 2, 27, 12, 0, 0, tzinfo=UTC)
_RECENT = (_NOW - timedelta(days=1)).isoformat()
_OLD = (_NOW - timedelta(days=90)).isoformat()
_VERY_OLD = (_NOW - timedelta(days=365)).isoformat()


def _make_entry(
    key: str = "test-key",
    value: str = "test value",
    *,
    tier: MemoryTier = MemoryTier.pattern,
    confidence: float = 0.8,
    source: MemorySource = MemorySource.agent,
    updated_at: str = "",
    access_count: int = 0,
    contradicted: bool = False,
    tags: list[str] | None = None,
) -> MemoryEntry:
    return MemoryEntry(
        key=key,
        value=value,
        tier=tier,
        confidence=confidence,
        source=source,
        source_agent="test",
        scope=MemoryScope.project,
        tags=tags or [],
        updated_at=updated_at or _RECENT,
        created_at=updated_at or _RECENT,
        last_accessed=updated_at or _RECENT,
        access_count=access_count,
        contradicted=contradicted,
    )


def _make_store(entries: list[MemoryEntry] | None = None) -> MagicMock:
    """Create a mock MemoryStore with search and list_all."""
    store = MagicMock()
    entries = entries or []

    store.list_all.return_value = entries
    # store.search returns the same entries (simulating FTS match)
    store.search.return_value = entries

    entry_map = {e.key: e for e in entries}
    store.get.side_effect = lambda k, **kwargs: entry_map.get(k)

    return store


# ---------------------------------------------------------------------------
# ScoredMemory model tests
# ---------------------------------------------------------------------------


class TestScoredMemory:
    def test_scored_memory_creation(self) -> None:
        entry = _make_entry()
        scored = ScoredMemory(
            entry=entry,
            score=0.75,
            effective_confidence=0.8,
            bm25_relevance=0.5,
            stale=False,
        )
        assert scored.score == 0.75
        assert scored.entry.key == "test-key"


# ---------------------------------------------------------------------------
# MemoryRetriever tests
# ---------------------------------------------------------------------------


class TestMemoryRetriever:
    def test_empty_query_returns_empty(self) -> None:
        retriever = MemoryRetriever()
        store = _make_store([_make_entry()])
        assert retriever.search("", store) == []
        assert retriever.search("   ", store) == []

    def test_no_matching_entries(self) -> None:
        retriever = MemoryRetriever()
        entries = [_make_entry("unrelated-key", "no match here")]
        store = _make_store(entries)
        # store.search returns empty for non-matching query
        store.search.return_value = []

        results = retriever.search("completely different query", store)
        assert len(results) == 0

    def test_exact_key_match_ranks_highest(self) -> None:
        entries = [
            _make_entry("jwt-auth", "JWT authentication config", confidence=0.7),
            _make_entry("auth-setup", "Authentication setup details", confidence=0.7),
        ]
        retriever = MemoryRetriever()
        store = _make_store(entries)

        results = retriever.search("jwt-auth", store)
        assert len(results) >= 1
        assert results[0].entry.key == "jwt-auth"

    def test_high_confidence_outranks_low(self) -> None:
        entries = [
            _make_entry(
                "low-conf",
                "test framework value",
                confidence=0.3,
                updated_at=_RECENT,
            ),
            _make_entry(
                "high-conf",
                "test framework value",
                confidence=0.9,
                updated_at=_RECENT,
            ),
        ]
        retriever = MemoryRetriever()
        store = _make_store(entries)

        results = retriever.search("test framework", store)
        assert len(results) == 2
        assert results[0].entry.key == "high-conf"

    def test_recent_memory_outranks_old(self) -> None:
        entries = [
            _make_entry(
                "old-memory",
                "database config setup",
                confidence=0.8,
                updated_at=_OLD,
            ),
            _make_entry(
                "new-memory",
                "database config setup",
                confidence=0.8,
                updated_at=_RECENT,
            ),
        ]
        retriever = MemoryRetriever()
        store = _make_store(entries)

        results = retriever.search("database config", store)
        assert len(results) == 2
        assert results[0].entry.key == "new-memory"

    def test_contradicted_excluded_by_default(self) -> None:
        entries = [
            _make_entry("good-key", "valid memory", contradicted=False),
            _make_entry("bad-key", "contradicted memory", contradicted=True),
        ]
        retriever = MemoryRetriever()
        store = _make_store(entries)

        results = retriever.search("memory", store)
        keys = [r.entry.key for r in results]
        assert "bad-key" not in keys

    def test_contradicted_included_when_requested(self) -> None:
        entries = [
            _make_entry("bad-key", "contradicted memory", contradicted=True),
        ]
        retriever = MemoryRetriever()
        store = _make_store(entries)

        results = retriever.search("contradicted memory", store, include_contradicted=True)
        assert len(results) == 1
        assert results[0].entry.key == "bad-key"

    def test_result_limit_respected(self) -> None:
        entries = [
            _make_entry(f"key-{i}", f"matching value {i}") for i in range(20)
        ]
        retriever = MemoryRetriever()
        store = _make_store(entries)

        results = retriever.search("matching value", store, limit=5)
        assert len(results) <= 5

    def test_max_limit_capped(self) -> None:
        entries = [
            _make_entry(f"key-{i}", f"value {i}") for i in range(60)
        ]
        retriever = MemoryRetriever()
        store = _make_store(entries)

        results = retriever.search("value", store, limit=100)
        assert len(results) <= 50

    def test_low_confidence_filtered(self) -> None:
        entries = [
            _make_entry(
                "very-low",
                "matching text",
                confidence=0.05,
                updated_at=_VERY_OLD,
            ),
        ]
        retriever = MemoryRetriever(config=DecayConfig())
        store = _make_store(entries)

        # Confidence floor is 0.1, so entry decays to 0.1.
        # Use min_confidence > 0.1 to filter it out.
        results = retriever.search("matching text", store, min_confidence=0.2)
        assert len(results) == 0

    def test_frequency_affects_ranking(self) -> None:
        entries = [
            _make_entry(
                "rarely-accessed",
                "shared pattern data",
                access_count=1,
                confidence=0.8,
            ),
            _make_entry(
                "often-accessed",
                "shared pattern data",
                access_count=20,
                confidence=0.8,
            ),
        ]
        retriever = MemoryRetriever()
        store = _make_store(entries)

        results = retriever.search("shared pattern", store)
        assert len(results) == 2
        assert results[0].entry.key == "often-accessed"

    def test_fallback_to_like_search(self) -> None:
        """When FTS5 search returns no results, fallback to LIKE."""
        entries = [_make_entry("my-key", "some matching content")]
        retriever = MemoryRetriever()
        store = _make_store(entries)
        # store.search raises exception = FTS5 unavailable
        store.search.side_effect = Exception("FTS5 not available")

        results = retriever.search("matching content", store)
        assert len(results) == 1

    def test_word_overlap_scoring(self) -> None:
        entry = _make_entry("test-key", "python fastapi web framework")
        score = MemoryRetriever._word_overlap_score("python fastapi", entry)
        assert score > 0.0


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


class TestScoringHelpers:
    def _retriever(self) -> MemoryRetriever:
        return MemoryRetriever()

    def test_normalize_relevance_zero(self) -> None:
        assert self._retriever()._normalize_relevance(0.0) == 0.0

    def test_normalize_relevance_positive(self) -> None:
        # BM25 normalization: score / (score + 5.0)
        score = self._retriever()._normalize_relevance(5.0)
        assert 0.0 < score < 1.0
        assert score == pytest.approx(0.5)

    def test_normalize_relevance_large(self) -> None:
        score = self._retriever()._normalize_relevance(100.0)
        assert score > 0.9

    def test_recency_score_recent(self) -> None:
        entry = _make_entry(updated_at=_NOW.isoformat())
        score = MemoryRetriever._recency_score(entry, _NOW)
        assert score == pytest.approx(1.0, abs=0.01)

    def test_recency_score_old(self) -> None:
        entry = _make_entry(updated_at=_OLD)
        score = MemoryRetriever._recency_score(entry, _NOW)
        assert score < 0.1

    def test_frequency_score_zero(self) -> None:
        entry = _make_entry(access_count=0)
        assert self._retriever()._frequency_score(entry) == 0.0

    def test_frequency_score_capped(self) -> None:
        entry = _make_entry(access_count=100)
        assert self._retriever()._frequency_score(entry) == 1.0

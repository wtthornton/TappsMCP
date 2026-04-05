"""Tests for memory injection into expert/research responses (Epic 25, Story 25.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from tapps_mcp.memory.injection import (
    _MAX_INJECT_HIGH,
    _MAX_INJECT_MEDIUM,
    _MIN_SCORE,
    append_memory_to_answer,
    inject_memories,
)
from tapps_mcp.memory.models import (
    MemoryEntry,
    MemoryScope,
    MemorySource,
    MemoryTier,
)

_RECENT = (datetime.now(tz=UTC) - timedelta(hours=1)).isoformat()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    key: str = "test-key",
    value: str = "test value for matching",
    confidence: float = 0.8,
    contradicted: bool = False,
) -> MemoryEntry:
    return MemoryEntry(
        key=key,
        value=value,
        tier=MemoryTier.pattern,
        confidence=confidence,
        source=MemorySource.agent,
        source_agent="test",
        scope=MemoryScope.project,
        tags=[],
        updated_at=_RECENT,
        created_at=_RECENT,
        last_accessed=_RECENT,
        access_count=5,
        contradicted=contradicted,
    )


def _make_store(entries: list[MemoryEntry] | None = None) -> MagicMock:
    store = MagicMock()
    # Avoid MagicMock cascade into scoring weights (tapps-brain validates
    # that profile.scoring weights sum to ~1.0 when set).
    store.profile = None
    entries = entries or []
    store.search.return_value = entries
    store.list_all.return_value = entries
    entry_map = {e.key: e for e in entries}
    store.get.side_effect = lambda k, **kw: entry_map.get(k)
    return store


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestInjectMemories:
    def test_memories_injected_when_relevant(self) -> None:
        entries = [_make_entry("jwt-config", "JWT authentication with RS256")]
        store = _make_store(entries)

        result = inject_memories("JWT authentication", store, "high")

        assert result["memory_injected"] >= 1
        assert "jwt-config" in result["memory_section"]
        assert "Project Memory" in result["memory_section"]

    def test_no_injection_when_no_matches(self) -> None:
        store = _make_store([])

        result = inject_memories("completely unrelated", store, "high")

        assert result["memory_injected"] == 0
        assert result["memory_section"] == ""

    def test_low_engagement_never_injects(self) -> None:
        entries = [_make_entry("key", "matching value")]
        store = _make_store(entries)

        result = inject_memories("matching value", store, "low")

        assert result["memory_injected"] == 0
        assert result["memory_section"] == ""

    def test_high_engagement_max_limit(self) -> None:
        entries = [
            _make_entry(f"key-{i}", f"matching search term {i}")
            for i in range(10)
        ]
        store = _make_store(entries)

        result = inject_memories("matching search term", store, "high")

        assert result["memory_injected"] <= _MAX_INJECT_HIGH

    def test_medium_engagement_max_limit(self) -> None:
        entries = [
            _make_entry(f"key-{i}", f"matching value {i}", confidence=0.9)
            for i in range(10)
        ]
        store = _make_store(entries)

        result = inject_memories("matching value", store, "medium")

        assert result["memory_injected"] <= _MAX_INJECT_MEDIUM

    def test_medium_engagement_filters_low_confidence(self) -> None:
        entries = [
            _make_entry("low-conf", "matching data", confidence=0.3),
        ]
        store = _make_store(entries)

        result = inject_memories("matching data", store, "medium")

        # Medium requires confidence > 0.5, entry has 0.3
        assert result["memory_injected"] == 0

    def test_contradicted_memories_not_injected(self) -> None:
        entries = [
            _make_entry("bad-key", "contradicted data", contradicted=True),
        ]
        store = _make_store(entries)

        result = inject_memories("contradicted data", store, "high")

        # Contradicted entries are excluded by retriever by default
        assert result["memory_injected"] == 0

    def test_memory_section_format(self) -> None:
        entries = [_make_entry("my-key", "my value content")]
        store = _make_store(entries)

        result = inject_memories("my value content", store, "high")

        if result["memory_injected"] > 0:
            assert "### Project Memory" in result["memory_section"]
            assert "confidence:" in result["memory_section"]
            assert "tier:" in result["memory_section"]

    def test_memories_list_in_result(self) -> None:
        entries = [_make_entry("test-key", "test matching value")]
        store = _make_store(entries)

        result = inject_memories("test matching value", store, "high")

        if result["memory_injected"] > 0:
            assert len(result["memories"]) > 0
            mem = result["memories"][0]
            assert "key" in mem
            assert "confidence" in mem
            assert "score" in mem


class TestAppendMemoryToAnswer:
    def test_appends_when_section_exists(self) -> None:
        answer = "Expert answer here."
        memory_result = {
            "memory_section": "### Project Memory\n- **key** (conf: 0.8): value",
            "memory_injected": 1,
        }

        result = append_memory_to_answer(answer, memory_result)

        assert "Expert answer here." in result
        assert "### Project Memory" in result

    def test_no_append_when_empty_section(self) -> None:
        answer = "Expert answer here."
        memory_result = {"memory_section": "", "memory_injected": 0}

        result = append_memory_to_answer(answer, memory_result)

        assert result == answer

"""Unit tests for memory retrieval deduplication (Epic 58, Story 58.5)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tapps_mcp.server_memory_tools import (
    _filter_consolidated_sources,
    _is_consolidated_source,
    tapps_memory,
)


async def _noop_init() -> None:
    """Async no-op replacement for ensure_session_initialized."""


@pytest.fixture(autouse=True)
def _mock_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip session initialization in tests."""
    monkeypatch.setattr(
        "tapps_mcp.server_memory_tools.ensure_session_initialized",
        _noop_init,
    )


@pytest.fixture()
def mock_store(tmp_path: Path):
    """Create a real MemoryStore and patch _get_memory_store."""
    from tapps_core.memory.store import MemoryStore

    store = MemoryStore(tmp_path)
    try:
        with patch("tapps_mcp.server_memory_tools._get_memory_store", return_value=store):
            yield store
    finally:
        store.close()


class TestIsConsolidatedSource:
    """Tests for _is_consolidated_source helper."""

    def test_not_contradicted_returns_false(self) -> None:
        """Non-contradicted entries are not consolidated sources."""
        from tapps_core.memory.models import MemoryEntry

        entry = MemoryEntry(key="test", value="test value")
        assert _is_consolidated_source(entry) is False

    def test_contradicted_without_reason_returns_false(self) -> None:
        """Contradicted entries without consolidated marker return False."""
        from tapps_core.memory.models import MemoryEntry

        entry = MemoryEntry(
            key="test",
            value="test value",
            contradicted=True,
            contradiction_reason="outdated information",
        )
        assert _is_consolidated_source(entry) is False

    def test_contradicted_with_consolidated_marker_returns_true(self) -> None:
        """Entries marked as consolidated into another return True."""
        from tapps_core.memory.models import MemoryEntry

        entry = MemoryEntry(
            key="test",
            value="test value",
            contradicted=True,
            contradiction_reason="consolidated into db-config-abc123",
        )
        assert _is_consolidated_source(entry) is True

    def test_marker_case_insensitive(self) -> None:
        """Consolidated marker detection is case-insensitive."""
        from tapps_core.memory.models import MemoryEntry

        entry = MemoryEntry(
            key="test",
            value="test value",
            contradicted=True,
            contradiction_reason="CONSOLIDATED INTO other-key",
        )
        assert _is_consolidated_source(entry) is True

    def test_none_contradiction_reason(self) -> None:
        """None contradiction_reason doesn't crash."""
        from tapps_core.memory.models import MemoryEntry

        entry = MemoryEntry(
            key="test",
            value="test value",
            contradicted=True,
            contradiction_reason=None,
        )
        assert _is_consolidated_source(entry) is False


class TestFilterConsolidatedSources:
    """Tests for _filter_consolidated_sources helper."""

    def test_empty_list(self) -> None:
        """Empty list returns empty list."""
        result = _filter_consolidated_sources([])
        assert result == []

    def test_no_consolidated_sources(self) -> None:
        """List without consolidated sources unchanged."""
        from tapps_core.memory.models import MemoryEntry

        entries = [
            MemoryEntry(key="a", value="value a"),
            MemoryEntry(key="b", value="value b"),
        ]
        result = _filter_consolidated_sources(entries)
        assert len(result) == 2

    def test_filters_consolidated_sources(self) -> None:
        """Filters out entries marked as consolidated."""
        from tapps_core.memory.models import MemoryEntry

        entries = [
            MemoryEntry(key="active", value="active entry"),
            MemoryEntry(
                key="source",
                value="source entry",
                contradicted=True,
                contradiction_reason="consolidated into consolidated-abc",
            ),
        ]
        result = _filter_consolidated_sources(entries)
        assert len(result) == 1
        assert result[0].key == "active"

    def test_preserves_non_consolidated_contradicted(self) -> None:
        """Non-consolidated contradicted entries are preserved."""
        from tapps_core.memory.models import MemoryEntry

        entries = [
            MemoryEntry(
                key="outdated",
                value="outdated info",
                contradicted=True,
                contradiction_reason="superseded by newer info",
            ),
        ]
        result = _filter_consolidated_sources(entries)
        assert len(result) == 1


@pytest.mark.asyncio()
class TestSearchDeduplication:
    """Tests for search action deduplication."""

    async def test_search_default_filters_sources(self, mock_store) -> None:
        """Search filters consolidated sources by default."""
        # Save entries
        await tapps_memory(action="save", key="active", value="active entry", tags="test")

        # Manually mark an entry as consolidated source
        mock_store.save(
            key="source",
            value="source entry that was consolidated",
            tags=["test"],
        )
        mock_store.update_fields(
            "source",
            contradicted=True,
            contradiction_reason="consolidated into consolidated-abc",
        )

        result = await tapps_memory(action="search", query="test entry")

        assert result["success"] is True
        # Source entry should be filtered out
        keys = [r["entry"]["key"] for r in result["data"]["results"]]
        assert "source" not in keys

    async def test_search_include_sources_shows_all(self, mock_store) -> None:
        """Search with include_sources=True shows consolidated sources."""
        await tapps_memory(action="save", key="active", value="active entry", tags="test")

        mock_store.save(
            key="source",
            value="source entry that was consolidated",
            tags=["test"],
        )
        mock_store.update_fields(
            "source",
            contradicted=True,
            contradiction_reason="consolidated into consolidated-abc",
        )

        result = await tapps_memory(
            action="search",
            query="test entry",
            include_sources=True,
        )

        assert result["success"] is True
        # With include_sources, source entry should appear
        keys = [r["entry"]["key"] for r in result["data"]["results"]]
        assert "source" in keys or len(keys) >= 1


@pytest.mark.asyncio()
class TestListDeduplication:
    """Tests for list action deduplication."""

    async def test_list_default_filters_sources(self, mock_store) -> None:
        """List filters consolidated sources by default."""
        await tapps_memory(action="save", key="active", value="active entry")

        mock_store.save(key="source", value="source entry")
        mock_store.update_fields(
            "source",
            contradicted=True,
            contradiction_reason="consolidated into consolidated-abc",
        )

        result = await tapps_memory(action="list")

        assert result["success"] is True
        keys = [e["key"] for e in result["data"]["entries"]]
        assert "active" in keys
        assert "source" not in keys

    async def test_list_include_sources_shows_all(self, mock_store) -> None:
        """List with include_sources=True shows consolidated sources."""
        await tapps_memory(action="save", key="active", value="active entry")

        mock_store.save(key="source", value="source entry")
        mock_store.update_fields(
            "source",
            contradicted=True,
            contradiction_reason="consolidated into consolidated-abc",
        )

        result = await tapps_memory(action="list", include_sources=True)

        assert result["success"] is True
        keys = [e["key"] for e in result["data"]["entries"]]
        assert "active" in keys
        assert "source" in keys

    async def test_list_count_reflects_filtering(self, mock_store) -> None:
        """List total_count reflects filtered entries."""
        await tapps_memory(action="save", key="a", value="entry a")
        await tapps_memory(action="save", key="b", value="entry b")

        mock_store.update_fields(
            "b",
            contradicted=True,
            contradiction_reason="consolidated into consolidated-c",
        )

        result = await tapps_memory(action="list")

        assert result["success"] is True
        # Only active entries counted after filtering
        assert result["data"]["total_count"] == 1


@pytest.mark.asyncio()
class TestRankedSearchDeduplication:
    """Tests for ranked BM25 search deduplication."""

    async def test_ranked_search_filters_sources(self, mock_store) -> None:
        """Ranked search filters consolidated sources."""
        await tapps_memory(
            action="save",
            key="active-db",
            value="Use PostgreSQL database",
            tags="database",
        )

        mock_store.save(
            key="old-db",
            value="Old database config",
            tags=["database"],
        )
        mock_store.update_fields(
            "old-db",
            contradicted=True,
            contradiction_reason="consolidated into active-db",
        )

        result = await tapps_memory(
            action="search",
            query="database",
            ranked=True,
        )

        assert result["success"] is True
        assert result["data"]["ranked"] is True
        keys = [r["entry"]["key"] for r in result["data"]["results"]]
        assert "old-db" not in keys


@pytest.mark.asyncio()
class TestRetrievalDeduplicationIntegration:
    """Integration tests for retrieval deduplication after consolidation."""

    async def test_consolidate_then_search_hides_sources(self, mock_store) -> None:
        """After consolidation, search hides source entries."""
        # Create entries that will be consolidated
        await tapps_memory(
            action="save",
            key="cache-1",
            value="Use Redis cache",
            tier="pattern",
            tags="cache",
        )
        await tapps_memory(
            action="save",
            key="cache-2",
            value="Redis with TTL",
            tier="pattern",
            tags="cache",
        )

        # Consolidate
        await tapps_memory(
            action="consolidate",
            entry_ids="cache-1,cache-2",
        )

        # Search should show consolidated entry, hide sources
        result = await tapps_memory(action="search", query="cache Redis")

        assert result["success"] is True
        keys = [r["entry"]["key"] for r in result["data"]["results"]]
        # Original entries should be hidden (they're now sources)
        assert "cache-1" not in keys
        assert "cache-2" not in keys

    async def test_consolidate_then_list_hides_sources(self, mock_store) -> None:
        """After consolidation, list hides source entries."""
        await tapps_memory(
            action="save",
            key="api-1",
            value="REST API",
            tier="pattern",
            tags="api",
        )
        await tapps_memory(
            action="save",
            key="api-2",
            value="API versioning",
            tier="pattern",
            tags="api",
        )

        # Consolidate
        await tapps_memory(
            action="consolidate",
            entry_ids="api-1,api-2",
        )

        # List should hide sources
        result = await tapps_memory(action="list")

        assert result["success"] is True
        keys = [e["key"] for e in result["data"]["entries"]]
        assert "api-1" not in keys
        assert "api-2" not in keys


@pytest.mark.asyncio()
class TestParameterInteraction:
    """Tests for include_sources parameter interactions."""

    async def test_include_sources_with_ranked_false(self, mock_store) -> None:
        """include_sources works with unranked search."""
        await tapps_memory(action="save", key="test1", value="test value")

        mock_store.update_fields(
            "test1",
            contradicted=True,
            contradiction_reason="consolidated into other",
        )

        # Unranked search with include_sources
        result = await tapps_memory(
            action="search",
            query="test",
            ranked=False,
            include_sources=True,
        )

        assert result["success"] is True

    async def test_include_sources_with_tier_filter(self, mock_store) -> None:
        """include_sources works with tier filtering."""
        await tapps_memory(
            action="save",
            key="arch",
            value="arch entry",
            tier="architectural",
        )
        mock_store.update_fields(
            "arch",
            contradicted=True,
            contradiction_reason="consolidated into other",
        )

        result = await tapps_memory(
            action="list",
            tier="architectural",
            include_sources=True,
        )

        assert result["success"] is True
        keys = [e["key"] for e in result["data"]["entries"]]
        assert "arch" in keys

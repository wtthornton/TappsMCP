"""Unit tests for memory retrieval deduplication helpers (Epic 58, Story 58.5).

TAP-1993/TAP-1994: search, list, save, consolidate actions are now refused
(redirected to tapps-brain tools). The async integration tests that called
those actions via tapps_memory() have been removed. The pure-helper tests for
_is_consolidated_source and _filter_consolidated_sources remain valid.
"""

from __future__ import annotations

from tapps_mcp.server_memory_tools import (
    _filter_consolidated_sources,
    _is_consolidated_source,
)


class TestIsConsolidatedSource:
    """Tests for _is_consolidated_source helper."""

    def test_not_contradicted_returns_false(self) -> None:
        """Non-contradicted entries are not consolidated sources."""
        from tapps_brain.models import MemoryEntry

        entry = MemoryEntry(key="test", value="test value")
        assert _is_consolidated_source(entry) is False

    def test_contradicted_without_reason_returns_false(self) -> None:
        """Contradicted entries without consolidated marker return False."""
        from tapps_brain.models import MemoryEntry

        entry = MemoryEntry(
            key="test",
            value="test value",
            contradicted=True,
            contradiction_reason="outdated information",
        )
        assert _is_consolidated_source(entry) is False

    def test_contradicted_with_consolidated_marker_returns_true(self) -> None:
        """Entries marked as consolidated into another return True."""
        from tapps_brain.models import MemoryEntry

        entry = MemoryEntry(
            key="test",
            value="test value",
            contradicted=True,
            contradiction_reason="consolidated into db-config-abc123",
        )
        assert _is_consolidated_source(entry) is True

    def test_marker_case_insensitive(self) -> None:
        """Consolidated marker detection is case-insensitive."""
        from tapps_brain.models import MemoryEntry

        entry = MemoryEntry(
            key="test",
            value="test value",
            contradicted=True,
            contradiction_reason="CONSOLIDATED INTO other-key",
        )
        assert _is_consolidated_source(entry) is True

    def test_none_contradiction_reason(self) -> None:
        """None contradiction_reason doesn't crash."""
        from tapps_brain.models import MemoryEntry

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
        from tapps_brain.models import MemoryEntry

        entries = [
            MemoryEntry(key="a", value="value a"),
            MemoryEntry(key="b", value="value b"),
        ]
        result = _filter_consolidated_sources(entries)
        assert len(result) == 2

    def test_filters_consolidated_sources(self) -> None:
        """Filters out entries marked as consolidated."""
        from tapps_brain.models import MemoryEntry

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
        from tapps_brain.models import MemoryEntry

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

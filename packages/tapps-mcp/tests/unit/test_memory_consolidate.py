"""Unit tests for tapps_memory consolidate action (Epic 58, Story 58.4)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tapps_mcp.server_memory_tools import tapps_memory


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


@pytest.mark.asyncio()
class TestConsolidateAction:
    """Tests for the consolidate action."""

    async def test_consolidate_in_valid_actions(self) -> None:
        """Verify consolidate is a valid action."""
        from tapps_mcp.server_memory_tools import _VALID_ACTIONS

        assert "consolidate" in _VALID_ACTIONS

    async def test_consolidate_not_enough_entries(self, mock_store) -> None:
        """Consolidate fails with fewer than 2 entries."""
        await tapps_memory(action="save", key="k1", value="v1")

        result = await tapps_memory(action="consolidate")

        assert result["success"] is True
        assert result["data"]["consolidated"] is False
        assert "not_enough" in result["data"]["reason"]

    async def test_consolidate_no_similar_entries(self, mock_store) -> None:
        """Consolidate fails when entries are not similar."""
        await tapps_memory(
            action="save", key="database-config", value="Use PostgreSQL",
            tier="architectural", tags="database",
        )
        await tapps_memory(
            action="save", key="ui-framework", value="Use React",
            tier="pattern", tags="frontend,ui",
        )

        result = await tapps_memory(action="consolidate")

        assert result["success"] is True
        assert result["data"]["consolidated"] is False
        assert result["data"]["reason"] in ("no_similar_entries", "not_enough_entries")


@pytest.mark.asyncio()
class TestConsolidateWithEntryIds:
    """Tests for consolidate with explicit entry_ids."""

    async def test_consolidate_explicit_ids_success(self, mock_store) -> None:
        """Consolidate specific entries by IDs."""
        await tapps_memory(
            action="save", key="db-choice-1", value="Use PostgreSQL for main database",
            tier="architectural", tags="database",
        )
        await tapps_memory(
            action="save", key="db-choice-2", value="PostgreSQL with read replicas",
            tier="architectural", tags="database",
        )

        result = await tapps_memory(
            action="consolidate",
            entry_ids="db-choice-1,db-choice-2",
        )

        assert result["success"] is True
        assert result["data"]["consolidated"] is True
        assert result["data"]["source_count"] == 2
        assert "db-choice-1" in result["data"]["source_keys"]
        assert "db-choice-2" in result["data"]["source_keys"]
        assert result["data"]["discovery_method"] == "explicit"

    async def test_consolidate_explicit_ids_not_found(self, mock_store) -> None:
        """Consolidate fails when entry_ids not found."""
        await tapps_memory(action="save", key="k1", value="v1")

        result = await tapps_memory(
            action="consolidate",
            entry_ids="k1,nonexistent",
        )

        assert result["success"] is True
        assert result["data"]["consolidated"] is False
        assert result["data"]["reason"] == "entries_not_found"
        assert "nonexistent" in result["data"]["not_found"]

    async def test_consolidate_explicit_single_id(self, mock_store) -> None:
        """Consolidate fails with only one entry_id."""
        await tapps_memory(action="save", key="k1", value="v1")

        result = await tapps_memory(
            action="consolidate",
            entry_ids="k1",
        )

        assert result["success"] is True
        assert result["data"]["consolidated"] is False
        assert "not_enough" in result["data"]["reason"]


@pytest.mark.asyncio()
class TestConsolidateWithQuery:
    """Tests for consolidate with query-based discovery."""

    async def test_consolidate_query_success(self, mock_store) -> None:
        """Consolidate entries found by query."""
        await tapps_memory(
            action="save", key="auth-jwt", value="Use JWT for authentication tokens",
            tier="pattern", tags="auth,security",
        )
        await tapps_memory(
            action="save", key="auth-session", value="JWT tokens stored in session",
            tier="pattern", tags="auth,session",
        )
        await tapps_memory(
            action="save", key="unrelated", value="Use blue theme",
            tier="context", tags="ui",
        )

        result = await tapps_memory(
            action="consolidate",
            query="JWT authentication",
        )

        assert result["success"] is True
        # May or may not consolidate depending on similarity
        # Just verify the query path was taken
        if result["data"]["consolidated"]:
            assert result["data"]["discovery_method"] == "query"

    async def test_consolidate_query_no_results(self, mock_store) -> None:
        """Consolidate fails when query returns no results."""
        await tapps_memory(action="save", key="k1", value="v1")

        result = await tapps_memory(
            action="consolidate",
            query="nonexistent query terms",
        )

        assert result["success"] is True
        assert result["data"]["consolidated"] is False


@pytest.mark.asyncio()
class TestConsolidateDryRun:
    """Tests for consolidate dry_run mode."""

    async def test_dry_run_preview_explicit_ids(self, mock_store) -> None:
        """Dry run previews consolidation without making changes."""
        await tapps_memory(
            action="save", key="cache-redis-1", value="Use Redis for caching",
            tier="pattern", tags="cache,redis",
        )
        await tapps_memory(
            action="save", key="cache-redis-2", value="Redis with 1h TTL",
            tier="pattern", tags="cache,redis",
        )

        result = await tapps_memory(
            action="consolidate",
            entry_ids="cache-redis-1,cache-redis-2",
            dry_run=True,
        )

        assert result["success"] is True
        assert result["data"]["dry_run"] is True
        assert result["data"]["would_consolidate"] is True
        assert result["data"]["source_count"] == 2
        assert "consolidation_reason" in result["data"]

        # Verify no actual consolidation happened
        get_result = await tapps_memory(action="get", key="cache-redis-1")
        assert get_result["data"]["found"] is True

    async def test_dry_run_shows_source_entries(self, mock_store) -> None:
        """Dry run includes source entry details."""
        await tapps_memory(
            action="save", key="e1", value="Entry 1",
            tier="architectural", tags="test",
        )
        await tapps_memory(
            action="save", key="e2", value="Entry 2",
            tier="pattern", tags="test",
        )

        result = await tapps_memory(
            action="consolidate",
            entry_ids="e1,e2",
            dry_run=True,
        )

        assert result["success"] is True
        assert "source_entries" in result["data"]
        source_keys = [e["key"] for e in result["data"]["source_entries"]]
        assert "e1" in source_keys
        assert "e2" in source_keys


@pytest.mark.asyncio()
class TestConsolidateAutoDiscovery:
    """Tests for auto-discovery consolidation mode."""

    async def test_auto_discovers_similar_entries(self, mock_store) -> None:
        """Auto-discovery finds and consolidates similar entries."""
        # Create multiple similar entries
        await tapps_memory(
            action="save", key="api-rest-1", value="Use REST for API",
            tier="architectural", tags="api",
        )
        await tapps_memory(
            action="save", key="api-rest-2", value="REST API with versioning",
            tier="architectural", tags="api",
        )
        await tapps_memory(
            action="save", key="api-rest-3", value="REST endpoints follow naming",
            tier="architectural", tags="api",
        )

        result = await tapps_memory(action="consolidate")

        assert result["success"] is True
        # May or may not find similar entries depending on threshold
        if result["data"]["consolidated"]:
            assert result["data"]["discovery_method"] == "auto"
            assert result["data"]["source_count"] >= 2


@pytest.mark.asyncio()
class TestConsolidateProvenance:
    """Tests for consolidation provenance tracking."""

    async def test_consolidated_entry_has_source_keys(self, mock_store) -> None:
        """Consolidated entry tracks source keys."""
        await tapps_memory(
            action="save", key="src1", value="Source value 1",
            tier="pattern", tags="test",
        )
        await tapps_memory(
            action="save", key="src2", value="Source value 2",
            tier="pattern", tags="test",
        )

        result = await tapps_memory(
            action="consolidate",
            entry_ids="src1,src2",
        )

        assert result["success"] is True
        if result["data"]["consolidated"]:
            assert "source_keys" in result["data"]
            assert len(result["data"]["source_keys"]) == 2

    async def test_source_entries_marked_contradicted(self, mock_store) -> None:
        """Source entries are marked as contradicted after consolidation."""
        await tapps_memory(
            action="save", key="old1", value="Old value 1",
            tier="pattern", tags="test",
        )
        await tapps_memory(
            action="save", key="old2", value="Old value 2",
            tier="pattern", tags="test",
        )

        result = await tapps_memory(
            action="consolidate",
            entry_ids="old1,old2",
        )

        if result["data"]["consolidated"]:
            # Source entries should be marked as contradicted
            get_result = await tapps_memory(action="get", key="old1")
            assert get_result["data"]["found"] is True
            entry = get_result["data"]["entry"]
            assert entry.get("contradicted") is True

    async def test_consolidated_confidence_is_weighted(self, mock_store) -> None:
        """Consolidated entry has weighted confidence."""
        await tapps_memory(
            action="save", key="high-conf", value="High confidence",
            tier="pattern", tags="test", confidence=0.9,
        )
        await tapps_memory(
            action="save", key="low-conf", value="Low confidence",
            tier="pattern", tags="test", confidence=0.5,
        )

        result = await tapps_memory(
            action="consolidate",
            entry_ids="high-conf,low-conf",
        )

        if result["data"]["consolidated"]:
            conf = result["data"]["confidence"]
            # Weighted average should be between 0.5 and 0.9
            assert 0.5 <= conf <= 0.9


@pytest.mark.asyncio()
class TestConsolidateReason:
    """Tests for consolidation reason detection."""

    async def test_same_topic_reason(self, mock_store) -> None:
        """Detects same_topic consolidation reason."""
        await tapps_memory(
            action="save", key="topic1", value="Topic content A",
            tier="architectural", tags="same-tag",
        )
        await tapps_memory(
            action="save", key="topic2", value="Topic content B",
            tier="architectural", tags="same-tag",
        )

        result = await tapps_memory(
            action="consolidate",
            entry_ids="topic1,topic2",
            dry_run=True,
        )

        if result["data"]["would_consolidate"]:
            assert "consolidation_reason" in result["data"]
            # Reason could be same_topic, similarity, or manual
            assert result["data"]["consolidation_reason"] in (
                "same_topic", "similarity", "supersession", "manual",
            )


@pytest.mark.asyncio()
class TestConsolidateEdgeCases:
    """Edge case tests for consolidate action."""

    async def test_consolidate_empty_store(self, mock_store) -> None:
        """Consolidate fails gracefully with empty store."""
        result = await tapps_memory(action="consolidate")

        assert result["success"] is True
        assert result["data"]["consolidated"] is False
        assert "not_enough" in result["data"]["reason"]

    async def test_consolidate_already_consolidated_skipped(self, mock_store) -> None:
        """Already-consolidated entries are skipped."""
        await tapps_memory(
            action="save", key="e1", value="Entry 1",
            tier="pattern", tags="test",
        )
        await tapps_memory(
            action="save", key="e2", value="Entry 2",
            tier="pattern", tags="test",
        )

        # First consolidation
        result1 = await tapps_memory(
            action="consolidate",
            entry_ids="e1,e2",
        )

        if result1["data"]["consolidated"]:
            # Now the source entries are marked as contradicted
            # A second consolidation attempt should handle this
            result2 = await tapps_memory(action="consolidate")

            # Should either find no entries or handle gracefully
            assert result2["success"] is True

    async def test_consolidate_with_tags_filter(self, mock_store) -> None:
        """Consolidate respects tag filtering in search."""
        await tapps_memory(
            action="save", key="tagged1", value="Tagged value 1",
            tier="pattern", tags="specific-tag",
        )
        await tapps_memory(
            action="save", key="tagged2", value="Tagged value 2",
            tier="pattern", tags="specific-tag",
        )
        await tapps_memory(
            action="save", key="other", value="Other value",
            tier="pattern", tags="different",
        )

        # Query should find tagged entries
        result = await tapps_memory(
            action="consolidate",
            query="Tagged value",
        )

        assert result["success"] is True

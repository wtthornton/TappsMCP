"""Unit tests for tapps_memory unconsolidate action (Epic 58, Story 58.6)."""

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _consolidate_two(key1: str = "src1", key2: str = "src2") -> dict:
    """Save two entries and consolidate them. Return consolidation result."""
    await tapps_memory(
        action="save", key=key1, value=f"Value for {key1}",
        tier="pattern", tags="test",
    )
    await tapps_memory(
        action="save", key=key2, value=f"Value for {key2}",
        tier="pattern", tags="test",
    )
    return await tapps_memory(
        action="consolidate",
        entry_ids=f"{key1},{key2}",
    )


# ---------------------------------------------------------------------------
# Unconsolidate action validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
class TestUnconsolidateValidation:
    """Basic validation tests for the unconsolidate action."""

    async def test_unconsolidate_in_valid_actions(self) -> None:
        """Verify unconsolidate is a valid action."""
        from tapps_mcp.server_memory_tools import _VALID_ACTIONS

        assert "unconsolidate" in _VALID_ACTIONS

    async def test_unconsolidate_in_dispatch(self) -> None:
        """Verify unconsolidate is in the dispatch table."""
        from tapps_mcp.server_memory_tools import _DISPATCH

        assert "unconsolidate" in _DISPATCH

    async def test_unconsolidate_missing_key(self, mock_store) -> None:
        """Unconsolidate requires a key."""
        result = await tapps_memory(action="unconsolidate")

        assert result["success"] is True
        assert result["data"]["error"] == "missing_key"

    async def test_unconsolidate_entry_not_found(self, mock_store) -> None:
        """Unconsolidate fails when entry doesn't exist."""
        result = await tapps_memory(action="unconsolidate", key="nonexistent")

        assert result["success"] is True
        assert result["data"]["undone"] is False
        assert result["data"]["reason"] == "entry_not_found"

    async def test_unconsolidate_not_consolidated(self, mock_store) -> None:
        """Unconsolidate fails for a non-consolidated entry."""
        await tapps_memory(action="save", key="plain-entry", value="Not consolidated")

        result = await tapps_memory(action="unconsolidate", key="plain-entry")

        assert result["success"] is True
        assert result["data"]["undone"] is False
        assert result["data"]["reason"] == "not_a_consolidated_entry"


# ---------------------------------------------------------------------------
# Unconsolidate success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
class TestUnconsolidateSuccess:
    """Tests for successful unconsolidation."""

    async def test_unconsolidate_restores_sources(self, mock_store) -> None:
        """Unconsolidate restores source entries."""
        cons_result = await _consolidate_two("src-a", "src-b")
        assert cons_result["data"]["consolidated"] is True
        cons_key = cons_result["data"]["consolidated_key"]

        # Source entries should be contradicted
        get_a = await tapps_memory(action="get", key="src-a")
        assert get_a["data"]["entry"]["contradicted"] is True

        # Unconsolidate
        result = await tapps_memory(action="unconsolidate", key=cons_key)

        assert result["success"] is True
        assert result["data"]["undone"] is True
        assert result["data"]["consolidated_entry_deleted"] is True
        assert len(result["data"]["restored_keys"]) == 2
        assert "src-a" in result["data"]["restored_keys"]
        assert "src-b" in result["data"]["restored_keys"]

    async def test_unconsolidate_clears_contradicted_flag(self, mock_store) -> None:
        """Source entries have contradicted=False after unconsolidation."""
        cons_result = await _consolidate_two("e1", "e2")
        assert cons_result["data"]["consolidated"] is True
        cons_key = cons_result["data"]["consolidated_key"]

        await tapps_memory(action="unconsolidate", key=cons_key)

        # Source entries should be restored
        get_e1 = await tapps_memory(action="get", key="e1")
        assert get_e1["data"]["found"] is True
        assert get_e1["data"]["entry"]["contradicted"] is False
        assert get_e1["data"]["entry"]["contradiction_reason"] is None

        get_e2 = await tapps_memory(action="get", key="e2")
        assert get_e2["data"]["found"] is True
        assert get_e2["data"]["entry"]["contradicted"] is False

    async def test_unconsolidate_deletes_consolidated_entry(self, mock_store) -> None:
        """The consolidated entry is deleted after unconsolidation."""
        cons_result = await _consolidate_two("d1", "d2")
        assert cons_result["data"]["consolidated"] is True
        cons_key = cons_result["data"]["consolidated_key"]

        await tapps_memory(action="unconsolidate", key=cons_key)

        # Consolidated entry should be gone
        get_cons = await tapps_memory(action="get", key=cons_key)
        assert get_cons["data"]["found"] is False

    async def test_unconsolidate_response_includes_metadata(self, mock_store) -> None:
        """Unconsolidate response includes store metadata."""
        cons_result = await _consolidate_two("m1", "m2")
        assert cons_result["data"]["consolidated"] is True
        cons_key = cons_result["data"]["consolidated_key"]

        result = await tapps_memory(action="unconsolidate", key=cons_key)

        assert "store_metadata" in result["data"]
        assert "total_count" in result["data"]["store_metadata"]


# ---------------------------------------------------------------------------
# Provenance view
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
class TestProvenance:
    """Tests for provenance view in get action."""

    async def test_get_consolidated_entry_has_provenance(self, mock_store) -> None:
        """Getting a consolidated entry includes provenance info."""
        cons_result = await _consolidate_two("prov-a", "prov-b")
        assert cons_result["data"]["consolidated"] is True
        cons_key = cons_result["data"]["consolidated_key"]

        get_result = await tapps_memory(action="get", key=cons_key)

        assert get_result["data"]["found"] is True
        assert "provenance" in get_result["data"]
        prov = get_result["data"]["provenance"]
        assert prov["is_consolidated"] is True
        assert prov["source_count"] == 2
        assert "prov-a" in prov["source_keys"]
        assert "prov-b" in prov["source_keys"]

    async def test_get_consolidated_provenance_includes_source_details(self, mock_store) -> None:
        """Provenance includes source entry details."""
        cons_result = await _consolidate_two("det-a", "det-b")
        assert cons_result["data"]["consolidated"] is True
        cons_key = cons_result["data"]["consolidated_key"]

        get_result = await tapps_memory(action="get", key=cons_key)

        prov = get_result["data"]["provenance"]
        assert "sources" in prov
        assert len(prov["sources"]) == 2
        source_keys = [s["key"] for s in prov["sources"]]
        assert "det-a" in source_keys
        assert "det-b" in source_keys
        # Each source has value and tier
        for source in prov["sources"]:
            assert "value" in source
            assert "tier" in source

    async def test_get_regular_entry_no_provenance(self, mock_store) -> None:
        """Getting a regular entry does not include provenance."""
        await tapps_memory(action="save", key="regular", value="Not consolidated")

        get_result = await tapps_memory(action="get", key="regular")

        assert get_result["data"]["found"] is True
        assert "provenance" not in get_result["data"]

    async def test_provenance_gone_after_unconsolidate(self, mock_store) -> None:
        """Provenance disappears after unconsolidation."""
        cons_result = await _consolidate_two("gone-a", "gone-b")
        assert cons_result["data"]["consolidated"] is True
        cons_key = cons_result["data"]["consolidated_key"]

        # Provenance should exist before unconsolidate
        get_before = await tapps_memory(action="get", key=cons_key)
        assert "provenance" in get_before["data"]

        # Unconsolidate
        await tapps_memory(action="unconsolidate", key=cons_key)

        # Consolidated entry is deleted, so no provenance
        get_after = await tapps_memory(action="get", key=cons_key)
        assert get_after["data"]["found"] is False

"""Unit tests for tapps_memory save_bulk action (Epic 55, Story 1)."""

from __future__ import annotations

import json
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
    with patch("tapps_mcp.server_memory_tools._get_memory_store", return_value=store):
        yield store


@pytest.mark.asyncio()
class TestSaveBulk:
    """Tests for the save_bulk action."""

    async def test_save_bulk_success(self, mock_store) -> None:
        entries = [
            {"key": "k1", "value": "v1"},
            {"key": "k2", "value": "v2"},
            {"key": "k3", "value": "v3"},
        ]
        result = await tapps_memory(
            action="save_bulk",
            entries=json.dumps(entries),
        )
        assert result["success"] is True
        data = result["data"]
        assert data["action"] == "save_bulk"
        assert data["saved"] == 3
        assert data["skipped"] == 0
        assert data["errors"] == []

    async def test_save_bulk_partial_error(self, mock_store) -> None:
        entries = [
            {"key": "k1", "value": "v1"},
            {"key": "", "value": "v2"},  # missing key
            {"key": "k3", "value": "v3"},
        ]
        result = await tapps_memory(
            action="save_bulk",
            entries=json.dumps(entries),
        )
        assert result["success"] is True
        data = result["data"]
        assert data["saved"] == 2
        assert data["skipped"] == 1
        assert len(data["errors"]) == 1

    async def test_save_bulk_cap_exceeded(self, mock_store) -> None:
        entries = [{"key": f"k{i}", "value": f"v{i}"} for i in range(51)]
        result = await tapps_memory(
            action="save_bulk",
            entries=json.dumps(entries),
        )
        assert result["success"] is True
        data = result["data"]
        assert data["error"] == "too_many_entries"

    async def test_save_bulk_invalid_json(self, mock_store) -> None:
        result = await tapps_memory(
            action="save_bulk",
            entries="not valid json [",
        )
        assert result["success"] is True
        data = result["data"]
        assert data["error"] == "invalid_json"

    async def test_save_bulk_empty_array(self, mock_store) -> None:
        result = await tapps_memory(
            action="save_bulk",
            entries="[]",
        )
        assert result["success"] is True
        data = result["data"]
        assert data["saved"] == 0
        assert data["skipped"] == 0
        assert data["errors"] == []

    async def test_save_bulk_inherits_defaults(self, mock_store) -> None:
        entries = [
            {"key": "k1", "value": "v1"},
            {"key": "k2", "value": "v2", "tier": "architectural"},
        ]
        result = await tapps_memory(
            action="save_bulk",
            entries=json.dumps(entries),
            tier="context",
            source="human",
            source_agent="test-agent",
            scope="project",
        )
        assert result["success"] is True
        assert result["data"]["saved"] == 2

        # Verify: k1 inherited tier="context", k2 overrode to "architectural"
        e1 = mock_store.get("k1")
        assert e1 is not None
        tier1 = e1.tier if isinstance(e1.tier, str) else e1.tier.value
        assert tier1 == "context"

        e2 = mock_store.get("k2")
        assert e2 is not None
        tier2 = e2.tier if isinstance(e2.tier, str) else e2.tier.value
        assert tier2 == "architectural"

    async def test_save_bulk_missing_entries_param(self, mock_store) -> None:
        result = await tapps_memory(action="save_bulk")
        assert result["success"] is True
        assert result["data"]["error"] == "missing_entries"

    async def test_save_bulk_non_array_json(self, mock_store) -> None:
        result = await tapps_memory(
            action="save_bulk",
            entries='{"key": "val"}',
        )
        assert result["success"] is True
        assert result["data"]["error"] == "invalid_format"

    async def test_save_bulk_missing_value(self, mock_store) -> None:
        entries = [{"key": "k1"}]
        result = await tapps_memory(
            action="save_bulk",
            entries=json.dumps(entries),
        )
        assert result["success"] is True
        data = result["data"]
        assert data["saved"] == 0
        assert data["skipped"] == 1
        assert len(data["errors"]) == 1
        assert "value" in data["errors"][0]["error"].lower()

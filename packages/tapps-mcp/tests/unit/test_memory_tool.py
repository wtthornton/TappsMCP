"""Unit tests for tapps_memory MCP tool handler (Epic 23, Story 4)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

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
def mock_store(tmp_path: Path) -> MagicMock:
    """Create a mock MemoryStore and patch _get_memory_store."""
    from tapps_mcp.memory.store import MemoryStore

    store = MemoryStore(tmp_path)
    with patch("tapps_mcp.server_memory_tools._get_memory_store", return_value=store):
        yield store  # type: ignore[misc]


@pytest.mark.asyncio()
class TestTappsMemoryTool:
    """Tests for the tapps_memory MCP tool handler."""

    async def test_invalid_action(self) -> None:
        result = await tapps_memory(action="invalid")
        assert result["success"] is False
        assert "invalid_action" in result["error"]["code"]

    async def test_save_action(self, mock_store: MagicMock) -> None:
        result = await tapps_memory(
            action="save",
            key="test-key",
            value="Test value",
            tier="pattern",
            source="agent",
        )
        assert result["success"] is True
        assert result["data"]["action"] == "save"
        assert result["data"]["entry"]["key"] == "test-key"

    async def test_save_missing_key(self, mock_store: MagicMock) -> None:
        result = await tapps_memory(action="save", value="some value")
        assert result["success"] is True  # returns success with error in data
        assert result["data"].get("error") == "missing_key"

    async def test_save_missing_value(self, mock_store: MagicMock) -> None:
        result = await tapps_memory(action="save", key="k1")
        assert result["success"] is True
        assert result["data"].get("error") == "missing_value"

    async def test_get_action_found(self, mock_store: MagicMock) -> None:
        await tapps_memory(action="save", key="k1", value="v1")
        result = await tapps_memory(action="get", key="k1")
        assert result["success"] is True
        assert result["data"]["found"] is True
        assert result["data"]["entry"]["key"] == "k1"

    async def test_get_action_not_found(self, mock_store: MagicMock) -> None:
        result = await tapps_memory(action="get", key="nonexistent")
        assert result["success"] is True
        assert result["data"]["found"] is False

    async def test_list_action(self, mock_store: MagicMock) -> None:
        await tapps_memory(action="save", key="k1", value="v1")
        await tapps_memory(action="save", key="k2", value="v2")
        result = await tapps_memory(action="list")
        assert result["success"] is True
        assert result["data"]["count"] == 2

    async def test_delete_action(self, mock_store: MagicMock) -> None:
        await tapps_memory(action="save", key="k1", value="v1")
        result = await tapps_memory(action="delete", key="k1")
        assert result["success"] is True
        assert result["data"]["deleted"] is True

    async def test_search_action(self, mock_store: MagicMock) -> None:
        await tapps_memory(action="save", key="arch-decision", value="Use SQLite for storage")
        result = await tapps_memory(action="search", query="SQLite")
        assert result["success"] is True
        assert result["data"]["count"] >= 1

    async def test_search_missing_query_and_tags(self, mock_store: MagicMock) -> None:
        result = await tapps_memory(action="search")
        assert result["success"] is True
        assert result["data"].get("error") == "missing_query"

    async def test_store_metadata_in_response(self, mock_store: MagicMock) -> None:
        await tapps_memory(action="save", key="k1", value="v1")
        result = await tapps_memory(action="get", key="k1")
        assert "store_metadata" in result["data"]
        assert "total_count" in result["data"]["store_metadata"]

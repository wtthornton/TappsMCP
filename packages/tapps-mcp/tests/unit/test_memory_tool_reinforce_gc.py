"""Unit tests for tapps_memory reinforce and gc actions (Epic 34.3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
def mock_store(tmp_path: Path):  # noqa: ANN201
    """Create a real MemoryStore backed by tmp_path and patch _get_memory_store."""
    from tapps_core.memory.store import MemoryStore

    store = MemoryStore(tmp_path)
    with patch("tapps_mcp.server_memory_tools._get_memory_store", return_value=store):
        yield store


@pytest.mark.asyncio()
class TestReinforceAction:
    """Tests for the reinforce action."""

    async def test_reinforce_success(self, mock_store: object) -> None:
        """Reinforce returns success with updated confidence info."""
        await tapps_memory(action="save", key="test-key", value="Test value")
        result = await tapps_memory(action="reinforce", key="test-key")
        assert result["success"] is True
        assert result["data"]["action"] == "reinforce"
        assert result["data"]["found"] is True
        assert "old_confidence" in result["data"]
        assert "new_confidence" in result["data"]
        assert "reinforce_count" in result["data"]

    async def test_reinforce_missing_key(self, mock_store: object) -> None:
        """Reinforce without key returns missing_key error."""
        result = await tapps_memory(action="reinforce")
        assert result["success"] is True
        assert result["data"]["error"] == "missing_key"

    async def test_reinforce_key_not_found(self, mock_store: object) -> None:
        """Reinforce with nonexistent key returns found=False."""
        result = await tapps_memory(action="reinforce", key="nonexistent")
        assert result["success"] is True
        assert result["data"]["found"] is False
        assert result["data"]["key"] == "nonexistent"

    async def test_reinforce_increments_count(self, mock_store: object) -> None:
        """Reinforce increments the reinforce_count."""
        await tapps_memory(action="save", key="counter-key", value="Track count")
        r1 = await tapps_memory(action="reinforce", key="counter-key")
        assert r1["data"]["reinforce_count"] == 1

        r2 = await tapps_memory(action="reinforce", key="counter-key")
        assert r2["data"]["reinforce_count"] == 2

    async def test_reinforce_resets_decay_clock(self, mock_store: object) -> None:
        """Reinforce sets last_reinforced on the entry."""
        await tapps_memory(action="save", key="decay-key", value="Decay test")
        result = await tapps_memory(action="reinforce", key="decay-key")
        entry = result["data"]["entry"]
        assert entry["last_reinforced"] is not None

    async def test_reinforce_has_store_metadata(self, mock_store: object) -> None:
        """Reinforce response includes store metadata."""
        await tapps_memory(action="save", key="meta-key", value="Metadata test")
        result = await tapps_memory(action="reinforce", key="meta-key")
        assert "store_metadata" in result["data"]
        assert "total_count" in result["data"]["store_metadata"]


@pytest.mark.asyncio()
class TestGCAction:
    """Tests for the gc (garbage collection) action."""

    async def test_gc_no_op_when_nothing_to_evict(self, mock_store: object) -> None:
        """GC with fresh entries archives nothing."""
        await tapps_memory(action="save", key="fresh-key", value="Fresh value")
        result = await tapps_memory(action="gc")
        assert result["success"] is True
        assert result["data"]["action"] == "gc"
        assert result["data"]["archived_count"] == 0
        assert result["data"]["remaining_count"] == 1

    async def test_gc_returns_counts(self, mock_store: object) -> None:
        """GC response includes archived_count and remaining_count."""
        result = await tapps_memory(action="gc")
        assert result["success"] is True
        assert "archived_count" in result["data"]
        assert "remaining_count" in result["data"]
        assert "archived_keys" in result["data"]

    async def test_gc_evicts_stale_session_entries(self, tmp_path: Path) -> None:
        """GC archives expired session-scoped memories."""
        from tapps_core.memory.models import MemoryEntry
        from tapps_core.memory.store import MemoryStore

        store = MemoryStore(tmp_path)

        # Create an old session-scoped entry with updated_at 10 days ago
        old_time = (datetime.now(tz=UTC) - timedelta(days=10)).isoformat()
        entry = MemoryEntry(
            key="old-session",
            value="Session data",
            tier="context",
            scope="session",
            source="agent",
            created_at=old_time,
            updated_at=old_time,
            last_accessed=old_time,
            confidence=0.3,
        )
        # Write directly to persistence and in-memory cache
        store._entries[entry.key] = entry  # noqa: SLF001
        store._persistence.save(entry)  # noqa: SLF001

        # Also add a fresh project-scoped entry
        store.save(key="fresh-project", value="Still relevant")

        with patch(
            "tapps_mcp.server_memory_tools._get_memory_store", return_value=store
        ):
            result = await tapps_memory(action="gc")

        assert result["success"] is True
        assert result["data"]["archived_count"] == 1
        assert "old-session" in result["data"]["archived_keys"]
        assert result["data"]["remaining_count"] == 1

    async def test_gc_has_store_metadata(self, mock_store: object) -> None:
        """GC response includes store metadata."""
        result = await tapps_memory(action="gc")
        assert "store_metadata" in result["data"]
        assert "total_count" in result["data"]["store_metadata"]

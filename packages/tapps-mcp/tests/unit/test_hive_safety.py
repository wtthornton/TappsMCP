"""Unit tests for TAP-2014: Hive elevation safety gate.

Covers:
- HiveElevationStore: propose / approve / check_approved
- Stale approval (> 7 days) is treated as missing
- brain_propose_hive_elevation MCP handler
- brain_approve_hive_elevation MCP handler
- HttpBrainBridge elevation_guard interception in hive_propagate
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.tools.hive_safety import (
    HiveElevationStore,
    _APPROVAL_MAX_AGE_SECONDS,
    get_elevation_store,
    reset_elevation_store,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_store() -> None:
    """Reset the module-level singleton before and after each test."""
    reset_elevation_store()
    yield  # type: ignore[misc]
    reset_elevation_store()


@pytest.fixture()
def store(tmp_path: Path) -> HiveElevationStore:
    """Return a fresh HiveElevationStore backed by a temp directory."""
    return HiveElevationStore(tmp_path / "hive-elevation-proposals.json")


@pytest.fixture()
def mock_settings(tmp_path: Path) -> Any:
    """Minimal settings mock with project_root pointing to tmp_path."""
    s = MagicMock()
    s.project_root = tmp_path
    return s


@pytest.fixture()
def mock_bridge() -> MagicMock:
    """MagicMock bridge with async record_kg_event."""
    bridge = MagicMock()
    bridge.record_kg_event = AsyncMock(return_value={"recorded": True})
    return bridge


# ---------------------------------------------------------------------------
# HiveElevationStore unit tests
# ---------------------------------------------------------------------------


class TestHiveElevationStore:
    """Tests for the local file-backed approval store."""

    def test_propose_returns_hex_id(self, store: HiveElevationStore) -> None:
        pid = store.propose("my-memory-key", "test justification")
        assert isinstance(pid, str)
        assert len(pid) == 16
        assert all(c in "0123456789abcdef" for c in pid)

    def test_propose_creates_pending_entry(self, store: HiveElevationStore) -> None:
        pid = store.propose("key1", "justification")
        proposals = store._load()
        assert pid in proposals
        entry = proposals[pid]
        assert entry["memory_key"] == "key1"
        assert entry["status"] == "pending"
        assert "proposed_at" in entry
        assert "proposed_at_ts" in entry

    def test_check_approved_pending_returns_false(self, store: HiveElevationStore) -> None:
        store.propose("key1", "justification")
        assert store.check_approved("key1") is False

    def test_approve_returns_approved_true(self, store: HiveElevationStore) -> None:
        pid = store.propose("key1", "justification")
        result = store.approve(pid)
        assert result["approved"] is True
        assert result["proposal_id"] == pid
        assert result["memory_key"] == "key1"

    def test_check_approved_after_approve_returns_true(self, store: HiveElevationStore) -> None:
        pid = store.propose("key1", "justification")
        store.approve(pid)
        assert store.check_approved("key1") is True

    def test_check_approved_wrong_key_returns_false(self, store: HiveElevationStore) -> None:
        pid = store.propose("key1", "justification")
        store.approve(pid)
        assert store.check_approved("other-key") is False

    def test_approve_unknown_proposal_returns_error(self, store: HiveElevationStore) -> None:
        result = store.approve("nonexistent-id")
        assert result["approved"] is False
        assert result["error"] == "proposal_not_found"

    def test_approve_already_approved_is_idempotent(self, store: HiveElevationStore) -> None:
        pid = store.propose("key1", "justification")
        store.approve(pid)
        result = store.approve(pid)
        assert result["approved"] is True
        assert result.get("already_approved") is True

    def test_stale_approval_returns_false(self, store: HiveElevationStore) -> None:
        """Approvals older than 7 days are rejected."""
        pid = store.propose("key1", "justification")
        proposals = store._load()
        proposals[pid]["status"] = "approved"
        proposals[pid]["approved_at_ts"] = time.time() - _APPROVAL_MAX_AGE_SECONDS - 1
        store._save(proposals)
        assert store.check_approved("key1") is False

    def test_fresh_approval_returns_true(self, store: HiveElevationStore) -> None:
        """Approvals within 7 days are accepted."""
        pid = store.propose("key1", "justification")
        proposals = store._load()
        proposals[pid]["status"] = "approved"
        proposals[pid]["approved_at_ts"] = time.time() - 60  # 1 minute ago
        store._save(proposals)
        assert store.check_approved("key1") is True

    def test_missing_store_file_check_returns_false(self, tmp_path: Path) -> None:
        """check_approved on a nonexistent file returns False (no crash)."""
        s = HiveElevationStore(tmp_path / "nonexistent.json")
        assert s.check_approved("key") is False

    def test_list_proposals_includes_expired_flag(self, store: HiveElevationStore) -> None:
        pid = store.propose("key1", "justification")
        store.approve(pid)
        rows = store.list_proposals()
        assert len(rows) == 1
        row = rows[0]
        assert row["proposal_id"] == pid
        assert row["expired"] is False

    def test_get_elevation_store_singleton(self, tmp_path: Path) -> None:
        s1 = get_elevation_store(tmp_path)
        s2 = get_elevation_store(tmp_path)
        assert s1 is s2


# ---------------------------------------------------------------------------
# MCP handler tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
class TestBrainProposeHiveElevation:
    """Tests for the brain_propose_hive_elevation MCP handler."""

    async def test_missing_memory_key_returns_error(self) -> None:
        from tapps_mcp.server_memory_tools import brain_propose_hive_elevation

        result = await brain_propose_hive_elevation(memory_key="", justification="reason")
        assert result["success"] is False
        assert "missing_param" in result["error"]["code"]

    async def test_missing_justification_returns_error(self) -> None:
        from tapps_mcp.server_memory_tools import brain_propose_hive_elevation

        result = await brain_propose_hive_elevation(memory_key="key1", justification="")
        assert result["success"] is False
        assert "missing_param" in result["error"]["code"]

    async def test_success_returns_proposal_id(
        self, mock_settings: Any, mock_bridge: MagicMock
    ) -> None:
        from tapps_mcp.server_memory_tools import brain_propose_hive_elevation

        with (
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=mock_bridge),
            patch("tapps_core.config.settings.load_settings", return_value=mock_settings),
        ):
            result = await brain_propose_hive_elevation(
                memory_key="test-key", justification="Important elevation"
            )

        assert result["success"] is True
        assert "proposal_id" in result["data"]
        assert result["data"]["status"] == "pending"
        assert result["data"]["memory_key"] == "test-key"

    async def test_brain_kg_event_fired_best_effort(
        self, mock_settings: Any, mock_bridge: MagicMock
    ) -> None:
        from tapps_mcp.server_memory_tools import brain_propose_hive_elevation

        with (
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=mock_bridge),
            patch("tapps_core.config.settings.load_settings", return_value=mock_settings),
        ):
            await brain_propose_hive_elevation(memory_key="test-key", justification="reason")

        mock_bridge.record_kg_event.assert_awaited_once()
        assert mock_bridge.record_kg_event.call_args.kwargs["event_type"] == "hive_elevation_proposed"

    async def test_bridge_none_does_not_crash(self, mock_settings: Any) -> None:
        from tapps_mcp.server_memory_tools import brain_propose_hive_elevation

        with (
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=None),
            patch("tapps_core.config.settings.load_settings", return_value=mock_settings),
        ):
            result = await brain_propose_hive_elevation(memory_key="k", justification="j")

        assert result["success"] is True


@pytest.mark.asyncio()
class TestBrainApproveHiveElevation:
    """Tests for the brain_approve_hive_elevation MCP handler."""

    async def test_missing_proposal_id_returns_error(self) -> None:
        from tapps_mcp.server_memory_tools import brain_approve_hive_elevation

        result = await brain_approve_hive_elevation(proposal_id="")
        assert result["success"] is False
        assert "missing_param" in result["error"]["code"]

    async def test_unknown_proposal_returns_error(self, mock_settings: Any) -> None:
        from tapps_mcp.server_memory_tools import brain_approve_hive_elevation

        with (
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=None),
            patch("tapps_core.config.settings.load_settings", return_value=mock_settings),
        ):
            result = await brain_approve_hive_elevation(proposal_id="does-not-exist")

        assert result["success"] is False
        assert result["error"]["code"] == "proposal_not_found"

    async def test_approve_known_proposal_succeeds(
        self, mock_settings: Any, mock_bridge: MagicMock
    ) -> None:
        from tapps_mcp.server_memory_tools import (
            brain_approve_hive_elevation,
            brain_propose_hive_elevation,
        )

        with (
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=mock_bridge),
            patch("tapps_core.config.settings.load_settings", return_value=mock_settings),
        ):
            propose_result = await brain_propose_hive_elevation(
                memory_key="key-to-approve", justification="good reason"
            )
            assert propose_result["success"] is True
            proposal_id = propose_result["data"]["proposal_id"]

            approve_result = await brain_approve_hive_elevation(proposal_id=proposal_id)

        assert approve_result["success"] is True
        assert approve_result["data"]["approved"] is True
        assert approve_result["data"]["memory_key"] == "key-to-approve"
        assert approve_result["data"]["proposal_id"] == proposal_id

    async def test_approval_kg_event_fired(
        self, mock_settings: Any, mock_bridge: MagicMock
    ) -> None:
        from tapps_mcp.server_memory_tools import (
            brain_approve_hive_elevation,
            brain_propose_hive_elevation,
        )

        with (
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=mock_bridge),
            patch("tapps_core.config.settings.load_settings", return_value=mock_settings),
        ):
            propose_r = await brain_propose_hive_elevation(memory_key="k", justification="j")
            pid = propose_r["data"]["proposal_id"]
            await brain_approve_hive_elevation(proposal_id=pid)

        # Both propose and approve fire record_kg_event
        assert mock_bridge.record_kg_event.await_count == 2
        event_types = [c.kwargs["event_type"] for c in mock_bridge.record_kg_event.call_args_list]
        assert "hive_elevation_proposed" in event_types
        assert "hive_elevation_approved" in event_types


# ---------------------------------------------------------------------------
# HttpBrainBridge elevation_guard integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
class TestBrainBridgeElevationGuard:
    """Verify HttpBrainBridge.hive_propagate respects the elevation_guard."""

    async def test_refused_without_approval(self) -> None:
        """With guard=always-False, all entries are refused and brain is not called."""
        from tapps_core.brain_bridge import HttpBrainBridge

        bridge = MagicMock(spec=HttpBrainBridge)
        bridge.elevation_guard = lambda _key: False
        bridge._http_mcp_call = AsyncMock()

        result = await HttpBrainBridge.hive_propagate(
            bridge,
            entries=[{"key": "blocked-key", "agent_scope": "hive"}],
            agent_id="test",
            agent_profile="hive",
        )

        assert result["refused_no_approval"] == 1
        assert result["propagated"] == 0
        bridge._http_mcp_call.assert_not_awaited()

    async def test_no_guard_calls_brain(self) -> None:
        """When elevation_guard is None, entries pass through to brain."""
        from tapps_core.brain_bridge import HttpBrainBridge

        bridge = MagicMock(spec=HttpBrainBridge)
        bridge.elevation_guard = None
        bridge._http_mcp_call = AsyncMock(return_value={"propagated": 1, "success": True})

        result = await HttpBrainBridge.hive_propagate(
            bridge,
            entries=[{"key": "some-key", "agent_scope": "hive"}],
            agent_id="test",
            agent_profile="hive",
        )

        assert result["propagated"] == 1
        bridge._http_mcp_call.assert_awaited_once()

    async def test_approved_key_calls_brain(self, tmp_path: Path) -> None:
        """When guard approves the key, brain is called normally."""
        from tapps_core.brain_bridge import HttpBrainBridge

        store = HiveElevationStore(tmp_path / "proposals.json")
        pid = store.propose("approved-key", "reason")
        store.approve(pid)

        bridge = MagicMock(spec=HttpBrainBridge)
        bridge.elevation_guard = store.check_approved
        bridge._http_mcp_call = AsyncMock(return_value={"propagated": 1, "success": True})

        result = await HttpBrainBridge.hive_propagate(
            bridge,
            entries=[{"key": "approved-key", "agent_scope": "hive"}],
            agent_id="test",
            agent_profile="hive",
        )

        assert result["propagated"] == 1
        assert result["refused_no_approval"] == 0
        bridge._http_mcp_call.assert_awaited_once()

    async def test_private_scope_skipped_regardless_of_guard(self) -> None:
        """private-scoped entries are still skipped even with a permissive guard."""
        from tapps_core.brain_bridge import HttpBrainBridge

        bridge = MagicMock(spec=HttpBrainBridge)
        bridge.elevation_guard = lambda _key: True  # would approve any key
        bridge._http_mcp_call = AsyncMock()

        result = await HttpBrainBridge.hive_propagate(
            bridge,
            entries=[{"key": "private-key", "agent_scope": "private"}],
            agent_id="test",
            agent_profile="hive",
        )

        assert result["skipped_private"] == 1
        assert result["propagated"] == 0
        bridge._http_mcp_call.assert_not_awaited()

    async def test_mixed_entries_approved_and_refused(self, tmp_path: Path) -> None:
        """Mixed entries: approved key propagates, unapproved key is refused."""
        from tapps_core.brain_bridge import HttpBrainBridge

        store = HiveElevationStore(tmp_path / "proposals.json")
        pid = store.propose("approved-key", "reason")
        store.approve(pid)

        bridge = MagicMock(spec=HttpBrainBridge)
        bridge.elevation_guard = store.check_approved
        bridge._http_mcp_call = AsyncMock(return_value={"propagated": 1, "success": True})

        entries = [
            {"key": "approved-key", "agent_scope": "hive"},
            {"key": "unapproved-key", "agent_scope": "hive"},
        ]
        result = await HttpBrainBridge.hive_propagate(
            bridge,
            entries=entries,
            agent_id="test",
            agent_profile="hive",
        )

        assert result["propagated"] == 1
        assert result["refused_no_approval"] == 1
        # Only one brain call (for the approved key)
        bridge._http_mcp_call.assert_awaited_once()

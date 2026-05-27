"""TAP-1993/TAP-1994: tapps_memory internal-function tests.

TAP-1993 (Phase 2): non-lifecycle actions return a refused-redirect envelope.
TAP-1994 (Phase 3): tapps_memory is no longer registered as an MCP tool.
The function continues to exist as an internal helper for lifecycle calls;
all non-lifecycle behaviour remains as before (refused envelope redirects).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.server_memory_tools import (
    _LIFECYCLE_ACTIONS,
    _REFUSED_BRAIN_TOOL,
    _VALID_ACTIONS,
    tapps_memory,
)


async def _noop_init() -> None:
    """Async no-op for ensure_session_initialized."""


@pytest.mark.asyncio()
class TestRefusedEnvelope:
    """TAP-1993: non-lifecycle actions return a refused-redirect envelope."""

    @pytest.fixture(autouse=True)
    def _mock_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Skip session initialization in tests."""
        monkeypatch.setattr(
            "tapps_mcp.server_memory_tools.ensure_session_initialized",
            _noop_init,
        )

    def _make_mock_bridge(self) -> MagicMock:
        bridge = MagicMock()
        bridge.record_event = AsyncMock(return_value={"recorded": True})
        return bridge

    @pytest.mark.parametrize("action", sorted(_VALID_ACTIONS - _LIFECYCLE_ACTIONS))
    async def test_non_lifecycle_action_returns_refused(self, action: str) -> None:
        """Every non-lifecycle action must return a refused envelope, not execute."""
        bridge = self._make_mock_bridge()

        with patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge):
            result = await tapps_memory(action=action)
            await asyncio.sleep(0)  # let any background tasks complete

        assert result["success"] is True, (
            f"action={action!r}: expected success=True for refused envelope, got {result}"
        )
        data = result["data"]
        assert data.get("refused") is True, (
            f"action={action!r}: expected 'refused': True in data, got {data}"
        )
        assert data.get("action") == action, (
            f"action={action!r}: 'action' field in envelope must echo the original action"
        )
        use = data.get("use", "")
        assert use.startswith("mcp__tapps-brain__"), (
            f"action={action!r}: 'use' field must reference a mcp__tapps-brain__ tool, got {use!r}"
        )
        assert "hint" in data, (
            f"action={action!r}: refused envelope must include a 'hint' field"
        )

    async def test_refused_envelope_use_field_matches_mapping(self) -> None:
        """The 'use' field in the refused envelope must match _REFUSED_BRAIN_TOOL."""
        bridge = self._make_mock_bridge()

        for action, expected_tool in _REFUSED_BRAIN_TOOL.items():
            with patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge):
                result = await tapps_memory(action=action)

            data = result["data"]
            assert data.get("refused") is True
            assert data.get("use") == expected_tool, (
                f"action={action!r}: expected use={expected_tool!r}, got {data.get('use')!r}"
            )

    async def test_refused_actions_do_not_touch_store(self) -> None:
        """Non-lifecycle actions must return before initializing the memory store."""
        bridge = self._make_mock_bridge()

        with (
            patch(
                "tapps_mcp.server_memory_tools._get_memory_store",
                side_effect=AssertionError("store must not be initialized for refused actions"),
            ),
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge),
        ):
            # 'save' is a non-lifecycle action that must never hit _get_memory_store
            result = await tapps_memory(action="save", key="k", value="v")

        data = result["data"]
        assert data.get("refused") is True

    async def test_refused_envelope_is_parseable_for_self_correction(self) -> None:
        """Integration test: an agent receiving a refused envelope can self-correct.

        The envelope must contain enough machine-readable info for the agent to:
        1. Detect refusal (refused=True).
        2. Identify the correct brain tool (use='mcp__tapps-brain__...').
        3. Echo the original action for logging (action='...').
        """
        bridge = self._make_mock_bridge()

        with patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge):
            result = await tapps_memory(action="search", query="session patterns")

        data = result["data"]
        # Step 1: detect refusal.
        assert data["refused"] is True
        # Step 2: self-correct — the use field names a callable brain tool.
        brain_tool = data["use"]
        assert brain_tool.startswith("mcp__tapps-brain__"), (
            f"use={brain_tool!r} is not a tapps-brain tool — agent cannot self-correct"
        )
        # Step 3: original action is preserved for diagnostics.
        assert data["action"] == "search"

    async def test_refused_telemetry_still_fires(self) -> None:
        """TAP-1992 telemetry fires even when the action is refused (Phase 1 data preserved)."""
        bridge = self._make_mock_bridge()

        with patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge):
            await tapps_memory(action="save", key="k", value="v")
            await asyncio.sleep(0)

        bridge.record_event.assert_called_once_with(
            "deprecated_tool_call", "tapps_memory:save"
        )


@pytest.mark.asyncio()
class TestLifecycleActions:
    """TAP-1993: lifecycle actions (session_start_capture, session_end_consolidate) execute."""

    @pytest.fixture(autouse=True)
    def _mock_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "tapps_mcp.server_memory_tools.ensure_session_initialized",
            _noop_init,
        )

    def _make_mock_bridge(self) -> MagicMock:
        bridge = MagicMock()
        bridge.record_event = AsyncMock(return_value={"recorded": True})
        return bridge

    async def test_session_start_capture_does_not_return_refused(self) -> None:
        """session_start_capture must NOT return the refused envelope."""
        bridge = self._make_mock_bridge()
        bridge.index_session = AsyncMock(return_value={"indexed": True, "session_id": "s1"})

        with (
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge),
            patch(
                "tapps_mcp.server_memory_tools._get_memory_store", side_effect=Exception("no store")
            ),
        ):
            result = await tapps_memory(
                action="session_start_capture",
                value="testing session capture",
            )

        data = result.get("data", result)
        assert data.get("refused") is not True, (
            f"session_start_capture must not return refused envelope; got {data}"
        )

    async def test_session_end_consolidate_does_not_return_refused(self) -> None:
        """session_end_consolidate must NOT return the refused envelope."""
        bridge = self._make_mock_bridge()
        bridge.session_end = AsyncMock(return_value={"finalized": True})

        with (
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge),
            patch(
                "tapps_mcp.server_memory_tools._get_memory_store", side_effect=Exception("no store")
            ),
        ):
            result = await tapps_memory(
                action="session_end_consolidate",
                value="Session complete — fixed TAP-1993",
            )

        data = result.get("data", result)
        assert data.get("refused") is not True, (
            f"session_end_consolidate must not return refused envelope; got {data}"
        )

    def test_lifecycle_actions_are_in_valid_actions(self) -> None:
        """Both lifecycle actions must be registered in _VALID_ACTIONS."""
        assert "session_start_capture" in _VALID_ACTIONS
        assert "session_end_consolidate" in _VALID_ACTIONS

    def test_lifecycle_actions_not_in_refused_mapping(self) -> None:
        """Lifecycle actions must not appear in _REFUSED_BRAIN_TOOL (they are not redirected)."""
        assert "session_start_capture" not in _REFUSED_BRAIN_TOOL
        assert "session_end_consolidate" not in _REFUSED_BRAIN_TOOL

    def test_refused_mapping_covers_all_non_lifecycle_valid_actions(self) -> None:
        """Every non-lifecycle valid action must have an entry in _REFUSED_BRAIN_TOOL."""
        non_lifecycle = _VALID_ACTIONS - _LIFECYCLE_ACTIONS
        missing = non_lifecycle - set(_REFUSED_BRAIN_TOOL.keys())
        assert not missing, (
            f"These non-lifecycle actions are missing from _REFUSED_BRAIN_TOOL: {sorted(missing)}"
        )


class TestMcpCatalogRemoval:
    """TAP-1994 (Phase 3): tapps_memory must NOT appear in the MCP tool catalog."""

    def test_tapps_memory_not_in_mcp_tool_catalog(self) -> None:
        """tapps_memory must be absent from the live MCP tool registry after Phase 3."""
        from tapps_mcp.server import mcp

        tools = mcp._tool_manager._tools
        assert "tapps_memory" not in tools, (
            "tapps_memory is still registered as an MCP tool — "
            "TAP-1994 requires it to be removed from the catalog"
        )

    def test_tapps_memory_not_in_all_tool_names(self) -> None:
        """ALL_TOOL_NAMES must not include tapps_memory after Phase 3."""
        from tapps_mcp.server import ALL_TOOL_NAMES

        assert "tapps_memory" not in ALL_TOOL_NAMES, (
            "tapps_memory still listed in ALL_TOOL_NAMES — remove it (TAP-1994)"
        )

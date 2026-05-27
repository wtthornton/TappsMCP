"""TAP-1991/TAP-1992: Deprecation notices and per-action telemetry for tapps_memory.

TAP-1991: Every sub-action in _VALID_ACTIONS must carry a
[DEPRECATED 2026-Q3 — use mcp__tapps-brain__<tool>] prefix in the Actions:
block of the tapps_memory docstring so Claude's tool catalog signals the
migration target.

TAP-1992: Every tapps_memory invocation must fire a best-effort
brain_record_event call so removal timing is data-driven.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.server_memory_tools import _LIFECYCLE_ACTIONS, _VALID_ACTIONS, tapps_memory


class TestDeprecationNotices:
    """TAP-1991: tapps_memory docstring must carry deprecation tags for all actions."""

    def _get_docstring(self) -> str:
        doc = inspect.getdoc(tapps_memory)
        assert doc is not None, "tapps_memory has no docstring"
        return doc

    def test_top_level_deprecation_notice_present(self) -> None:
        """Main tool description must carry the top-level [DEPRECATED] notice."""
        doc = self._get_docstring()
        assert "[DEPRECATED 2026-Q3" in doc, (
            "tapps_memory docstring is missing top-level deprecation notice. "
            "Expected '[DEPRECATED 2026-Q3' near the start of the docstring."
        )

    def test_top_level_notice_references_brain_tools(self) -> None:
        """Top-level deprecation notice must name the mcp__tapps-brain__ namespace."""
        doc = self._get_docstring()
        assert "mcp__tapps-brain__" in doc, (
            "tapps_memory docstring must reference mcp__tapps-brain__* as the migration target."
        )

    @pytest.mark.parametrize("action", sorted(_VALID_ACTIONS - _LIFECYCLE_ACTIONS))
    def test_action_has_deprecation_prefix(self, action: str) -> None:
        """Each deprecated action in _VALID_ACTIONS must have a [DEPRECATED 2026-Q3] prefix.

        Lifecycle actions (session_start_capture, session_end_consolidate) are excluded
        because they are active, non-deprecated actions (TAP-1993).
        """
        doc = self._get_docstring()
        # The Actions: block uses "        action_name: [DEPRECATED..." format.
        # We check for the action name followed by the deprecation tag anywhere in the doc.
        deprecated_marker = f"{action}: [DEPRECATED 2026-Q3"
        assert deprecated_marker in doc, (
            f"Action '{action}' is missing the deprecation prefix in the tapps_memory docstring. "
            f"Expected to find '{deprecated_marker}' in the Actions: block."
        )

    @pytest.mark.parametrize("action", sorted(_VALID_ACTIONS - _LIFECYCLE_ACTIONS))
    def test_action_deprecation_names_brain_tool(self, action: str) -> None:
        """Each deprecated action's docstring entry must name a specific mcp__tapps-brain__ target.

        Lifecycle actions are excluded (TAP-1993 — they are active, not deprecated).
        """
        doc = self._get_docstring()
        # Find the line with this action's deprecation tag.
        deprecated_marker = f"{action}: [DEPRECATED 2026-Q3"
        idx = doc.find(deprecated_marker)
        assert idx != -1, f"Action '{action}' missing deprecation prefix (checked in parametrize above)"
        # Extract up to 120 chars from the action description line to find the brain tool name.
        snippet = doc[idx : idx + 120]
        assert "mcp__tapps-brain__" in snippet, (
            f"Action '{action}' deprecation line does not name a mcp__tapps-brain__* replacement. "
            f"Found: {snippet!r}"
        )

    def test_all_valid_actions_covered(self) -> None:
        """Smoke test: _VALID_ACTIONS is non-empty and all expected CRUD actions are present."""
        assert len(_VALID_ACTIONS) >= 33, (
            f"Expected at least 33 actions in _VALID_ACTIONS, got {len(_VALID_ACTIONS)}"
        )
        expected_core = {"save", "get", "search", "delete", "list", "reinforce"}
        assert expected_core <= _VALID_ACTIONS, (
            f"Core CRUD actions missing from _VALID_ACTIONS: {expected_core - _VALID_ACTIONS}"
        )


async def _noop_init() -> None:
    """Async no-op for ensure_session_initialized."""


@pytest.mark.asyncio()
class TestDeprecationTelemetry:
    """TAP-1992: tapps_memory must fire brain_record_event on every valid action call."""

    @pytest.fixture(autouse=True)
    def _mock_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Skip session initialization in tests."""
        monkeypatch.setattr(
            "tapps_mcp.server_memory_tools.ensure_session_initialized",
            _noop_init,
        )

    def _make_mock_bridge(self) -> MagicMock:
        """Return a mock bridge with an async record_event."""
        bridge = MagicMock()
        bridge.record_event = AsyncMock(return_value={"recorded": True})
        return bridge

    async def test_record_event_fired_on_save(self, tmp_path: Any) -> None:
        """tapps_memory(action='save') fires record_event with correct entity id."""
        from tapps_mcp.memory.store import MemoryStore

        store = MemoryStore(tmp_path)
        bridge = self._make_mock_bridge()

        with (
            patch("tapps_mcp.server_memory_tools._get_memory_store", return_value=store),
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge),
        ):
            result = await tapps_memory(action="save", key="tap-1992-test", value="v")
            # Yield to the event loop so the create_task fires.
            await asyncio.sleep(0)

        assert result["success"] is True
        bridge.record_event.assert_called_once_with(
            "deprecated_tool_call", "tapps_memory:save"
        )

    async def test_record_event_brain_outage_does_not_break_tapps_memory(
        self, tmp_path: Any
    ) -> None:
        """A brain_record_event failure must not propagate to tapps_memory callers."""
        from tapps_mcp.memory.store import MemoryStore

        store = MemoryStore(tmp_path)
        bridge = self._make_mock_bridge()
        bridge.record_event = AsyncMock(side_effect=RuntimeError("brain is down"))

        with (
            patch("tapps_mcp.server_memory_tools._get_memory_store", return_value=store),
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge),
        ):
            result = await tapps_memory(action="save", key="tap-1992-outage", value="v")
            await asyncio.sleep(0)  # let task run

        # tapps_memory must still succeed despite brain outage
        assert result["success"] is True

    async def test_record_event_not_fired_for_invalid_action(self) -> None:
        """An invalid action must not fire a telemetry event."""
        bridge = self._make_mock_bridge()

        with patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge):
            result = await tapps_memory(action="not_a_real_action")
            await asyncio.sleep(0)

        assert result["success"] is False
        bridge.record_event.assert_not_called()

    async def test_record_event_entity_id_includes_action_name(self, tmp_path: Any) -> None:
        """The entity_id passed to record_event must be 'tapps_memory:<action>'."""
        from tapps_mcp.memory.store import MemoryStore

        store = MemoryStore(tmp_path)
        bridge = self._make_mock_bridge()

        with (
            patch("tapps_mcp.server_memory_tools._get_memory_store", return_value=store),
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge),
        ):
            await tapps_memory(action="search", query="test")
            await asyncio.sleep(0)

        bridge.record_event.assert_called_once_with(
            "deprecated_tool_call", "tapps_memory:search"
        )

    async def test_record_event_skipped_when_bridge_is_none(self, tmp_path: Any) -> None:
        """When no bridge is available, telemetry is silently skipped."""
        from tapps_mcp.memory.store import MemoryStore

        store = MemoryStore(tmp_path)

        with (
            patch("tapps_mcp.server_memory_tools._get_memory_store", return_value=store),
            patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=None),
        ):
            result = await tapps_memory(action="save", key="no-bridge", value="v")

        assert result["success"] is True  # still works without bridge

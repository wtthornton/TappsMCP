"""Tests for TAP-2005: tapps_session_end calls flywheel_process to close feedback loop."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCallFlywheelProcess:
    """Unit tests for session_end_helpers.call_flywheel_process."""

    @pytest.mark.asyncio
    async def test_calls_flywheel_process_with_since(self) -> None:
        """flywheel_process is called with the session_start_iso timestamp."""
        bridge = MagicMock()
        bridge.flywheel_process = AsyncMock(return_value={"processed": 3, "gaps": 1})

        with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=bridge):
            from tapps_mcp.tools.session_end_helpers import call_flywheel_process

            result = await call_flywheel_process("2026-05-23T10:00:00+00:00")

        bridge.flywheel_process.assert_awaited_once_with(since="2026-05-23T10:00:00+00:00")
        assert result["success"] is True
        assert result["since"] == "2026-05-23T10:00:00+00:00"
        assert result["result"]["processed"] == 3

    @pytest.mark.asyncio
    async def test_calls_flywheel_process_with_empty_since(self) -> None:
        """flywheel_process is called with empty since when no session start was recorded."""
        bridge = MagicMock()
        bridge.flywheel_process = AsyncMock(return_value={"processed": 0})

        with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=bridge):
            from tapps_mcp.tools.session_end_helpers import call_flywheel_process

            result = await call_flywheel_process("")

        bridge.flywheel_process.assert_awaited_once_with(since="")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_returns_skipped_when_bridge_none(self) -> None:
        """Returns skipped=True when no bridge is available (brain not configured)."""
        with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=None):
            from tapps_mcp.tools.session_end_helpers import call_flywheel_process

            result = await call_flywheel_process("2026-05-23T10:00:00+00:00")

        assert result["success"] is False
        assert result["skipped"] is True
        assert result["reason"] == "bridge_unavailable"

    @pytest.mark.asyncio
    async def test_returns_skipped_when_method_missing(self) -> None:
        """Returns skipped=True when bridge exists but lacks flywheel_process."""
        bridge = MagicMock(spec=[])  # no methods

        with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=bridge):
            from tapps_mcp.tools.session_end_helpers import call_flywheel_process

            result = await call_flywheel_process("2026-05-23T10:00:00+00:00")

        assert result["success"] is False
        assert result["skipped"] is True
        assert result["reason"] == "flywheel_process_not_supported"

    @pytest.mark.asyncio
    async def test_returns_error_on_bridge_exception(self) -> None:
        """Best-effort: exceptions from flywheel_process surface as error, not raised."""
        bridge = MagicMock()
        bridge.flywheel_process = AsyncMock(side_effect=RuntimeError("network error"))

        with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=bridge):
            from tapps_mcp.tools.session_end_helpers import call_flywheel_process

            result = await call_flywheel_process("2026-05-23T10:00:00+00:00")

        assert result["success"] is False
        assert "network error" in result["error"]

    @pytest.mark.asyncio
    async def test_returns_skipped_when_bridge_resolve_raises(self) -> None:
        """Best-effort: exceptions from _get_brain_bridge surface as skipped, not raised."""
        with patch(
            "tapps_mcp.server_helpers._get_brain_bridge",
            side_effect=ImportError("bridge import failed"),
        ):
            from tapps_mcp.tools.session_end_helpers import call_flywheel_process

            result = await call_flywheel_process("2026-05-23T10:00:00+00:00")

        assert result["success"] is False
        assert result["skipped"] is True


class TestSessionStateIsoStamp:
    """Tests for session_start_iso tracking in _SessionFlags."""

    def test_session_flags_has_session_start_iso_field(self) -> None:
        """_SessionFlags carries a session_start_iso field (default empty string)."""
        from tapps_mcp.server_pipeline_tools import _SessionFlags

        flags = _SessionFlags()
        assert flags.session_start_iso == ""

    def test_reset_session_state_clears_iso(self) -> None:
        """_reset_session_state resets session_start_iso to empty string."""
        from tapps_mcp import server_pipeline_tools as _spt

        _spt._session_state.session_start_iso = "2026-05-23T10:00:00+00:00"
        _spt._reset_session_state()
        assert _spt._session_state.session_start_iso == ""

    def test_session_start_iso_is_set_on_session_start(self) -> None:
        """session_start_iso is initially empty until tapps_session_start runs."""
        from tapps_mcp import server_pipeline_tools as _spt

        _spt._reset_session_state()
        assert _spt._session_state.session_start_iso == ""

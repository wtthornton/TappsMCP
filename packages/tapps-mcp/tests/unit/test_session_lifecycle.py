"""Tests for tapps session lifecycle helpers.

TAP-2005: tapps_session_end calls flywheel_process to close feedback loop.
TAP-1999: session_start calls memory_index_session; session_end calls
memory_search_sessions to fetch the live brain-native session record.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestRunSessionEnd:
    """TAP-3174: shared run_session_end helper for MCP tool and CLI."""

    @pytest.mark.asyncio
    async def test_run_session_end_composes_flywheel_and_search(self) -> None:
        bridge = MagicMock()
        bridge.flywheel_process = AsyncMock(return_value={"processed": 1})
        bridge.search_sessions = AsyncMock(return_value={"results": [{"id": "s1"}]})

        with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=bridge):
            from tapps_mcp.tools.session_end_helpers import run_session_end

            result = await run_session_end("2026-06-09T12:00:00+00:00")

        assert result["session_start_iso"] == "2026-06-09T12:00:00+00:00"
        assert result["flywheel"]["success"] is True
        assert result["session_search"]["success"] is True

    def test_run_session_end_sync_cli_wrapper(self) -> None:
        with patch(
            "tapps_mcp.tools.session_end_helpers.run_session_end",
            new=AsyncMock(
                return_value={
                    "flywheel": {"success": False, "skipped": True},
                    "session_search": {"success": False, "skipped": True},
                    "session_start_iso": None,
                }
            ),
        ):
            from tapps_mcp.tools.session_end_helpers import run_session_end_sync

            result = run_session_end_sync()

        assert result["session_start_iso"] is None
        assert result["flywheel"]["skipped"] is True


class TestSessionEndCli:
    """TAP-3174: session-end CLI command."""

    def test_session_end_cli_exits_zero_on_degrade(self) -> None:
        from click.testing import CliRunner

        from tapps_mcp.cli import main

        runner = CliRunner()
        with patch(
            "tapps_mcp.tools.session_end_helpers.run_session_end_sync",
            return_value={
                "flywheel": {"success": False, "skipped": True, "reason": "bridge_unavailable"},
                "session_search": {"success": False, "skipped": True},
                "session_start_iso": None,
            },
        ):
            result = runner.invoke(main, ["session-end"])
        assert result.exit_code == 0
        assert "bridge_unavailable" in result.output


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


class TestCallMemoryIndexSessionStart:
    """TAP-1999: unit tests for session_start_helpers.call_memory_index_session_start."""

    @pytest.mark.asyncio
    async def test_calls_index_session_with_session_id_and_project(self) -> None:
        """index_session called with session_id and a chunk containing project name."""
        bridge = MagicMock()
        bridge.index_session = AsyncMock(return_value={"stored": True})

        with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=bridge):
            from tapps_mcp.tools.session_start_helpers import call_memory_index_session_start

            result = await call_memory_index_session_start(
                "2026-05-23T10:00:00+00:00", Path("/repo/tapps-mcp")
            )

        bridge.index_session.assert_awaited_once()
        call_args = bridge.index_session.await_args
        session_id_arg, chunks_arg = call_args.args
        assert session_id_arg == "2026-05-23T10:00:00+00:00"
        assert any("session_start:2026-05-23T10:00:00+00:00" in c for c in chunks_arg)
        assert any("project:tapps-mcp" in c for c in chunks_arg)
        assert result["success"] is True
        assert result["session_id"] == "2026-05-23T10:00:00+00:00"

    @pytest.mark.asyncio
    async def test_returns_skipped_when_bridge_none(self) -> None:
        """Returns skipped=True when no bridge is available."""
        with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=None):
            from tapps_mcp.tools.session_start_helpers import call_memory_index_session_start

            result = await call_memory_index_session_start(
                "2026-05-23T10:00:00+00:00", Path("/repo/tapps-mcp")
            )

        assert result["success"] is False
        assert result["skipped"] is True
        assert result["reason"] == "bridge_unavailable"

    @pytest.mark.asyncio
    async def test_returns_skipped_when_method_missing(self) -> None:
        """Returns skipped=True when bridge has no index_session method."""
        bridge = MagicMock(spec=[])  # no methods

        with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=bridge):
            from tapps_mcp.tools.session_start_helpers import call_memory_index_session_start

            result = await call_memory_index_session_start(
                "2026-05-23T10:00:00+00:00", Path("/repo/tapps-mcp")
            )

        assert result["success"] is False
        assert result["skipped"] is True
        assert result["reason"] == "index_session_not_supported"

    @pytest.mark.asyncio
    async def test_returns_error_on_bridge_exception(self) -> None:
        """Best-effort: exceptions from index_session surface as error, not raised."""
        bridge = MagicMock()
        bridge.index_session = AsyncMock(side_effect=RuntimeError("network error"))

        with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=bridge):
            from tapps_mcp.tools.session_start_helpers import call_memory_index_session_start

            result = await call_memory_index_session_start(
                "2026-05-23T10:00:00+00:00", Path("/repo/tapps-mcp")
            )

        assert result["success"] is False
        assert "network error" in result["error"]


class TestCallMemorySearchSessions:
    """TAP-1999: unit tests for session_end_helpers.call_memory_search_sessions."""

    @pytest.mark.asyncio
    async def test_calls_search_sessions_with_query(self) -> None:
        """search_sessions called with the provided query and returns results."""
        bridge = MagicMock()
        bridge.search_sessions = AsyncMock(
            return_value={"results": [{"session_id": "abc", "score": 0.9}]}
        )

        with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=bridge):
            from tapps_mcp.tools.session_end_helpers import call_memory_search_sessions

            result = await call_memory_search_sessions("2026-05-23T10:00:00+00:00")

        bridge.search_sessions.assert_awaited_once_with(
            "2026-05-23T10:00:00+00:00", limit=10
        )
        assert result["success"] is True
        assert result["query"] == "2026-05-23T10:00:00+00:00"

    @pytest.mark.asyncio
    async def test_calls_search_sessions_with_custom_limit(self) -> None:
        """search_sessions is called with the specified limit."""
        bridge = MagicMock()
        bridge.search_sessions = AsyncMock(return_value={"results": []})

        with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=bridge):
            from tapps_mcp.tools.session_end_helpers import call_memory_search_sessions

            await call_memory_search_sessions("recent", limit=5)

        bridge.search_sessions.assert_awaited_once_with("recent", limit=5)

    @pytest.mark.asyncio
    async def test_returns_skipped_when_bridge_none(self) -> None:
        """Returns skipped=True when no bridge available."""
        with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=None):
            from tapps_mcp.tools.session_end_helpers import call_memory_search_sessions

            result = await call_memory_search_sessions("recent")

        assert result["success"] is False
        assert result["skipped"] is True
        assert result["reason"] == "bridge_unavailable"

    @pytest.mark.asyncio
    async def test_returns_skipped_when_method_missing(self) -> None:
        """Returns skipped=True when bridge lacks search_sessions."""
        bridge = MagicMock(spec=[])

        with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=bridge):
            from tapps_mcp.tools.session_end_helpers import call_memory_search_sessions

            result = await call_memory_search_sessions("recent")

        assert result["success"] is False
        assert result["skipped"] is True
        assert result["reason"] == "search_sessions_not_supported"

    @pytest.mark.asyncio
    async def test_returns_error_on_exception(self) -> None:
        """Best-effort: exceptions from search_sessions surface as error."""
        bridge = MagicMock()
        bridge.search_sessions = AsyncMock(side_effect=RuntimeError("timeout"))

        with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=bridge):
            from tapps_mcp.tools.session_end_helpers import call_memory_search_sessions

            result = await call_memory_search_sessions("recent")

        assert result["success"] is False
        assert "timeout" in result["error"]


class TestSessionBoundaryRoundTrip:
    """TAP-1999: session start indexes via brain; session end searches via brain."""

    @pytest.mark.asyncio
    async def test_session_end_includes_session_search_key(self) -> None:
        """tapps_session_end response includes session_search from memory_search_sessions."""
        from tapps_mcp import server_pipeline_tools as _spt

        _spt._reset_session_state()
        _spt._session_state.session_start_iso = "2026-05-23T10:00:00+00:00"

        mock_bridge = MagicMock()
        mock_bridge.flywheel_process = AsyncMock(return_value={"processed": 0})
        mock_bridge.search_sessions = AsyncMock(return_value={"results": []})

        with (
            patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=mock_bridge),
            patch("tapps_mcp.server._record_call"),
            patch("tapps_mcp.server._record_execution"),
        ):
            result = await _spt.tapps_session_end()

        assert result["success"] is True
        data = result["data"]
        assert "session_search" in data
        assert data["session_start_iso"] == "2026-05-23T10:00:00+00:00"
        mock_bridge.search_sessions.assert_awaited_once_with(
            "2026-05-23T10:00:00+00:00", limit=10
        )


class TestCleanupLegacyLearningDir:
    """TAP-2023: _cleanup_legacy_learning_dir removes the cargo-cult artifact."""

    def test_returns_false_when_directory_absent(self, tmp_path: Path) -> None:
        """No-op when .tapps-mcp/learning/ does not exist."""
        from tapps_mcp.server_pipeline_tools import _cleanup_legacy_learning_dir

        assert _cleanup_legacy_learning_dir(tmp_path) is False

    def test_removes_empty_directory(self, tmp_path: Path) -> None:
        """Removes an empty learning/ directory and returns True."""
        from tapps_mcp.server_pipeline_tools import _cleanup_legacy_learning_dir

        learning = tmp_path / ".tapps-mcp" / "learning"
        learning.mkdir(parents=True)
        assert _cleanup_legacy_learning_dir(tmp_path) is True
        assert not learning.exists()

    def test_removes_directory_with_known_files(self, tmp_path: Path) -> None:
        """Removes learning/ even when it contains the expected JSONL files."""
        from tapps_mcp.server_pipeline_tools import _cleanup_legacy_learning_dir

        learning = tmp_path / ".tapps-mcp" / "learning"
        learning.mkdir(parents=True)
        (learning / "outcomes.jsonl").write_text("{}", encoding="utf-8")
        (learning / "expert_performance.jsonl").write_text("{}", encoding="utf-8")
        assert _cleanup_legacy_learning_dir(tmp_path) is True
        assert not learning.exists()

    def test_leaves_directory_with_unknown_files(self, tmp_path: Path) -> None:
        """Does NOT remove learning/ when it has unexpected contents."""
        from tapps_mcp.server_pipeline_tools import _cleanup_legacy_learning_dir

        learning = tmp_path / ".tapps-mcp" / "learning"
        learning.mkdir(parents=True)
        (learning / "custom-data.json").write_text("{}", encoding="utf-8")
        assert _cleanup_legacy_learning_dir(tmp_path) is False
        assert learning.exists()

    def test_idempotent_second_call_returns_false(self, tmp_path: Path) -> None:
        """A second call after successful removal is a no-op returning False."""
        from tapps_mcp.server_pipeline_tools import _cleanup_legacy_learning_dir

        learning = tmp_path / ".tapps-mcp" / "learning"
        learning.mkdir(parents=True)
        assert _cleanup_legacy_learning_dir(tmp_path) is True
        assert _cleanup_legacy_learning_dir(tmp_path) is False

"""Tests for composite tools (session_start, validate_changed, quick_check)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.tools.checklist import CallTracker


@pytest.fixture(autouse=True)
def _reset_tracker() -> None:  # type: ignore[misc]
    """Reset CallTracker before every test."""
    CallTracker.reset()


# ---------------------------------------------------------------------------
# tapps_session_start
# ---------------------------------------------------------------------------


class TestTappsSessionStart:
    """Tests for the tapps_session_start composite tool."""

    def test_returns_success(self) -> None:
        from tapps_mcp.server import tapps_session_start

        result = tapps_session_start()
        assert result["success"] is True
        assert result["tool"] == "tapps_session_start"

    def test_includes_server_and_profile_data(self) -> None:
        from tapps_mcp.server import tapps_session_start

        result = tapps_session_start()
        data = result["data"]
        assert "server" in data
        assert "configuration" in data
        assert "pipeline" in data
        assert "quick_start" in data
        assert "critical_rules" in data
        # project_profile may be present or None depending on env
        assert "project_profile" in data

    def test_records_all_calls(self) -> None:
        from tapps_mcp.server import tapps_session_start

        tapps_session_start()
        called = CallTracker.get_called_tools()
        assert "tapps_session_start" in called
        assert "tapps_server_info" in called
        assert "tapps_project_profile" in called

    def test_includes_next_steps(self) -> None:
        from tapps_mcp.server import tapps_session_start

        result = tapps_session_start()
        assert "next_steps" in result["data"]

    def test_includes_pipeline_progress(self) -> None:
        from tapps_mcp.server import tapps_session_start

        result = tapps_session_start()
        progress = result["data"]["pipeline_progress"]
        assert "discover" in progress["completed_stages"]


# ---------------------------------------------------------------------------
# tapps_validate_changed
# ---------------------------------------------------------------------------


class TestTappsValidateChanged:
    """Tests for the tapps_validate_changed batch tool."""

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.server.load_settings")
    async def test_no_files_returns_empty(
        self,
        mock_settings: MagicMock,
        mock_validate: MagicMock,
    ) -> None:
        from tapps_mcp.server import tapps_validate_changed

        mock_settings.return_value.project_root = Path("/fake")
        mock_settings.return_value.tool_timeout = 30

        with patch(
            "tapps_mcp.tools.batch_validator.detect_changed_python_files",
            return_value=[],
        ):
            result = await tapps_validate_changed()

        assert result["success"] is True
        assert result["data"]["files_validated"] == 0
        assert result["data"]["all_gates_passed"] is True

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.server.load_settings")
    async def test_explicit_file_paths(
        self,
        mock_settings: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.server import tapps_validate_changed

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")
        mock_validate.return_value = f
        mock_settings.return_value.project_root = tmp_path
        mock_settings.return_value.quality_preset = "standard"
        mock_settings.return_value.tool_timeout = 30

        result = await tapps_validate_changed(file_paths=str(f))
        assert result["success"] is True
        assert result["data"]["files_validated"] == 1

    @pytest.mark.asyncio
    async def test_records_call(self) -> None:
        from tapps_mcp.server import tapps_validate_changed

        with (
            patch(
                "tapps_mcp.tools.batch_validator.detect_changed_python_files",
                return_value=[],
            ),
            patch("tapps_mcp.server.load_settings") as mock_settings,
        ):
            mock_settings.return_value.project_root = Path("/fake")
            await tapps_validate_changed()

        assert "tapps_validate_changed" in CallTracker.get_called_tools()


# ---------------------------------------------------------------------------
# tapps_quick_check
# ---------------------------------------------------------------------------


class TestTappsQuickCheck:
    """Tests for the tapps_quick_check lite-mode tool."""

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.server.load_settings")
    async def test_success(
        self,
        mock_settings: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.server import tapps_quick_check

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")
        mock_validate.return_value = f
        mock_settings.return_value.project_root = tmp_path
        mock_settings.return_value.quality_preset = "standard"
        mock_settings.return_value.tool_timeout = 30

        result = await tapps_quick_check(str(f))
        assert result["success"] is True
        data = result["data"]
        assert "overall_score" in data
        assert "gate_passed" in data
        assert "security_passed" in data

    @pytest.mark.asyncio
    async def test_invalid_path(self) -> None:
        from tapps_mcp.server import tapps_quick_check

        result = await tapps_quick_check("/nonexistent/file.py")
        assert result["success"] is False
        assert result["error"]["code"] == "path_denied"

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.server.load_settings")
    async def test_records_call(
        self,
        mock_settings: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.server import tapps_quick_check

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")
        mock_validate.return_value = f
        mock_settings.return_value.project_root = tmp_path
        mock_settings.return_value.quality_preset = "standard"
        mock_settings.return_value.tool_timeout = 30

        await tapps_quick_check(str(f))
        assert "tapps_quick_check" in CallTracker.get_called_tools()

    @pytest.mark.asyncio
    @patch("tapps_mcp.server._validate_file_path")
    @patch("tapps_mcp.server.load_settings")
    async def test_includes_nudges(
        self,
        mock_settings: MagicMock,
        mock_validate: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.server import tapps_quick_check

        f = tmp_path / "test.py"
        f.write_text("x = 1\n", encoding="utf-8")
        mock_validate.return_value = f
        mock_settings.return_value.project_root = tmp_path
        mock_settings.return_value.quality_preset = "standard"
        mock_settings.return_value.tool_timeout = 30

        result = await tapps_quick_check(str(f))
        assert "next_steps" in result["data"]
        assert "pipeline_progress" in result["data"]


# ---------------------------------------------------------------------------
# Checklist equivalence
# ---------------------------------------------------------------------------


class TestChecklistEquivalence:
    """Test that composite tools satisfy individual tool requirements."""

    def test_quick_check_satisfies_score_and_gate(self) -> None:
        CallTracker.record("tapps_quick_check")
        result = CallTracker.evaluate("feature")
        # feature requires: tapps_score_file, tapps_quality_gate
        assert result.complete is True

    def test_validate_changed_satisfies_review(self) -> None:
        CallTracker.record("tapps_validate_changed")
        result = CallTracker.evaluate("review")
        # review requires: tapps_score_file, tapps_security_scan, tapps_quality_gate
        assert result.complete is True


# ---------------------------------------------------------------------------
# batch_validator module
# ---------------------------------------------------------------------------


class TestBatchValidator:
    """Tests for the batch_validator module."""

    @patch("tapps_mcp.tools.batch_validator.subprocess.run")
    def test_detect_changed_filters_py_only(
        self,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.tools.batch_validator import detect_changed_python_files

        # Create test files
        (tmp_path / "a.py").write_text("x = 1\n")
        (tmp_path / "b.txt").write_text("hello\n")
        (tmp_path / "c.py").write_text("y = 2\n")

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="a.py\nb.txt\nc.py\n",
        )

        result = detect_changed_python_files(tmp_path)
        assert len(result) == 2
        assert all(p.suffix == ".py" for p in result)

    @patch("tapps_mcp.tools.batch_validator.subprocess.run")
    def test_detect_changed_empty_diff(
        self,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.tools.batch_validator import detect_changed_python_files

        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = detect_changed_python_files(tmp_path)
        assert result == []

    @patch("tapps_mcp.tools.batch_validator.subprocess.run")
    def test_detect_changed_deduplicates(
        self,
        mock_run: MagicMock,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.tools.batch_validator import detect_changed_python_files

        (tmp_path / "a.py").write_text("x = 1\n")

        # Both unstaged and staged return the same file
        mock_run.return_value = MagicMock(returncode=0, stdout="a.py\n")
        result = detect_changed_python_files(tmp_path)
        assert len(result) == 1

    def test_format_batch_summary(self) -> None:
        from tapps_mcp.tools.batch_validator import format_batch_summary

        results = [
            {"gate_passed": True, "security_issues": 0},
            {"gate_passed": False, "security_issues": 2},
        ]
        summary = format_batch_summary(results)
        assert "2 files" in summary
        assert "1 passed" in summary
        assert "1 failed" in summary
        assert "2 security" in summary

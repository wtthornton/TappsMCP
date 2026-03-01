"""Tests for MCP tool handlers in server_pipeline_tools.py."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.tools.checklist import CallTracker


# ---------------------------------------------------------------------------
# tapps_session_start
# ---------------------------------------------------------------------------


class TestTappsSessionStart:
    def setup_method(self) -> None:
        CallTracker.reset()

    @pytest.mark.asyncio
    async def test_returns_success(self) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        result = await tapps_session_start()
        assert result["success"] is True
        assert result["tool"] == "tapps_session_start"
        assert "data" in result

    @pytest.mark.asyncio
    async def test_includes_server_info(self) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        result = await tapps_session_start()
        data = result["data"]
        assert "server" in data
        assert data["server"]["name"] == "TappsMCP"

    @pytest.mark.asyncio
    async def test_includes_installed_checkers(self) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        result = await tapps_session_start()
        data = result["data"]
        assert "installed_checkers" in data

    @pytest.mark.asyncio
    async def test_includes_memory_status(self) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        result = await tapps_session_start()
        data = result["data"]
        assert "memory_status" in data
        assert "enabled" in data["memory_status"]

    @pytest.mark.asyncio
    async def test_records_call(self) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_session_start

        CallTracker.reset()
        await tapps_session_start()
        assert "tapps_session_start" in CallTracker.get_called_tools()


# ---------------------------------------------------------------------------
# tapps_set_engagement_level
# ---------------------------------------------------------------------------


class TestTappsSetEngagementLevel:
    def setup_method(self) -> None:
        CallTracker.reset()

    def test_invalid_level_returns_error(self) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_set_engagement_level

        result = tapps_set_engagement_level("invalid")
        assert result["success"] is False

    def test_valid_levels_accepted(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_set_engagement_level

        # Create .git so PathValidator accepts the tmp_path as project root
        (tmp_path / ".git").mkdir(exist_ok=True)
        (tmp_path / "pyproject.toml").write_text("[project]\n")

        for level in ("high", "medium", "low"):
            with patch(
                "tapps_mcp.server_pipeline_tools.load_settings"
            ) as mock_settings:
                mock_settings.return_value = MagicMock(
                    project_root=str(tmp_path),
                )
                result = tapps_set_engagement_level(level)
                assert result["success"] is True

    def test_records_call(self) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_set_engagement_level

        CallTracker.reset()
        tapps_set_engagement_level("invalid")
        assert "tapps_set_engagement_level" in CallTracker.get_called_tools()


# ---------------------------------------------------------------------------
# tapps_upgrade
# ---------------------------------------------------------------------------


class TestTappsUpgrade:
    def setup_method(self) -> None:
        CallTracker.reset()

    @patch("tapps_mcp.server_pipeline_tools.load_settings")
    @patch("tapps_mcp.pipeline.upgrade.upgrade_pipeline")
    def test_dry_run_returns_success(
        self, mock_upgrade: MagicMock, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_upgrade

        mock_settings.return_value = MagicMock(project_root=tmp_path)
        mock_upgrade.return_value = {"success": True, "dry_run": True, "changes": []}

        result = tapps_upgrade(dry_run=True)
        assert result["success"] is True
        mock_upgrade.assert_called_once()

    @patch("tapps_mcp.server_pipeline_tools.load_settings")
    @patch("tapps_mcp.pipeline.upgrade.upgrade_pipeline")
    def test_records_call(
        self, mock_upgrade: MagicMock, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_upgrade

        mock_settings.return_value = MagicMock(project_root=tmp_path)
        mock_upgrade.return_value = {"success": True}

        CallTracker.reset()
        tapps_upgrade()
        assert "tapps_upgrade" in CallTracker.get_called_tools()


# ---------------------------------------------------------------------------
# tapps_doctor
# ---------------------------------------------------------------------------


class TestTappsDoctor:
    def setup_method(self) -> None:
        CallTracker.reset()

    @patch("tapps_mcp.server_pipeline_tools.load_settings")
    @patch("tapps_mcp.distribution.doctor.run_doctor")
    def test_returns_success(
        self, mock_doctor: MagicMock, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_doctor

        mock_settings.return_value = MagicMock(project_root=tmp_path)
        mock_doctor.return_value = {"checks": [], "passed": True}

        result = tapps_doctor()
        assert result["success"] is True
        assert result["tool"] == "tapps_doctor"

    @patch("tapps_mcp.server_pipeline_tools.load_settings")
    @patch("tapps_mcp.distribution.doctor.run_doctor")
    def test_records_call(
        self, mock_doctor: MagicMock, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_doctor

        mock_settings.return_value = MagicMock(project_root=tmp_path)
        mock_doctor.return_value = {"checks": [], "passed": True}

        CallTracker.reset()
        tapps_doctor()
        assert "tapps_doctor" in CallTracker.get_called_tools()


# ---------------------------------------------------------------------------
# tapps_init
# ---------------------------------------------------------------------------


class TestTappsInit:
    def setup_method(self) -> None:
        CallTracker.reset()

    @pytest.mark.asyncio
    @patch("tapps_mcp.server_pipeline_tools.load_settings")
    @patch("tapps_mcp.pipeline.init.bootstrap_pipeline")
    async def test_dry_run_returns_success(
        self, mock_bootstrap: MagicMock, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_init

        mock_settings.return_value = MagicMock(
            project_root=tmp_path,
            memory=MagicMock(enabled=False),
        )
        mock_bootstrap.return_value = {
            "errors": [],
            "dry_run": True,
            "files_created": [],
        }

        result = await tapps_init(dry_run=True)
        assert result["success"] is True

    @pytest.mark.asyncio
    @patch("tapps_mcp.server_pipeline_tools.load_settings")
    @patch("tapps_mcp.pipeline.init.bootstrap_pipeline")
    async def test_verify_only_returns_success(
        self, mock_bootstrap: MagicMock, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_init

        mock_settings.return_value = MagicMock(
            project_root=tmp_path,
            memory=MagicMock(enabled=False),
        )
        mock_bootstrap.return_value = {
            "errors": [],
            "verify_only": True,
        }

        result = await tapps_init(verify_only=True)
        assert result["success"] is True

    @pytest.mark.asyncio
    @patch("tapps_mcp.server_pipeline_tools.load_settings")
    @patch("tapps_mcp.pipeline.init.bootstrap_pipeline")
    async def test_records_call(
        self, mock_bootstrap: MagicMock, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_init

        mock_settings.return_value = MagicMock(
            project_root=tmp_path,
            memory=MagicMock(enabled=False),
        )
        mock_bootstrap.return_value = {"errors": []}

        CallTracker.reset()
        await tapps_init(dry_run=True)
        assert "tapps_init" in CallTracker.get_called_tools()

    @pytest.mark.asyncio
    @patch("tapps_mcp.server_pipeline_tools.load_settings")
    @patch("tapps_mcp.pipeline.init.bootstrap_pipeline")
    async def test_error_propagated(
        self, mock_bootstrap: MagicMock, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_init

        mock_settings.return_value = MagicMock(
            project_root=tmp_path,
            memory=MagicMock(enabled=False),
        )
        mock_bootstrap.return_value = {"errors": ["Something went wrong"]}

        result = await tapps_init(dry_run=True)
        assert result["success"] is False


# ---------------------------------------------------------------------------
# tapps_validate_changed
# ---------------------------------------------------------------------------


class TestTappsValidateChanged:
    def setup_method(self) -> None:
        CallTracker.reset()

    @pytest.mark.asyncio
    async def test_no_files_returns_success(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        with patch(
            "tapps_mcp.server_pipeline_tools.load_settings"
        ) as mock_settings:
            mock_settings.return_value = MagicMock(
                project_root=tmp_path,
                dependency_scan_enabled=False,
            )
            # Empty git diff = no files to validate
            with patch(
                "tapps_mcp.server_pipeline_tools._discover_changed_files",
                return_value=[],
            ):
                result = await tapps_validate_changed()
                assert result["success"] is True
                # When no files are found, the response may use different keys
                data = result["data"]
                assert "summary" in data or data.get("total_files", 0) == 0

    @pytest.mark.asyncio
    async def test_records_call(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import tapps_validate_changed

        with patch(
            "tapps_mcp.server_pipeline_tools.load_settings"
        ) as mock_settings:
            mock_settings.return_value = MagicMock(
                project_root=tmp_path,
                dependency_scan_enabled=False,
            )
            with patch(
                "tapps_mcp.server_pipeline_tools._discover_changed_files",
                return_value=[],
            ):
                CallTracker.reset()
                await tapps_validate_changed()
                assert "tapps_validate_changed" in CallTracker.get_called_tools()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestDiscoverChangedFiles:
    def test_explicit_paths(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import _discover_changed_files

        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("x = 1\n", encoding="utf-8")
        f2.write_text("y = 2\n", encoding="utf-8")

        with patch(
            "tapps_mcp.server._validate_file_path",
            side_effect=lambda p: Path(p),
        ):
            result = _discover_changed_files(
                f"{f1},{f2}",
                "HEAD",
                tmp_path,
            )
        assert len(result) == 2

    def test_empty_paths_no_git(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import _discover_changed_files

        # No git repo in tmp_path, so detect_changed_python_files returns []
        result = _discover_changed_files("", "HEAD", tmp_path)
        assert isinstance(result, list)

    def test_skips_non_py_files(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import _discover_changed_files

        with patch(
            "tapps_mcp.server._validate_file_path",
            side_effect=lambda p: Path(p),
        ):
            result = _discover_changed_files(
                "readme.md,data.json",
                "HEAD",
                tmp_path,
            )
        assert len(result) == 0


class TestCollectResults:
    def test_normal_results(self) -> None:
        from tapps_mcp.server_pipeline_tools import _collect_results

        paths = [Path("a.py"), Path("b.py")]
        raw = [{"score": 80}, {"score": 90}]
        results = _collect_results(raw, paths)
        assert len(results) == 2
        assert results[0]["score"] == 80

    def test_exception_results(self) -> None:
        from tapps_mcp.server_pipeline_tools import _collect_results

        paths = [Path("a.py")]
        raw: list = [RuntimeError("boom")]
        results = _collect_results(raw, paths)
        assert len(results) == 1
        assert "errors" in results[0]
        assert "boom" in results[0]["errors"][0]


class TestWriteValidateOkMarker:
    def test_creates_marker_file(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import _write_validate_ok_marker

        _write_validate_ok_marker(tmp_path)
        marker = tmp_path / ".tapps-mcp" / "sessions" / "last_validate_ok"
        assert marker.exists()

    def test_no_error_on_readonly(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import _write_validate_ok_marker

        # Should not raise even if directory creation fails
        with patch("pathlib.Path.mkdir", side_effect=OSError("permission denied")):
            _write_validate_ok_marker(tmp_path)  # no exception

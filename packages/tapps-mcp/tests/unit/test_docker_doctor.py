"""Tests for Docker health checks in the tapps-mcp doctor module (Epic 46.7)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.distribution.doctor import (
    CheckResult,
    _collect_docker_checks,
    _is_docker_available,
    check_docker_companions,
    check_docker_daemon,
    check_docker_images,
    check_docker_mcp_config,
    check_docker_mcp_toolkit,
    run_doctor_structured,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_process_mock(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> AsyncMock:
    """Create an AsyncMock for asyncio.create_subprocess_exec."""
    proc = AsyncMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(
        return_value=(stdout.encode("utf-8"), stderr.encode("utf-8"))
    )
    return proc


def _patch_subprocess(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> Any:
    """Patch asyncio.create_subprocess_exec to return a mock process."""
    proc = _make_process_mock(returncode, stdout, stderr)
    return patch(
        "tapps_mcp.distribution.doctor.asyncio.create_subprocess_exec",
        return_value=proc,
    )


# ---------------------------------------------------------------------------
# check_docker_daemon
# ---------------------------------------------------------------------------


class TestCheckDockerDaemon:
    """Tests for check_docker_daemon."""

    def test_daemon_running(self) -> None:
        with _patch_subprocess(returncode=0, stdout="27.5.1"):
            result = asyncio.run(check_docker_daemon())
        assert result.ok is True
        assert "27.5.1" in result.message

    def test_daemon_not_running(self) -> None:
        with _patch_subprocess(returncode=1, stderr="Cannot connect to Docker daemon"):
            result = asyncio.run(check_docker_daemon())
        assert result.ok is False
        assert "not running" in result.message

    def test_docker_not_installed(self) -> None:
        with patch(
            "tapps_mcp.distribution.doctor.asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("docker not found"),
        ):
            result = asyncio.run(check_docker_daemon())
        assert result.ok is False
        assert "not running" in result.message

    def test_docker_timeout(self) -> None:
        async def _timeout_exec(*args: Any, **kwargs: Any) -> Any:
            raise asyncio.TimeoutError

        with patch(
            "tapps_mcp.distribution.doctor.asyncio.create_subprocess_exec",
            side_effect=_timeout_exec,
        ):
            result = asyncio.run(check_docker_daemon())
        assert result.ok is False


# ---------------------------------------------------------------------------
# check_docker_mcp_toolkit
# ---------------------------------------------------------------------------


class TestCheckDockerMcpToolkit:
    """Tests for check_docker_mcp_toolkit."""

    def test_toolkit_installed(self) -> None:
        with _patch_subprocess(returncode=0, stdout="Docker MCP Toolkit v0.2.0"):
            result = asyncio.run(check_docker_mcp_toolkit())
        assert result.ok is True
        assert "installed" in result.message

    def test_toolkit_not_installed(self) -> None:
        with _patch_subprocess(
            returncode=1, stderr="'mcp' is not a docker command"
        ):
            result = asyncio.run(check_docker_mcp_toolkit())
        assert result.ok is False
        assert "not installed" in result.message


# ---------------------------------------------------------------------------
# check_docker_images
# ---------------------------------------------------------------------------


class TestCheckDockerImages:
    """Tests for check_docker_images."""

    def test_both_images_present(self) -> None:
        with _patch_subprocess(returncode=0, stdout="[{}]"):
            result = asyncio.run(
                check_docker_images("tapps-mcp:latest", "docs-mcp:latest")
            )
        assert result.ok is True
        assert "present" in result.message.lower()

    def test_one_image_missing(self) -> None:
        call_count = 0

        async def _side_effect(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_process_mock(0, "[{}]")
            return _make_process_mock(1, "", "No such image")

        with patch(
            "tapps_mcp.distribution.doctor.asyncio.create_subprocess_exec",
            side_effect=_side_effect,
        ):
            result = asyncio.run(
                check_docker_images("tapps-mcp:latest", "docs-mcp:latest")
            )
        assert result.ok is False
        assert "docs-mcp:latest" in result.message

    def test_both_images_missing(self) -> None:
        with _patch_subprocess(returncode=1, stderr="No such image"):
            result = asyncio.run(
                check_docker_images("tapps-mcp:latest", "docs-mcp:latest")
            )
        assert result.ok is False
        assert "tapps-mcp:latest" in result.message
        assert "docs-mcp:latest" in result.message


# ---------------------------------------------------------------------------
# check_docker_companions
# ---------------------------------------------------------------------------


class TestCheckDockerCompanions:
    """Tests for check_docker_companions."""

    def test_no_companions_configured(self) -> None:
        result = asyncio.run(check_docker_companions([]))
        assert result.ok is True
        assert "No companion" in result.message

    def test_all_companions_present(self) -> None:
        with _patch_subprocess(returncode=0, stdout="[{}]"):
            result = asyncio.run(check_docker_companions(["context7"]))
        assert result.ok is True
        assert "context7" in result.message

    def test_companion_missing(self) -> None:
        with _patch_subprocess(returncode=1, stderr="No such image"):
            result = asyncio.run(check_docker_companions(["context7"]))
        assert result.ok is False
        assert "context7" in result.message
        assert "docker pull" in result.detail


# ---------------------------------------------------------------------------
# check_docker_mcp_config
# ---------------------------------------------------------------------------


class TestCheckDockerMcpConfig:
    """Tests for check_docker_mcp_config."""

    def test_docker_config_present_with_profile(self, tmp_path: Path) -> None:
        config = {
            "mcpServers": {
                "tapps-mcp": {
                    "command": "docker",
                    "args": ["mcp", "gateway", "run", "--profile", "tapps-standard"],
                }
            }
        }
        (tmp_path / ".mcp.json").write_text(json.dumps(config), encoding="utf-8")
        result = check_docker_mcp_config(tmp_path, "tapps-standard")
        assert result.ok is True
        assert "tapps-standard" in result.message

    def test_docker_config_wrong_profile(self, tmp_path: Path) -> None:
        config = {
            "mcpServers": {
                "tapps-mcp": {
                    "command": "docker",
                    "args": ["mcp", "gateway", "run", "--profile", "other-profile"],
                }
            }
        }
        (tmp_path / ".mcp.json").write_text(json.dumps(config), encoding="utf-8")
        result = check_docker_mcp_config(tmp_path, "tapps-standard")
        assert result.ok is False
        assert "tapps-standard" in result.detail

    def test_no_docker_config(self, tmp_path: Path) -> None:
        config = {
            "mcpServers": {
                "tapps-mcp": {"command": "tapps-mcp"}
            }
        }
        (tmp_path / ".mcp.json").write_text(json.dumps(config), encoding="utf-8")
        result = check_docker_mcp_config(tmp_path, "tapps-standard")
        assert result.ok is False
        assert "No MCP config references Docker" in result.message

    def test_no_config_files(self, tmp_path: Path) -> None:
        result = check_docker_mcp_config(tmp_path, "tapps-standard")
        assert result.ok is False

    def test_claude_json_fallback(self, tmp_path: Path) -> None:
        """Falls back to .claude.json when .mcp.json doesn't have docker config."""
        config = {
            "mcpServers": {
                "tapps-mcp": {
                    "command": "docker",
                    "args": ["mcp", "gateway", "run", "--profile", "tapps-standard"],
                }
            }
        }
        (tmp_path / ".claude.json").write_text(json.dumps(config), encoding="utf-8")
        result = check_docker_mcp_config(tmp_path, "tapps-standard")
        assert result.ok is True


# ---------------------------------------------------------------------------
# _collect_docker_checks
# ---------------------------------------------------------------------------


class TestCollectDockerChecks:
    """Tests for _collect_docker_checks."""

    def test_skips_remaining_when_daemon_down(self) -> None:
        with _patch_subprocess(returncode=1, stderr="daemon not running"):
            results = asyncio.run(
                _collect_docker_checks(
                    project_root=Path("/tmp/test"),
                    image="tapps:latest",
                    docs_image="docs:latest",
                    companions=["context7"],
                    profile="tapps-standard",
                )
            )
        # Only daemon check should be present
        assert len(results) == 1
        assert results[0].name == "Docker daemon"
        assert results[0].ok is False

    def test_runs_all_checks_when_daemon_up(self, tmp_path: Path) -> None:
        with _patch_subprocess(returncode=0, stdout="27.5.1"):
            results = asyncio.run(
                _collect_docker_checks(
                    project_root=tmp_path,
                    image="tapps:latest",
                    docs_image="docs:latest",
                    companions=["context7"],
                    profile="tapps-standard",
                )
            )
        # All 5 checks should run
        assert len(results) == 5
        names = [r.name for r in results]
        assert "Docker daemon" in names
        assert "Docker MCP Toolkit" in names
        assert "Docker images" in names
        assert "Docker companions" in names
        assert "Docker MCP config" in names


# ---------------------------------------------------------------------------
# _is_docker_available
# ---------------------------------------------------------------------------


class TestIsDockerAvailable:
    """Tests for _is_docker_available."""

    def test_docker_on_path(self) -> None:
        with patch("tapps_mcp.distribution.doctor.shutil.which", return_value="/usr/bin/docker"):
            assert _is_docker_available() is True

    def test_docker_not_on_path(self) -> None:
        with patch("tapps_mcp.distribution.doctor.shutil.which", return_value=None):
            assert _is_docker_available() is False


# ---------------------------------------------------------------------------
# run_doctor_structured integration (Docker section)
# ---------------------------------------------------------------------------


class TestRunDoctorStructuredDocker:
    """Tests for Docker checks in run_doctor_structured output."""

    def test_no_docker_section_when_disabled(self, tmp_path: Path) -> None:
        """Docker checks are skipped when docker.enabled=False and docker not on PATH."""
        mock_settings = MagicMock()
        mock_settings.docker.enabled = False

        with (
            patch("tapps_mcp.distribution.doctor.Path.home", return_value=tmp_path),
            patch("tapps_mcp.distribution.doctor.shutil.which", return_value=None),
            patch(
                "tapps_core.config.settings.load_settings",
                return_value=mock_settings,
            ),
        ):
            result = run_doctor_structured(project_root=str(tmp_path))

        assert "docker_checks" not in result

    def test_docker_section_present_when_enabled(self, tmp_path: Path) -> None:
        """Docker checks appear when docker.enabled=True."""
        mock_settings = MagicMock()
        mock_settings.docker.enabled = True
        mock_settings.docker.image = "tapps:latest"
        mock_settings.docker.docs_image = "docs:latest"
        mock_settings.docker.companions = []
        mock_settings.docker.profile = "tapps-standard"

        with (
            patch("tapps_mcp.distribution.doctor.Path.home", return_value=tmp_path),
            patch("tapps_mcp.distribution.doctor.shutil.which", return_value=None),
            patch(
                "tapps_core.config.settings.load_settings",
                return_value=mock_settings,
            ),
            _patch_subprocess(returncode=1, stderr="daemon not running"),
        ):
            result = run_doctor_structured(project_root=str(tmp_path))

        assert "docker_checks" in result
        dc = result["docker_checks"]
        assert dc["fail_count"] >= 1
        assert len(dc["checks"]) >= 1

    def test_docker_section_when_docker_on_path(self, tmp_path: Path) -> None:
        """Docker checks appear when docker is on PATH even if not enabled in settings."""
        mock_settings = MagicMock()
        mock_settings.docker.enabled = False
        mock_settings.docker.image = "tapps:latest"
        mock_settings.docker.docs_image = "docs:latest"
        mock_settings.docker.companions = []
        mock_settings.docker.profile = "tapps-standard"

        def _which(name: str) -> str | None:
            if name == "docker":
                return "/usr/bin/docker"
            return None

        with (
            patch("tapps_mcp.distribution.doctor.Path.home", return_value=tmp_path),
            patch("tapps_mcp.distribution.doctor.shutil.which", side_effect=_which),
            patch(
                "tapps_core.config.settings.load_settings",
                return_value=mock_settings,
            ),
            _patch_subprocess(returncode=0, stdout="27.5.1"),
        ):
            result = run_doctor_structured(project_root=str(tmp_path))

        assert "docker_checks" in result
        dc = result["docker_checks"]
        assert dc["pass_count"] >= 1

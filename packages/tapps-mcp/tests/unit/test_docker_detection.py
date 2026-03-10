"""Tests for Docker detection and companion recommendations in pipeline.init."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from tapps_mcp.pipeline.init import (
    _detect_docker,
    _recommend_companions,
)


class TestDetectDocker:
    """Tests for _detect_docker async function."""

    def test_no_docker_on_path(self) -> None:
        """When docker is not on PATH, returns all-false result."""
        with patch("shutil.which", return_value=None):
            result = asyncio.run(_detect_docker())
        assert result["docker_available"] is False
        assert result["docker_mcp_available"] is False
        assert result["docker_version"] is None
        assert result["installed_servers"] == []

    def test_docker_available(self) -> None:
        """When docker info succeeds, docker_available is True."""
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"24.0.7\n", b""))
        mock_proc.returncode = 0

        # docker mcp version fails
        mock_proc_mcp = AsyncMock()
        mock_proc_mcp.communicate = AsyncMock(return_value=(b"", b"unknown command"))
        mock_proc_mcp.returncode = 1

        call_count = 0

        async def fake_exec(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_proc
            return mock_proc_mcp

        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("asyncio.create_subprocess_exec", side_effect=fake_exec),
        ):
            result = asyncio.run(_detect_docker())

        assert result["docker_available"] is True
        assert result["docker_version"] == "24.0.7"
        assert result["docker_mcp_available"] is False

    def test_docker_and_mcp_available(self) -> None:
        """When both docker info and docker mcp version succeed."""
        mock_proc_info = AsyncMock()
        mock_proc_info.communicate = AsyncMock(return_value=(b"25.0.1\n", b""))
        mock_proc_info.returncode = 0

        mock_proc_mcp = AsyncMock()
        mock_proc_mcp.communicate = AsyncMock(return_value=(b"1.0.0\n", b""))
        mock_proc_mcp.returncode = 0

        call_count = 0

        async def fake_exec(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_proc_info
            return mock_proc_mcp

        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("asyncio.create_subprocess_exec", side_effect=fake_exec),
        ):
            result = asyncio.run(_detect_docker())

        assert result["docker_available"] is True
        assert result["docker_version"] == "25.0.1"
        assert result["docker_mcp_available"] is True

    def test_docker_info_timeout(self) -> None:
        """When docker info times out, returns early."""

        async def timeout_exec(*args: Any, **kwargs: Any) -> Any:
            raise asyncio.TimeoutError

        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("asyncio.create_subprocess_exec", side_effect=timeout_exec),
        ):
            result = asyncio.run(_detect_docker())

        assert result["docker_available"] is False
        assert result["docker_mcp_available"] is False

    def test_docker_info_oserror(self) -> None:
        """When docker info raises OSError, returns early."""

        async def oserror_exec(*args: Any, **kwargs: Any) -> Any:
            raise OSError("permission denied")

        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("asyncio.create_subprocess_exec", side_effect=oserror_exec),
        ):
            result = asyncio.run(_detect_docker())

        assert result["docker_available"] is False

    def test_docker_info_nonzero_returncode(self) -> None:
        """When docker info returns non-zero, docker_available stays False."""
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"error"))
        mock_proc.returncode = 1

        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            result = asyncio.run(_detect_docker())

        assert result["docker_available"] is False

    def test_docker_mcp_timeout(self) -> None:
        """When docker mcp version times out, mcp_available stays False."""
        mock_proc_info = AsyncMock()
        mock_proc_info.communicate = AsyncMock(return_value=(b"24.0.0\n", b""))
        mock_proc_info.returncode = 0

        call_count = 0

        async def fake_exec(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_proc_info
            raise asyncio.TimeoutError

        with (
            patch("shutil.which", return_value="/usr/bin/docker"),
            patch("asyncio.create_subprocess_exec", side_effect=fake_exec),
        ):
            result = asyncio.run(_detect_docker())

        assert result["docker_available"] is True
        assert result["docker_mcp_available"] is False


class TestRecommendCompanions:
    """Tests for _recommend_companions function."""

    def test_reports_configured_status(self) -> None:
        """Companions are reported as 'configured' not 'installed'."""
        docker_result: dict[str, Any] = {"installed_servers": []}
        companions = ["context7", "github"]
        rec = _recommend_companions(docker_result, companions)
        assert rec["status"] == "configured"
        assert rec["configured"] == ["context7", "github"]
        assert "installed" not in rec
        assert "missing" not in rec

    def test_includes_install_commands(self) -> None:
        """Install commands are provided for all configured companions."""
        docker_result: dict[str, Any] = {"installed_servers": []}
        companions = ["context7", "github"]
        rec = _recommend_companions(docker_result, companions)
        assert len(rec["install_commands"]) == 2

    def test_empty_companions(self) -> None:
        docker_result: dict[str, Any] = {"installed_servers": ["context7"]}
        rec = _recommend_companions(docker_result, [])
        assert rec["configured"] == []
        assert rec["install_commands"] == []
        assert rec["status"] == "configured"

    def test_install_command_format(self) -> None:
        docker_result: dict[str, Any] = {"installed_servers": []}
        companions = ["myserver"]
        rec = _recommend_companions(docker_result, companions)
        assert rec["install_commands"] == [
            "docker mcp profile server add tapps-standard --server catalog://myserver"
        ]

    def test_docker_result_ignored(self) -> None:
        """docker_result installed_servers is ignored -- we report config only."""
        docker_result: dict[str, Any] = {"installed_servers": ["extra", "context7"]}
        companions = ["context7"]
        rec = _recommend_companions(docker_result, companions)
        assert rec["configured"] == ["context7"]
        assert rec["status"] == "configured"

    def test_includes_note_about_runtime(self) -> None:
        """Result includes a note about Docker Desktop dependency."""
        docker_result: dict[str, Any] = {}
        companions = ["context7"]
        rec = _recommend_companions(docker_result, companions)
        assert "note" in rec
        assert "Docker Desktop" in rec["note"]

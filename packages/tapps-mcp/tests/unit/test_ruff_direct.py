"""Tests for tools.ruff_direct — synchronous ruff in thread pool."""

from unittest.mock import patch

import pytest

from tapps_mcp.tools.ruff_direct import _run_ruff_sync, run_ruff_check_direct


class TestRunRuffSync:
    @patch("tapps_mcp.tools.ruff_direct.subprocess.run")
    def test_returns_issues_on_output(self, mock_run):
        import subprocess

        mock_run.return_value = subprocess.CompletedProcess(
            args=["ruff"],
            returncode=1,
            stdout=(
                '[{"code":"E501","message":"line too long",'
                '"filename":"t.py","location":{"row":1,"column":80}}]'
            ),
            stderr="",
        )
        issues = _run_ruff_sync("test.py")
        assert len(issues) == 1
        assert issues[0].code == "E501"

    @patch("tapps_mcp.tools.ruff_direct.subprocess.run")
    def test_returns_empty_on_no_output(self, mock_run):
        import subprocess

        mock_run.return_value = subprocess.CompletedProcess(
            args=["ruff"],
            returncode=0,
            stdout="",
            stderr="",
        )
        issues = _run_ruff_sync("test.py")
        assert issues == []

    @patch("tapps_mcp.tools.ruff_direct.subprocess.run", side_effect=FileNotFoundError)
    def test_returns_empty_when_not_found(self, _mock):
        issues = _run_ruff_sync("test.py")
        assert issues == []

    @patch("tapps_mcp.tools.ruff_direct.subprocess.run")
    def test_returns_empty_on_timeout(self, mock_run):
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ruff", timeout=30)
        issues = _run_ruff_sync("test.py")
        assert issues == []


class TestRunRuffCheckDirect:
    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.ruff_direct._run_ruff_sync")
    async def test_delegates_to_sync(self, mock_sync):
        mock_sync.return_value = []
        result = await run_ruff_check_direct("test.py", cwd="/tmp", timeout=10)
        assert result == []
        mock_sync.assert_called_once_with("test.py", cwd="/tmp", timeout=10)

    @pytest.mark.asyncio
    @patch("tapps_mcp.tools.ruff_direct.subprocess.run")
    async def test_async_returns_issues(self, mock_run):
        import subprocess

        mock_run.return_value = subprocess.CompletedProcess(
            args=["ruff"],
            returncode=1,
            stdout=(
                '[{"code":"F401","message":"unused import",'
                '"filename":"t.py","location":{"row":1,"column":1}}]'
            ),
            stderr="",
        )
        issues = await run_ruff_check_direct("test.py")
        assert len(issues) == 1
        assert issues[0].code == "F401"

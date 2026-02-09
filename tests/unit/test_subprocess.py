"""Tests for tools.subprocess_utils and tools.subprocess_runner."""

import platform
from unittest.mock import patch

from tapps_mcp.tools.subprocess_runner import run_command
from tapps_mcp.tools.subprocess_utils import CommandResult, wrap_windows_cmd_shim


class TestWrapWindowsCmdShim:
    def test_empty_argv(self):
        assert wrap_windows_cmd_shim([]) == []

    @patch("tapps_mcp.tools.subprocess_utils.platform.system", return_value="Linux")
    def test_non_windows_passthrough(self, _mock):
        result = wrap_windows_cmd_shim(["ruff", "check", "."])
        assert result == ["ruff", "check", "."]

    @patch("tapps_mcp.tools.subprocess_utils.platform.system", return_value="Windows")
    def test_cmd_extension_wrapped(self, _mock):
        result = wrap_windows_cmd_shim(["ruff.cmd", "check", "."])
        assert result == ["cmd", "/c", "ruff.cmd", "check", "."]

    @patch("tapps_mcp.tools.subprocess_utils.platform.system", return_value="Windows")
    @patch("tapps_mcp.tools.subprocess_utils.shutil.which", return_value=None)
    def test_no_cmd_extension_passthrough(self, _which, _sys):
        result = wrap_windows_cmd_shim(["python", "-c", "pass"])
        assert result == ["python", "-c", "pass"]


class TestCommandResult:
    def test_success_property(self):
        assert CommandResult(returncode=0).success is True
        assert CommandResult(returncode=1).success is False
        assert CommandResult(returncode=-1).success is False


class TestRunCommand:
    def test_run_echo(self):
        if platform.system() == "Windows":
            result = run_command(["cmd", "/c", "echo", "hello"], timeout=10)
        else:
            result = run_command(["echo", "hello"], timeout=10)
        assert result.success is True
        assert "hello" in result.stdout

    def test_command_not_found(self):
        result = run_command(["nonexistent_tool_xyz_123"], timeout=5)
        assert result.success is False
        assert "not found" in result.stderr.lower() or result.returncode != 0

    def test_timeout(self):
        # Use python -c sleep for cross-platform timeout testing
        cmd = ["python", "-c", "import time; time.sleep(10)"]
        result = run_command(cmd, timeout=1)
        assert result.timed_out is True
        assert result.success is False

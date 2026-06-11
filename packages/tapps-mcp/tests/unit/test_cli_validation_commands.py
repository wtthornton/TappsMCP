"""CLI parity tests for validation commands (TAP-3586)."""

from __future__ import annotations

from click.testing import CliRunner

from tapps_mcp.cli import main


class TestValidationCliCommands:
    def test_quick_check_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["quick-check", "--help"])
        assert result.exit_code == 0
        assert "--file-path" in result.output

    def test_validate_changed_accepts_file_paths(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["validate-changed", "--help"])
        assert result.exit_code == 0
        assert "--file-paths" in result.output or "--paths" in result.output

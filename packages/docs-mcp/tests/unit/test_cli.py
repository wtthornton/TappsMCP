"""Tests for DocsMCP CLI."""

from __future__ import annotations

from click.testing import CliRunner

from docs_mcp.cli import cli


class TestCLI:
    def test_cli_version(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_cli_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "DocsMCP" in result.output

    def test_serve_command_exists(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["serve", "--help"])
        assert result.exit_code == 0
        assert "transport" in result.output.lower()

    def test_doctor_command_exists(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["doctor", "--help"])
        assert result.exit_code == 0

    def test_scan_command_exists(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["scan", "--help"])
        assert result.exit_code == 0

    def test_generate_command_exists(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["generate", "--help"])
        assert result.exit_code == 0

    def test_version_command_exists(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["version"])
        assert result.exit_code == 0
        assert "docsmcp" in result.output.lower()

    def test_doctor_runs(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["doctor"])
        assert result.exit_code == 0
        assert "DocsMCP" in result.output
        assert "Done" in result.output

    def test_generate_not_implemented(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["generate"])
        assert result.exit_code == 0
        assert "Not yet implemented" in result.output

"""Tests for the extracted validation CLI commands (covers cli_validation)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from tapps_mcp.cli_validation import quick_check_cmd, validate_changed_cmd
from tapps_mcp.tools.validate_changed_cli_exit import validate_changed_cli_exit_code


def test_validate_changed_help() -> None:
    runner = CliRunner()
    result = runner.invoke(validate_changed_cmd, ["--help"])
    assert result.exit_code == 0
    assert "--file-paths" in result.output or "--paths" in result.output


def test_quick_check_help() -> None:
    runner = CliRunner()
    result = runner.invoke(quick_check_cmd, ["--help"])
    assert result.exit_code == 0
    assert "--file-path" in result.output


def test_validate_changed_empty_gate_exits_zero() -> None:
    runner = CliRunner()
    mock_result = {
        "success": True,
        "data": {
            "files_validated": 0,
            "all_gates_passed": False,
            "summary": "No changed scorable files found — inconclusive, nothing was gated.",
            "summary_rows": [],
        },
    }
    with patch(
        "tapps_mcp.server_pipeline_tools.tapps_validate_changed",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        result = runner.invoke(validate_changed_cmd, ["--quick"])
    assert result.exit_code == 0
    assert validate_changed_cli_exit_code(mock_result["data"]) == 0

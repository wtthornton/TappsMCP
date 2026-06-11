"""CLI parity tests for validation commands (TAP-3586)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

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

    def test_validate_changed_exits_nonzero_on_blocking_judge_fail(self) -> None:
        runner = CliRunner()
        mock_result = {
            "success": True,
            "data": {
                "summary": "1 file validated",
                "summary_rows": [
                    "PASS   foo.py  score=100.0",
                    "FAIL   judge:audit  fail",
                ],
                "all_gates_passed": False,
                "judges_passed": False,
            },
        }
        with patch(
            "tapps_mcp.server_pipeline_tools.tapps_validate_changed",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = runner.invoke(main, ["validate-changed", "--quick"])
        assert result.exit_code == 1
        assert "judge:audit" in result.output

"""CLI parity tests for validation commands (TAP-3586)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from tapps_mcp.cli import main
from tapps_mcp.tools.validate_changed_cli_exit import validate_changed_cli_exit_code


class TestValidateChangedCliExitCode:
    """Stamp/docs-only PRs must not fail CI when nothing scorable changed."""

    def test_zero_files_auto_detect_exits_zero(self) -> None:
        assert (
            validate_changed_cli_exit_code(
                {
                    "files_validated": 0,
                    "all_gates_passed": False,
                    "summary": "No changed scorable files found — inconclusive, nothing was gated.",
                },
                explicit_paths=False,
            )
            == 0
        )

    def test_zero_files_with_failed_judges_exits_one(self) -> None:
        assert (
            validate_changed_cli_exit_code(
                {
                    "files_validated": 0,
                    "all_gates_passed": False,
                    "judges_passed": False,
                },
                explicit_paths=False,
            )
            == 1
        )

    def test_zero_files_with_explicit_paths_exits_one(self) -> None:
        assert (
            validate_changed_cli_exit_code(
                {
                    "files_validated": 0,
                    "all_gates_passed": False,
                    "path_hint": "Explicit paths provided but none validated.",
                },
                explicit_paths=True,
            )
            == 1
        )

    def test_gate_fail_exits_one(self) -> None:
        assert (
            validate_changed_cli_exit_code(
                {"files_validated": 1, "all_gates_passed": False},
                explicit_paths=False,
            )
            == 1
        )

    def test_all_pass_exits_zero(self) -> None:
        assert (
            validate_changed_cli_exit_code(
                {"files_validated": 2, "all_gates_passed": True, "judges_passed": True},
                explicit_paths=False,
            )
            == 0
        )


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

    def test_validate_changed_exits_zero_when_nothing_to_gate(self) -> None:
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
            result = runner.invoke(main, ["validate-changed", "--quick"])
        assert result.exit_code == 0

    def test_validate_changed_exits_nonzero_on_blocking_judge_fail(self) -> None:
        runner = CliRunner()
        mock_result = {
            "success": True,
            "data": {
                "summary": "1 file validated",
                "files_validated": 1,
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

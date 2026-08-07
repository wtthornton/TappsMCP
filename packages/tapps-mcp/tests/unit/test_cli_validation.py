"""Tests for the extracted validation CLI commands (covers cli_validation)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from tapps_mcp.cli_validation import (
    quick_check_cmd,
    session_budget_cmd,
    validate_changed_cmd,
)
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


def _write_transcript(tmp_path: Path) -> Path:
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        '{"message":{"content":[{"type":"tool_use"}]}}\n'
        '{"message":{"content":[{"type":"text"}]}}\n',
        encoding="utf-8",
    )
    return transcript


def test_session_budget_under_threshold_reports_not_over(tmp_path: Path) -> None:
    transcript = _write_transcript(tmp_path)
    runner = CliRunner()
    result = runner.invoke(session_budget_cmd, ["--transcript", str(transcript), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["over"] is False
    assert payload["message_count"] == 2
    assert payload["tool_use_count"] == 1


def test_session_budget_over_threshold_flags_rotation(tmp_path: Path) -> None:
    transcript = _write_transcript(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        session_budget_cmd, ["--transcript", str(transcript), "--threshold", "1"]
    )
    assert result.exit_code == 0
    assert "OVER" in result.output
    assert "session rotation" in result.output


def test_session_budget_read_failure_is_not_double_wrapped(tmp_path: Path) -> None:
    """An OSError mid-read surfaces once, not re-wrapped by the outer handler."""
    transcript = _write_transcript(tmp_path)
    runner = CliRunner()
    with patch.object(Path, "open", side_effect=OSError("disk gone")):
        result = runner.invoke(session_budget_cmd, ["--transcript", str(transcript)])
    assert result.exit_code == 1
    assert "Failed to read transcript" in result.output
    assert "disk gone" in result.output
    # Click renders its own "Error: " prefix; the handler must not add a second.
    assert result.output.count("Error:") == 1

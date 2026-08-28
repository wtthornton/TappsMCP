"""Exact-name coverage tests for cli_ops_audit."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from tapps_mcp.cli_ops_audit import (
    audit_fleet_cmd,
    auto_capture,
    pipeline_mark_cmd,
    usage_gaps_hint_cmd,
)


def test_usage_gaps_hint_help() -> None:
    result = CliRunner().invoke(usage_gaps_hint_cmd, ["--help"])
    assert result.exit_code == 0
    assert "project-root" in result.output


def test_audit_fleet_help() -> None:
    result = CliRunner().invoke(audit_fleet_cmd, ["--help"])
    assert result.exit_code == 0
    assert "--period" in result.output


def test_pipeline_mark_help() -> None:
    result = CliRunner().invoke(pipeline_mark_cmd, ["--help"])
    assert result.exit_code == 0
    assert "contract-verified" in result.output


def test_auto_capture_help() -> None:
    result = CliRunner().invoke(auto_capture, ["--help"])
    assert result.exit_code == 0
    assert "--transcript-turns" in result.output
    assert "--transcript-max-bytes" in result.output


def test_auto_capture_echoes_json_and_warns_when_nothing_saved(tmp_path) -> None:
    fake_result = {"saved": 0, "facts": 0, "reason": "no_context", "session_id": "sess-1"}
    with patch(
        "tapps_mcp.memory.auto_capture.run_auto_capture",
        new=AsyncMock(return_value=fake_result),
    ):
        result = CliRunner().invoke(
            auto_capture,
            ["--project-root", str(tmp_path)],
            input="{}",
        )
    assert result.exit_code == 0
    lines = result.output.strip().splitlines()
    assert json.loads(lines[0]) == fake_result
    assert "WARNING: auto-capture saved 0 facts (reason=no_context)" in result.output


def test_auto_capture_no_warning_when_facts_saved(tmp_path) -> None:
    fake_result = {"saved": 2, "facts": 2, "reason": None, "session_id": "sess-2"}
    with patch(
        "tapps_mcp.memory.auto_capture.run_auto_capture",
        new=AsyncMock(return_value=fake_result),
    ):
        result = CliRunner().invoke(
            auto_capture,
            ["--project-root", str(tmp_path)],
            input="{}",
        )
    assert result.exit_code == 0
    assert json.loads(result.output.strip()) == fake_result
    assert "WARNING" not in result.output

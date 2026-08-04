"""Exact-name coverage tests for cli_ops_audit."""

from __future__ import annotations

from click.testing import CliRunner

from tapps_mcp.cli_ops_audit import (
    audit_fleet_cmd,
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

"""Exact-name coverage tests for cli_ops_build."""

from __future__ import annotations

from click.testing import CliRunner

from tapps_mcp.cli_ops_build import (
    build_plugin,
    rollback,
    show_config,
    validate_skills_cmd,
)


def test_build_plugin_help() -> None:
    result = CliRunner().invoke(build_plugin, ["--help"])
    assert result.exit_code == 0
    assert "--output-dir" in result.output


def test_validate_skills_help() -> None:
    result = CliRunner().invoke(validate_skills_cmd, ["--help"])
    assert result.exit_code == 0
    assert "--platform" in result.output


def test_rollback_help() -> None:
    result = CliRunner().invoke(rollback, ["--help"])
    assert result.exit_code == 0
    assert "--list" in result.output or "list" in result.output.lower()


def test_show_config_help() -> None:
    result = CliRunner().invoke(show_config, ["--help"])
    assert result.exit_code == 0
    assert "project-root" in result.output

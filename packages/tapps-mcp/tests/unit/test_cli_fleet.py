"""Tests for the extracted fleet CLI group (exact-name coverage for cli_fleet)."""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from tapps_mcp.cli_fleet import fleet_group, fleet_start, fleet_stop


def test_fleet_group_help() -> None:
    runner = CliRunner()
    result = runner.invoke(fleet_group, ["--help"])
    assert result.exit_code == 0
    assert "start" in result.output
    assert "restart" in result.output


def test_fleet_start_echoes_and_exits_on_errors() -> None:
    runner = CliRunner()
    with (
        patch("tapps_mcp.distribution.fleet_control.ensure_fleet_env_file"),
        patch(
            "tapps_mcp.distribution.fleet_control.start_fleet",
            return_value={
                "code_root": "/tmp/x",
                "host": "127.0.0.1",
                "started": ["nlt-build"],
                "skipped": [],
                "errors": ["boom"],
            },
        ),
    ):
        result = runner.invoke(fleet_start, [])
    assert result.exit_code == 1
    assert "boom" in result.output


def test_fleet_stop_reports_stopped() -> None:
    runner = CliRunner()
    with patch(
        "tapps_mcp.distribution.fleet_control.stop_fleet",
        return_value={"stopped": ["nlt-build"], "missing": []},
    ):
        result = runner.invoke(fleet_stop, [])
    assert result.exit_code == 0
    assert "nlt-build" in result.output

"""Tests for the extracted handoff CLI group (covers cli_handoff)."""

from __future__ import annotations

from click.testing import CliRunner

from tapps_mcp.cli_handoff import handoff_group, handoff_write


def test_handoff_group_help() -> None:
    runner = CliRunner()
    result = runner.invoke(handoff_group, ["--help"])
    assert result.exit_code == 0
    assert "write" in result.output


def test_handoff_write_requires_input() -> None:
    runner = CliRunner()
    result = runner.invoke(handoff_write, [], input="")
    assert result.exit_code == 2
    assert (
        "Provide --file" in result.output
        or "stdin" in result.output
        or "empty" in result.output.lower()
    )

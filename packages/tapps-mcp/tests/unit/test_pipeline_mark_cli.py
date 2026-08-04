"""CLI smoke for ``tapps-mcp pipeline-mark`` (TAP-5543/5548)."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from tapps_mcp.cli import main
from tapps_mcp.tools.contract_telemetry import mark_recorded_recently


def test_pipeline_mark_contract_verified(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["pipeline-mark", "contract-verified", "--project-root", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert "contract-verified" in result.output
    assert mark_recorded_recently(tmp_path, kind="contract-verified")


def test_pipeline_mark_creator_verifier(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["pipeline-mark", "creator-verifier", "--project-root", str(tmp_path)],
    )
    assert result.exit_code == 0, result.output
    assert mark_recorded_recently(tmp_path, kind="creator-verifier")

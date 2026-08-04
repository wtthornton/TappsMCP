"""Smoke tests for tapps_mcp.distribution.doctor_consumer (TAP-5606 split)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.distribution.doctor_consumer import (
    _build_requirements_summary,
    check_plaintext_secrets,
    check_uv_path_mismatch,
)
from tapps_mcp.distribution.doctor_result import CheckResult


def test_check_uv_path_mismatch_not_uv_project_passes(tmp_path: Path) -> None:
    result = check_uv_path_mismatch(tmp_path)
    assert result.ok is True


def test_check_plaintext_secrets_no_configs_passes(tmp_path: Path) -> None:
    result = check_plaintext_secrets(tmp_path)
    assert result.ok is True
    assert "No plaintext secrets" in result.message


def test_build_requirements_summary_has_seven_requirements() -> None:
    summary = _build_requirements_summary([CheckResult("AGENTS.md", True, "ok")])
    assert len(summary) == 7
    assert summary[0]["requirement"] == 1
    assert summary[-1]["requirement"] == 7

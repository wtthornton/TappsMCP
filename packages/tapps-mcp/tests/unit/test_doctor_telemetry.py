"""Smoke tests for tapps_mcp.distribution.doctor_telemetry (TAP-5606 split)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.distribution.doctor_telemetry import (
    _read_engagement_level,
    check_cache_gate_block_hint,
    check_continuous_learning_v2_skill,
    check_install_git_hooks_hint,
    check_lookup_docs_discipline,
)


def test_read_engagement_level_none_when_config_absent(tmp_path: Path) -> None:
    assert _read_engagement_level(tmp_path) is None


def test_read_engagement_level_reads_valid_value(tmp_path: Path) -> None:
    (tmp_path / ".tapps-mcp.yaml").write_text(
        "llm_engagement_level: high\n", encoding="utf-8"
    )
    assert _read_engagement_level(tmp_path) == "high"


def test_check_lookup_docs_discipline_no_stale_scaffolding(tmp_path: Path) -> None:
    result = check_lookup_docs_discipline(tmp_path)
    assert result.ok is True


def test_check_continuous_learning_v2_skill_missing_fails(tmp_path: Path) -> None:
    result = check_continuous_learning_v2_skill(tmp_path)
    assert result.ok is False
    assert "not found" in result.message


def test_check_cache_gate_block_hint_off_no_violations(tmp_path: Path) -> None:
    result = check_cache_gate_block_hint(tmp_path)
    assert result.ok is True


def test_check_install_git_hooks_hint_default_medium_engagement(tmp_path: Path) -> None:
    result = check_install_git_hooks_hint(tmp_path)
    assert result.ok is True
    assert "optional at llm_engagement_level=medium" in result.message

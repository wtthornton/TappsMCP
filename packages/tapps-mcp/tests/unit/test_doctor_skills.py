"""Exact-stem smoke tests for tapps_mcp.distribution.doctor_skills (TAP-5606 split)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.distribution.doctor_skills import (
    check_orchestration_prompt_skill_current,
    check_validation_contract_skill_current,
    check_wayfind_skill_current,
)


def _core_tier_project(tmp_path: Path) -> Path:
    (tmp_path / ".tapps-mcp.yaml").write_text("skill_tier: core\n", encoding="utf-8")
    return tmp_path


def test_check_orchestration_prompt_skill_absent_passes_on_core_tier(tmp_path: Path) -> None:
    result = check_orchestration_prompt_skill_current(_core_tier_project(tmp_path))
    assert result.ok is True
    assert "not required" in result.message


def test_check_wayfind_skill_absent_passes_on_core_tier(tmp_path: Path) -> None:
    result = check_wayfind_skill_current(_core_tier_project(tmp_path))
    assert result.ok is True


def test_check_validation_contract_skill_absent_passes_on_core_tier(tmp_path: Path) -> None:
    result = check_validation_contract_skill_current(_core_tier_project(tmp_path))
    assert result.ok is True


def test_check_orchestration_prompt_skill_missing_fails_on_full_tier(tmp_path: Path) -> None:
    result = check_orchestration_prompt_skill_current(tmp_path)
    assert result.ok is False
    assert "missing" in result.message

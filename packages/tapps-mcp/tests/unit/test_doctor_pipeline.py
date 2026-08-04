"""Smoke tests for tapps_mcp.distribution.doctor_pipeline (TAP-5606 split)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.distribution.doctor_pipeline import (
    _count_cache_gate_violations_24h,
    _detect_cache_gate_mode,
    _tapps_skill_bases,
    check_deprecated_wrapper_skills,
    check_finish_task_skill,
    check_session_handoff_schema,
)


def test_detect_cache_gate_mode_off_when_script_absent(tmp_path: Path) -> None:
    assert _detect_cache_gate_mode(tmp_path) == "off"


def test_count_cache_gate_violations_24h_zero_when_log_absent(tmp_path: Path) -> None:
    assert _count_cache_gate_violations_24h(tmp_path) == 0


def test_tapps_skill_bases_defaults_to_claude(tmp_path: Path) -> None:
    bases = _tapps_skill_bases(tmp_path)
    assert bases == [("claude", tmp_path / ".claude" / "skills")]


def test_check_deprecated_wrapper_skills_none_found_passes(tmp_path: Path) -> None:
    result = check_deprecated_wrapper_skills(tmp_path)
    assert result.ok is True
    assert "No deprecated wrapper skills" in result.message


def test_check_finish_task_skill_missing_fails(tmp_path: Path) -> None:
    result = check_finish_task_skill(tmp_path)
    assert result.ok is False
    assert "Missing" in result.message


def test_check_session_handoff_schema_absent_is_optional_pass(tmp_path: Path) -> None:
    result = check_session_handoff_schema(tmp_path)
    assert result.ok is True
    assert "optional until handoff" in result.message

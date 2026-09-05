"""Smoke tests for tapps_mcp.distribution.doctor_pipeline (TAP-5606 split)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tapps_mcp.distribution.doctor_pipeline import (
    BYPASS_LOG,
    _count_bypass_log_24h,
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


def _write_bypass_log(tmp_path: Path, entries: list[dict[str, object]]) -> Path:
    log_dir = tmp_path / ".tapps-mcp"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / BYPASS_LOG
    with log_path.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    return log_path


def test_count_bypass_log_24h_zero_when_log_absent(tmp_path: Path) -> None:
    assert _count_bypass_log_24h(tmp_path) == 0


def test_count_bypass_log_24h_counts_dated_entry(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    _write_bypass_log(
        tmp_path,
        [
            {"ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "bypass": "TAPPS_SKIP_GATE"},
        ],
    )
    assert _count_bypass_log_24h(tmp_path) == 1


def test_count_bypass_log_24h_excludes_entry_outside_window(tmp_path: Path) -> None:
    """Negative control: an entry older than 24h must not be counted."""
    stale = datetime.now(UTC) - timedelta(hours=25)
    _write_bypass_log(
        tmp_path,
        [
            {"ts": stale.strftime("%Y-%m-%dT%H:%M:%SZ"), "bypass": "TAPPS_SKIP_GATE"},
        ],
    )
    assert _count_bypass_log_24h(tmp_path) == 0


def test_count_bypass_log_24h_mixed_window(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    stale = now - timedelta(hours=48)
    _write_bypass_log(
        tmp_path,
        [
            {"ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "bypass": "TAPPS_SKIP_GATE"},
            {"ts": stale.strftime("%Y-%m-%dT%H:%M:%SZ"), "bypass": "TAPPS_SKIP_GATE"},
            {"ts": "not-a-timestamp", "bypass": "TAPPS_SKIP_GATE"},
        ],
    )
    assert _count_bypass_log_24h(tmp_path) == 1

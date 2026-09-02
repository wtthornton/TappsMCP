"""Tests for the skill-learnings hygiene doctor check (TAP-6861).

Proves the check is wired into the real doctor chain
(:func:`tapps_mcp.distribution.doctor_runner._collect_checks`) and that it
fires on a dirty fixture (a near-duplicate bullet pair) while passing clean
on a small, non-duplicated one. Size/ceiling is deliberately NOT this check's
job — ``check_orchestration_prompt_learnings_ceiling`` (TAP-6854, landed
independently in #344) already owns it; see
``test_size_finding_does_not_double_report_with_ceiling_check`` below.
"""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.distribution.doctor_runner import _collect_checks
from tapps_mcp.distribution.doctor_skill_learnings import (
    CHECK_NAME,
    check_skill_learnings_hygiene,
)

_SKILL_MD = "---\nname: demo\ndescription: A demo skill.\n---\n\n- some project bullet.\n"


def _write_skill_pair(tmp_path: Path, *, skill_name: str, learnings_md: str) -> Path:
    skill_dir = tmp_path / ".claude" / "skills" / skill_name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(_SKILL_MD, encoding="utf-8")
    (skill_dir / "learnings.md").write_text(learnings_md, encoding="utf-8")
    return skill_dir


def test_check_registered_in_real_doctor_chain(tmp_path: Path) -> None:
    """TAP-6861 criterion: fires without the operator asking — must be a real
    entry in ``_collect_checks``, not a standalone function nobody calls."""
    checks = _collect_checks(tmp_path, quick=True)
    names = [c.name for c in checks]
    assert CHECK_NAME in names


def test_clean_skill_learnings_pass(tmp_path: Path) -> None:
    _write_skill_pair(tmp_path, skill_name="clean-skill", learnings_md="- one distinct bullet.\n")

    result = check_skill_learnings_hygiene(tmp_path)

    assert result.ok is True
    assert result.severity == "pass"
    assert "no hygiene findings" in result.message


def test_size_finding_does_not_double_report_with_ceiling_check(tmp_path: Path) -> None:
    """Reconciliation (round-3, TAP-6861 vs TAP-6854): an over-ceiling
    ``learnings.md`` must not be reported by BOTH doctor checks under two
    different names. ``check_orchestration_prompt_learnings_ceiling`` owns
    size/ceiling; this check stays clean on it even when over-ceiling.
    """
    # A single over-ceiling bullet (one "- " top-level line, nothing else to
    # pair it against) isolates the size dimension: over_ceiling=True in the
    # underlying audit, but near_duplicate and contradiction both stay empty
    # since there is no sibling bullet or managed block to compare against.
    dirty_learnings = "- " + ("padding word repeated many times in one bullet " * 3000) + "\n"
    _write_skill_pair(tmp_path, skill_name="dirty-skill", learnings_md=dirty_learnings)

    result = check_skill_learnings_hygiene(tmp_path)

    assert result.ok is True
    assert "no hygiene findings" in result.message


def test_near_duplicate_bullets_fire_near_duplicate_finding(tmp_path: Path) -> None:
    dirty_learnings = (
        "- Run tapps_quick_check after every Python file edit.\n"
        "- Always run tapps_quick_check after every Python file edit.\n"
    )
    _write_skill_pair(tmp_path, skill_name="dup-skill", learnings_md=dirty_learnings)

    result = check_skill_learnings_hygiene(tmp_path)

    assert result.ok is False
    assert result.severity == "warn"
    assert "dup-skill" in result.message
    assert "near_duplicate" in result.message


def test_no_learnings_files_pass(tmp_path: Path) -> None:
    result = check_skill_learnings_hygiene(tmp_path)

    assert result.ok is True
    assert "no skill learnings.md files found" in result.message

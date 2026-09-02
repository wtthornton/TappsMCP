"""Exact-stem smoke tests for tapps_mcp.distribution.doctor_skills (TAP-5606 split)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.distribution.doctor_skills import (
    check_orchestration_prompt_skill_current,
    check_validation_contract_skill_current,
    check_wayfind_skill_current,
)
from tapps_mcp.pipeline.platform_skills import generate_skills
from tapps_mcp.pipeline.skill_managed_block import MARKER_END


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


def test_truncated_managed_block_fails_even_with_every_old_probed_phrase_present(
    tmp_path: Path,
) -> None:
    """TAP-6948 regression: the old check only probed for markers + companions +
    a handful of substring phrases. A managed block deployed from a stale
    (shorter) emitter still contains every one of those phrases while missing
    everything else — real-world false PASS, measured twice by a peer session
    (a 375-line deployed block against a 616-line current emitter). The
    fingerprint check must FAIL on content, not phrase presence.
    """
    (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
    generate_skills(tmp_path, "claude")
    skill_md = tmp_path / ".claude" / "skills" / "orchestration-prompt" / "SKILL.md"
    full = skill_md.read_text(encoding="utf-8")
    full_lines = full.splitlines(keepends=True)
    assert len(full_lines) > 600, "fixture assumes the real template is well over 600 lines"

    # Every phrase the retired substring probe checked for lives at or before
    # line 530 — truncating there reproduces a block that would have PASSED
    # the old check while being materially shorter (~530 vs 735+ lines) than
    # what the current emitter actually produces.
    truncated_body = "".join(full_lines[:530]) + MARKER_END + "\n"
    for phrase in ("validation contract", "expected-fail", "shift boundary", "host-feature-map"):
        assert phrase in truncated_body.lower(), (
            f"fixture must retain {phrase!r} to prove the old blind spot"
        )
    skill_md.write_text(truncated_body, encoding="utf-8")

    result = check_orchestration_prompt_skill_current(tmp_path)
    assert result.ok is False
    assert "stale content" in result.message
    assert "orchestration-prompt" in result.message

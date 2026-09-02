"""Exact-stem smoke tests for tapps_mcp.distribution.doctor_skills (TAP-5606 split)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.distribution.doctor_skills import (
    check_orchestration_prompt_learnings_ceiling,
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


def test_check_learnings_ceiling_absent_passes(tmp_path: Path) -> None:
    """No learnings.md deployed at all: nothing to measure, not a failure."""
    result = check_orchestration_prompt_learnings_ceiling(tmp_path)
    assert result.ok is True
    assert "no learnings.md" in result.message


def test_check_learnings_ceiling_under_ceiling_passes(tmp_path: Path) -> None:
    """TAP-6854 criterion 5 positive control: a small learnings.md must not flag.

    Without this, a check that always fails (or always passes) would look
    identical to a real ceiling check in the over-ceiling test below.
    """
    (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
    generate_skills(tmp_path, "claude")
    learnings = tmp_path / ".claude" / "skills" / "orchestration-prompt" / "learnings.md"
    learnings.write_text("- one short lesson (2026-09-02)\n", encoding="utf-8")

    result = check_orchestration_prompt_learnings_ceiling(tmp_path)
    assert result.ok is True
    assert "under ceiling" in result.message


def test_check_learnings_ceiling_over_bullet_count_fails(tmp_path: Path) -> None:
    """TAP-6854 criterion 5: 'the ceiling is enforced by a check, not by prose'.

    The emitted SKILL.md says 'Past roughly 120 bullets or 40 KB, merge' —
    until this check, nothing ever measured either number. This fixture is
    121 top-level bullets, each far under the byte ceiling on its own, so
    only the bullet-count half of the OR can be responsible for the flag.
    """
    (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
    generate_skills(tmp_path, "claude")
    learnings = tmp_path / ".claude" / "skills" / "orchestration-prompt" / "learnings.md"
    bullets = "\n".join(f"- lesson {i} (2026-09-02)" for i in range(121))
    learnings.write_text(bullets + "\n", encoding="utf-8")

    result = check_orchestration_prompt_learnings_ceiling(tmp_path)
    assert result.ok is False
    assert "past ceiling" in result.message
    assert "orchestration-prompt/learnings.md" in result.message


def test_check_learnings_ceiling_over_byte_size_fails(tmp_path: Path) -> None:
    """Same check, other half of the OR: a handful of bullets well over 40 KB."""
    (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
    generate_skills(tmp_path, "claude")
    learnings = tmp_path / ".claude" / "skills" / "orchestration-prompt" / "learnings.md"
    long_bullet = "- " + ("x" * 500) + " (2026-09-02)"
    content = "\n".join(long_bullet for _ in range(100))
    assert len(content.encode("utf-8")) > 40_000, "fixture must clear the byte ceiling"
    learnings.write_text(content + "\n", encoding="utf-8")

    result = check_orchestration_prompt_learnings_ceiling(tmp_path)
    assert result.ok is False
    assert "past ceiling" in result.message

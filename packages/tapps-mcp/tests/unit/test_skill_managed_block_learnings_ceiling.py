"""Unit tests for skill_managed_block.learnings_size_finding (TAP-6854 criterion 5).

Criterion 5: "the learnings.md ceiling is enforced by a check, not by prose."
The emitted orchestration-prompt SKILL.md tells the agent "Past roughly 120
bullets or 40 KB, merge overlapping lines" — until this function existed,
nothing measured either number. These tests exercise the pure measurement
function directly (independent of the doctor-check-level tests in
test_doctor_skills.py, which exercise it end to end through a real
generated skill tree).

TAP-6861 (branch tap-6861-skill-learnings, PR #345, unmerged as of this
writing) ships a fuller learnings.md audit built on primitives
(bullet_spans, Region, contradiction detection) this branch does not have.
This module is the minimal standalone half named in the round-2 fix brief —
no dependency on that unmerged code.
"""

from __future__ import annotations

from tapps_mcp.pipeline.skill_managed_block import (
    LEARNINGS_CEILING_BULLETS,
    LEARNINGS_CEILING_BYTES,
    learnings_size_finding,
)


def test_empty_file_is_under_ceiling() -> None:
    finding = learnings_size_finding("")
    assert finding.size_bytes == 0
    assert finding.bullet_count == 0
    assert finding.over_ceiling is False


def test_bullet_count_ignores_indented_continuation_lines() -> None:
    """Only column-0 '- ' lines count as a bullet — matching 'one lesson per bullet'."""
    content = (
        "- top-level bullet one\n"
        "  - nested detail, not a new lesson\n"
        "- top-level bullet two\n"
    )
    finding = learnings_size_finding(content)
    assert finding.bullet_count == 2


def test_exactly_at_ceiling_does_not_flag() -> None:
    """'Past' the ceiling is strictly greater-than, not greater-or-equal."""
    bullets = "\n".join(f"- lesson {i}" for i in range(LEARNINGS_CEILING_BULLETS))
    finding = learnings_size_finding(bullets)
    assert finding.bullet_count == LEARNINGS_CEILING_BULLETS
    assert finding.over_ceiling is False


def test_one_bullet_past_ceiling_flags() -> None:
    bullets = "\n".join(f"- lesson {i}" for i in range(LEARNINGS_CEILING_BULLETS + 1))
    finding = learnings_size_finding(bullets)
    assert finding.bullet_count == LEARNINGS_CEILING_BULLETS + 1
    assert finding.over_ceiling is True


def test_byte_ceiling_flags_independent_of_bullet_count() -> None:
    """A handful of bullets can still clear the byte ceiling on its own."""
    long_bullet = "- " + ("x" * (LEARNINGS_CEILING_BYTES + 1))
    finding = learnings_size_finding(long_bullet)
    assert finding.bullet_count == 1
    assert finding.size_bytes > LEARNINGS_CEILING_BYTES
    assert finding.over_ceiling is True


def test_custom_thresholds_are_respected() -> None:
    finding = learnings_size_finding(
        "- a\n- b\n- c\n", ceiling_bytes=1_000_000, ceiling_bullets=2
    )
    assert finding.bullet_count == 3
    assert finding.over_ceiling is True

"""Tests for ``check_skill_mirror_parity`` (TAP-6944).

A managed skill's Claude and Cursor copies are generated from the same
host-agnostic body, so their managed blocks should be byte-identical wherever
a project deploys both. This check catches the case where one mirror drifted
from the other without anyone noticing.
"""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.distribution.doctor_skills import check_skill_mirror_parity
from tapps_mcp.pipeline.platform_skills import generate_skills

SKILL = "tapps-wayfind"


def _skill_md(root: Path, host: str, skill: str = SKILL) -> Path:
    return root / f".{host}" / "skills" / skill / "SKILL.md"


def test_passes_when_only_one_host_is_deployed(tmp_path: Path) -> None:
    generate_skills(tmp_path, "claude")
    result = check_skill_mirror_parity(tmp_path)
    assert result.ok
    assert "no skill deployed to more than one host" in result.message


def test_passes_when_both_host_mirrors_match_byte_for_byte(tmp_path: Path) -> None:
    generate_skills(tmp_path, "claude")
    generate_skills(tmp_path, "cursor")
    result = check_skill_mirror_parity(tmp_path)
    assert result.ok
    assert "match" in result.message.lower()


def test_fails_naming_both_paths_on_divergence(tmp_path: Path) -> None:
    generate_skills(tmp_path, "claude")
    generate_skills(tmp_path, "cursor")

    cursor_path = _skill_md(tmp_path, "cursor")
    cursor_path.write_text(
        cursor_path.read_text(encoding="utf-8").replace("fog", "haze"),
        encoding="utf-8",
    )

    result = check_skill_mirror_parity(tmp_path)
    assert not result.ok
    assert SKILL in result.message
    claude_path = _skill_md(tmp_path, "claude")
    assert str(claude_path) in result.message
    assert str(cursor_path) in result.message


def test_single_byte_divergence_in_one_skill_does_not_mask_others(tmp_path: Path) -> None:
    """A divergence in one smart-merge skill is named without silencing the rest."""
    generate_skills(tmp_path, "claude")
    generate_skills(tmp_path, "cursor")

    cursor_path = _skill_md(tmp_path, "cursor", "orchestration-prompt")
    cursor_text = cursor_path.read_text(encoding="utf-8")
    assert "context lifecycle" in cursor_text.lower(), (
        "fixture assumes this phrase is present in the managed block"
    )
    cursor_path.write_text(
        cursor_text.replace("Context lifecycle", "Context limit"),
        encoding="utf-8",
    )

    result = check_skill_mirror_parity(tmp_path)
    assert not result.ok
    assert "orchestration-prompt" in result.message
    assert "tapps-wayfind" not in result.message
    assert "tapps-validation-contract" not in result.message

"""Tests for the doctor's context-budget checks.

Split out of ``test_doctor.py`` (3,419 lines, MI 0.0) so context-budget coverage
has a home that clears the quality gate.
"""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.distribution.context_budget import (
    _oversized_skill_bodies,
    check_skill_inventory_budget,
)


def _skill(root: Path, name: str, lines: int, companion: bool = False) -> None:
    skill_dir = root / ".claude" / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("line\n" * lines, encoding="utf-8")
    if companion:
        refs = skill_dir / "references"
        refs.mkdir(exist_ok=True)
        (refs / "claude-feature-map.md").write_text("x", encoding="utf-8")


def _budget(root: Path, body_max: int = 50) -> None:
    (root / ".mcp.json").write_text("{}", encoding="utf-8")
    (root / ".tapps-mcp.yaml").write_text(
        f"doctor_context_budget:\n  skill_body_max_lines: {body_max}\n  skill_count_max: 100\n",
        encoding="utf-8",
    )


class TestOversizedSkillBodies:
    """Companions are the remedy for an oversized body, not an exemption.

    orchestration-prompt shipped 365 lines against a 120-line ceiling and reported
    ``pass`` purely because it appears in ``SKILL_COMPANION_FILES``.
    """

    def test_companions_do_not_exempt_from_measurement(self, tmp_path: Path) -> None:
        _skill(tmp_path, "orchestration-prompt", 200, companion=True)
        skill_dirs = sorted((tmp_path / ".claude" / "skills").iterdir())
        found = _oversized_skill_bodies(
            skill_dirs,
            {"orchestration-prompt"},
            set(),
            {"orchestration-prompt"},
            50,
        )
        assert found == ["orchestration-prompt(201; has companions)"]

    def test_body_under_ceiling_is_not_flagged(self, tmp_path: Path) -> None:
        _skill(tmp_path, "orchestration-prompt", 10, companion=True)
        skill_dirs = sorted((tmp_path / ".claude" / "skills").iterdir())
        assert (
            _oversized_skill_bodies(
                skill_dirs, {"orchestration-prompt"}, set(), {"orchestration-prompt"}, 50
            )
            == []
        )

    def test_unregistered_and_deprecated_skills_are_skipped(self, tmp_path: Path) -> None:
        _skill(tmp_path, "third-party-thing", 200)
        _skill(tmp_path, "tapps-score", 200)
        skill_dirs = sorted((tmp_path / ".claude" / "skills").iterdir())
        assert (
            _oversized_skill_bodies(skill_dirs, {"tapps-score"}, {"tapps-score"}, set(), 50) == []
        )


class TestSkillInventoryBudget:
    def test_flags_oversized_even_with_companions(self, tmp_path: Path) -> None:
        _skill(tmp_path, "orchestration-prompt", 200, companion=True)
        _budget(tmp_path)
        result = check_skill_inventory_budget(tmp_path)
        assert result.ok is False
        assert result.severity == "warn"
        assert "orchestration-prompt" in result.message
        assert "has companions" in result.message

    def test_external_skills_are_noted_not_failed(self, tmp_path: Path) -> None:
        _skill(tmp_path, "some-user-skill", 10)
        _budget(tmp_path)
        result = check_skill_inventory_budget(tmp_path)
        assert result.ok is True
        assert "external skills" in result.message

    def test_no_skills_dir_skips(self, tmp_path: Path) -> None:
        _budget(tmp_path)
        result = check_skill_inventory_budget(tmp_path)
        assert result.ok is True
        assert "skipping" in result.message.lower()

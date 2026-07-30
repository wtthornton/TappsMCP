"""continuous-learning-v2 slim SKILL.md + companion progressive disclosure."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.pipeline.platform_skills import (
    CLAUDE_SKILLS,
    SKILL_COMPANION_FILES,
    generate_skills,
)


def test_claude_body_under_progressive_disclosure_threshold() -> None:
    lines = CLAUDE_SKILLS["continuous-learning-v2"].count("\n") + 1
    assert lines <= 120


def test_companions_registered() -> None:
    companions = SKILL_COMPANION_FILES["continuous-learning-v2"]
    assert "references/architecture.md" in companions
    assert "references/operations.md" in companions
    assert "Instinct Model" in companions["references/architecture.md"]
    assert "observer.enabled" in companions["references/operations.md"]


def test_generate_skills_writes_companions(tmp_path: Path) -> None:
    generate_skills(tmp_path, "claude", overwrite=True)
    skill = tmp_path / ".claude" / "skills" / "continuous-learning-v2"
    assert (skill / "SKILL.md").is_file()
    assert (skill / "references" / "architecture.md").is_file()
    assert (skill / "references" / "operations.md").is_file()
    body = (skill / "SKILL.md").read_text(encoding="utf-8")
    assert "references/architecture.md" in body
    assert body.count("\n") + 1 <= 120


def test_companions_refresh_when_skill_md_skipped(tmp_path: Path) -> None:
    skill = tmp_path / ".claude" / "skills" / "continuous-learning-v2"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# stale custom\n", encoding="utf-8")
    generate_skills(tmp_path, "claude", overwrite=False)
    assert (skill / "SKILL.md").read_text(encoding="utf-8") == "# stale custom\n"
    assert (skill / "references" / "architecture.md").is_file()

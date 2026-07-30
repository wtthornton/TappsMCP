"""Tests for skill_tier filtering and prune helpers."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.pipeline.platform_skills import (
    CORE_SKILL_NAMES,
    generate_skills,
    prune_skills_for_tier,
)


def test_generate_skills_core_tier_only_writes_core(tmp_path: Path) -> None:
    result = generate_skills(tmp_path, "claude", skill_tier="core")
    created = set(result["created"])
    assert created <= CORE_SKILL_NAMES
    assert "tapps-finish-task" in created
    assert "tapps-review-pipeline" in result["skipped_tier"]
    assert (tmp_path / ".claude" / "skills" / "tapps-finish-task" / "SKILL.md").is_file()
    assert not (tmp_path / ".claude" / "skills" / "tapps-review-pipeline").exists()


def test_generate_skills_full_includes_non_core(tmp_path: Path) -> None:
    result = generate_skills(tmp_path, "claude", skill_tier="full")
    assert "tapps-review-pipeline" in result["created"]
    assert result["skipped_tier"] == []


def test_prune_skills_for_tier_removes_non_core_registry(tmp_path: Path) -> None:
    generate_skills(tmp_path, "claude", skill_tier="full")
    assert (tmp_path / ".claude" / "skills" / "tapps-review-pipeline").is_dir()
    preview = prune_skills_for_tier(tmp_path, "claude", skill_tier="core", dry_run=True)
    assert "tapps-review-pipeline" in preview["would_prune"]
    assert preview["bytes_freed"] > 0
    applied = prune_skills_for_tier(tmp_path, "claude", skill_tier="core", dry_run=False)
    assert "tapps-review-pipeline" in applied["pruned"]
    assert not (tmp_path / ".claude" / "skills" / "tapps-review-pipeline").exists()
    assert (tmp_path / ".claude" / "skills" / "tapps-finish-task").is_dir()


def test_prune_does_not_delete_unknown_user_skills(tmp_path: Path) -> None:
    generate_skills(tmp_path, "claude", skill_tier="full")
    custom = tmp_path / ".claude" / "skills" / "my-custom-skill"
    custom.mkdir(parents=True)
    (custom / "SKILL.md").write_text("# custom\n", encoding="utf-8")
    prune_skills_for_tier(tmp_path, "claude", skill_tier="core", dry_run=False)
    assert custom.is_dir()


def test_karpathy_remove_block(tmp_path: Path) -> None:
    from tapps_mcp.pipeline import karpathy_block

    path = tmp_path / "CLAUDE.md"
    path.write_text("# keep me\n\n", encoding="utf-8")
    karpathy_block.install_or_refresh(path)
    assert karpathy_block.has_block(path)
    action = karpathy_block.remove_block(path)
    assert action == "refreshed"
    assert not karpathy_block.has_block(path)
    assert "# keep me" in path.read_text(encoding="utf-8")

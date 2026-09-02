"""Skills manifest emission + doctor directory-diff (TAP-6948 story 2)."""

from __future__ import annotations

import json
from pathlib import Path

from tapps_mcp.distribution.doctor_skills import (
    check_orchestration_prompt_skill_current,
    check_skills_manifest_directory,
)
from tapps_mcp.pipeline.platform_skills import (
    SKILLS_MANIFEST_REL_PATH,
    SMART_MERGE_SKILL_NAMES,
    generate_skills,
)
from tapps_mcp.pipeline.skill_managed_block import MARKER_BEGIN_PREFIX, install_or_refresh_skill


def _manifest_path(tmp_path: Path) -> Path:
    return tmp_path.joinpath(*SKILLS_MANIFEST_REL_PATH)


def _mutate_block(skill_md: Path) -> None:
    """Insert a line inside the managed block without touching BEGIN/END."""
    content = skill_md.read_text(encoding="utf-8")
    begin_idx = content.find(MARKER_BEGIN_PREFIX)
    assert begin_idx != -1, "fixture requires a managed block already on disk"
    line_end = content.find("\n", begin_idx) + 1
    mutated = content[:line_end] + "drift: hand-edited after upgrade\n" + content[line_end:]
    skill_md.write_text(mutated, encoding="utf-8")


class TestManifestEmission:
    def test_manifest_written_on_generate(self, tmp_path: Path) -> None:
        generate_skills(tmp_path, "claude")
        manifest = json.loads(_manifest_path(tmp_path).read_text(encoding="utf-8"))
        assert "claude" in manifest
        # A non-smart-merge skill and a smart-merge skill both get an entry —
        # the manifest covers the whole registry, not just the trio.
        assert "tapps-finish-task" in manifest["claude"]
        assert "orchestration-prompt" in manifest["claude"]
        entry = manifest["claude"]["tapps-finish-task"]
        assert isinstance(entry, str)
        assert len(entry) == 64  # sha256 hex digest

    def test_manifest_merges_across_platforms(self, tmp_path: Path) -> None:
        generate_skills(tmp_path, "claude")
        generate_skills(tmp_path, "cursor")
        manifest = json.loads(_manifest_path(tmp_path).read_text(encoding="utf-8"))
        assert "tapps-finish-task" in manifest["claude"]
        assert "tapps-finish-task" in manifest["cursor"]

    def test_manifest_omits_skipped_tier_skills(self, tmp_path: Path) -> None:
        generate_skills(tmp_path, "claude", skill_tier="core")
        manifest = json.loads(_manifest_path(tmp_path).read_text(encoding="utf-8"))
        assert "tapps-review-pipeline" not in manifest["claude"]
        assert "tapps-finish-task" in manifest["claude"]


class TestDirectoryDiffCheck:
    def test_absent_manifest_warns_not_silent_pass(self, tmp_path: Path) -> None:
        result = check_skills_manifest_directory(tmp_path)
        assert result.severity == "warn"
        assert result.ok is False
        assert "no manifest" in result.message
        assert "run upgrade" in result.message.lower()

    def test_current_deployment_passes(self, tmp_path: Path) -> None:
        (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
        generate_skills(tmp_path, "claude")
        result = check_skills_manifest_directory(tmp_path)
        assert result.ok is True
        assert "match the skills manifest" in result.message

    def test_stale_on_disk_fails(self, tmp_path: Path) -> None:
        (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
        generate_skills(tmp_path, "claude")
        _mutate_block(tmp_path / ".claude" / "skills" / "tapps-finish-task" / "SKILL.md")

        result = check_skills_manifest_directory(tmp_path)
        assert result.ok is False
        assert "tapps-finish-task" in result.message
        assert "stale on disk" in result.message

    def test_deployed_skill_absent_from_manifest_fails_unknown(self, tmp_path: Path) -> None:
        (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
        generate_skills(tmp_path, "claude")
        rogue = tmp_path / ".claude" / "skills" / "not-a-registered-skill" / "SKILL.md"
        install_or_refresh_skill(
            rogue, "---\nname: not-a-registered-skill\n---\n\nbody\n", "not-a-registered-skill"
        )

        result = check_skills_manifest_directory(tmp_path)
        assert result.ok is False
        assert "not-a-registered-skill" in result.message
        assert "unknown" in result.message

    def test_manifest_entry_missing_on_disk_fails(self, tmp_path: Path) -> None:
        (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
        generate_skills(tmp_path, "claude")
        skill_md = tmp_path / ".claude" / "skills" / "tapps-finish-task" / "SKILL.md"
        skill_md.unlink()

        result = check_skills_manifest_directory(tmp_path)
        assert result.ok is False
        assert "tapps-finish-task" in result.message
        assert "missing" in result.message

    def test_partitions_away_from_smart_merge_skills(self, tmp_path: Path) -> None:
        """TAP-6948 s2 partition: this check cedes the trio to
        ``check_orchestration_prompt_skill_current`` (and its two siblings) so
        the same drift is never reported by both checks.
        """
        (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
        generate_skills(tmp_path, "claude")
        assert "orchestration-prompt" in SMART_MERGE_SKILL_NAMES
        _mutate_block(tmp_path / ".claude" / "skills" / "orchestration-prompt" / "SKILL.md")

        directory_diff = check_skills_manifest_directory(tmp_path)
        assert directory_diff.ok is True, "smart-merge drift is not this check's finding"

        deep_check = check_orchestration_prompt_skill_current(tmp_path)
        assert deep_check.ok is False, "the existing deep-content check still catches it"

"""Tests for the multi-file, smart-merged ``orchestration-prompt`` platform skill.

Covers three concerns:
- ``generate_skills`` scaffolds SKILL.md + companion files + seed learnings.
- ``skill_managed_block.install_or_refresh_skill`` refreshes the managed block
  while preserving project customizations (and migrates legacy unmarked copies).
- companion docs refresh on upgrade but ``learnings.md`` is never overwritten.
- the doctor check reports current / stale / partial correctly.
"""

from __future__ import annotations

from tapps_mcp.distribution.doctor import check_orchestration_prompt_skill_current
from tapps_mcp.pipeline.platform_skills import generate_skills
from tapps_mcp.pipeline.skill_managed_block import (
    MARKER_BEGIN_PREFIX,
    MARKER_END,
    install_or_refresh_skill,
    wrap_with_markers,
)

SKILL = "orchestration-prompt"


def _skill_dir(root, host="claude"):
    return root / f".{host}" / "skills" / SKILL


class TestScaffold:
    def test_creates_skill_and_companions(self, tmp_path):
        generate_skills(tmp_path, "claude")
        d = _skill_dir(tmp_path)
        assert (d / "SKILL.md").exists()
        assert (d / "assets" / "prompt-template.md").exists()
        assert (d / "references" / "claude-feature-map.md").exists()
        assert (d / "learnings.md").exists()

    def test_skill_md_has_managed_marker(self, tmp_path):
        generate_skills(tmp_path, "claude")
        content = (_skill_dir(tmp_path) / "SKILL.md").read_text()
        assert f"{MARKER_BEGIN_PREFIX} {SKILL} v" in content
        assert MARKER_END in content
        assert "name: orchestration-prompt" in content

    def test_body_carries_the_four_enhancements(self, tmp_path):
        generate_skills(tmp_path, "claude")
        content = (_skill_dir(tmp_path) / "SKILL.md").read_text().lower()
        # 1. independent adversarial verifier
        assert "verifier subagent" in content
        assert "refute" in content
        # 2. model / effort tiering
        assert "model tier" in content
        # 3. ground-truth over LLM-judge
        assert "ground truth" in content or "ground-truth" in content
        # 4. context hygiene
        assert "context hygiene" in content

    def test_template_has_verifier_and_tier_columns(self, tmp_path):
        generate_skills(tmp_path, "claude")
        tpl = (_skill_dir(tmp_path) / "assets" / "prompt-template.md").read_text().lower()
        assert "model tier" in tpl
        assert "verifier subagent" in tpl

    def test_body_and_template_carry_harness_compatibility(self, tmp_path):
        generate_skills(tmp_path, "claude")
        d = _skill_dir(tmp_path)
        content = (d / "SKILL.md").read_text().lower()
        # method §6: the emitted prompt must survive the project's own hooks
        # (PreToolUse gates) and MCP standing nudges — adopt or override each.
        assert "harness-compatibility sweep" in content
        assert "adopt or override" in content or "adopted or overridden" in content
        tpl = (d / "assets" / "prompt-template.md").read_text().lower()
        assert "harness compatibility" in tpl

    def test_cursor_host_also_gets_skill(self, tmp_path):
        generate_skills(tmp_path, "cursor")
        assert (_skill_dir(tmp_path, "cursor") / "SKILL.md").exists()
        assert (_skill_dir(tmp_path, "cursor") / "references" / "claude-feature-map.md").exists()


class TestSmartMerge:
    def test_upgrade_preserves_project_region(self, tmp_path):
        generate_skills(tmp_path, "claude")
        skill_md = _skill_dir(tmp_path) / "SKILL.md"
        # Simulate a consumer appending a project region below the managed block.
        marker = "## Project: fleet wiring\n\nSee `fleet.md` for repo ids."
        skill_md.write_text(skill_md.read_text() + "\n\n" + marker, encoding="utf-8")

        generate_skills(tmp_path, "claude", overwrite=True)  # upgrade path
        after = skill_md.read_text()
        assert marker in after  # customization survived
        assert MARKER_END in after

    def test_learnings_not_overwritten_on_upgrade(self, tmp_path):
        generate_skills(tmp_path, "claude")
        learnings = _skill_dir(tmp_path) / "learnings.md"
        learnings.write_text("- my project lesson\n", encoding="utf-8")
        generate_skills(tmp_path, "claude", overwrite=True)
        assert learnings.read_text() == "- my project lesson\n"

    def test_companion_docs_refresh_on_upgrade(self, tmp_path):
        generate_skills(tmp_path, "claude")
        ref = _skill_dir(tmp_path) / "references" / "claude-feature-map.md"
        ref.write_text("stale\n", encoding="utf-8")
        generate_skills(tmp_path, "claude", overwrite=True)
        assert "feature map" in ref.read_text().lower()  # canonical content restored


class TestManagedBlockUnit:
    def test_created_then_unchanged(self, tmp_path):
        path = tmp_path / "SKILL.md"
        assert install_or_refresh_skill(path, "body v1", SKILL) == "created"
        assert install_or_refresh_skill(path, "body v1", SKILL) == "unchanged"

    def test_refreshed_on_body_change(self, tmp_path):
        path = tmp_path / "SKILL.md"
        install_or_refresh_skill(path, "body v1", SKILL)
        assert install_or_refresh_skill(path, "body v2", SKILL) == "refreshed"
        assert "body v2" in path.read_text()

    def test_legacy_migration_preserves_old_body(self, tmp_path):
        path = tmp_path / "SKILL.md"
        path.write_text("# hand-authored\n\nfleet-specific stuff\n", encoding="utf-8")
        assert install_or_refresh_skill(path, "platform body", SKILL) == "migrated"
        after = path.read_text()
        assert "platform body" in after  # managed block installed
        assert "fleet-specific stuff" in after  # old content preserved
        assert after.index(MARKER_BEGIN_PREFIX) < after.index("fleet-specific")

    def test_wrap_roundtrip_stamps_version(self, tmp_path):
        wrapped = wrap_with_markers("x", SKILL, version="9.9.9")
        assert f"{MARKER_BEGIN_PREFIX} {SKILL} v9.9.9 -->" in wrapped
        assert wrapped.endswith(MARKER_END)


class TestDoctorCheck:
    def test_ok_when_fully_deployed(self, tmp_path):
        (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
        generate_skills(tmp_path, "claude")
        result = check_orchestration_prompt_skill_current(tmp_path)
        assert result.ok
        assert "current" in result.message

    def test_ok_when_not_deployed(self, tmp_path):
        (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
        result = check_orchestration_prompt_skill_current(tmp_path)
        assert result.ok
        assert "not deployed" in result.message

    def test_flags_missing_companion(self, tmp_path):
        (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
        generate_skills(tmp_path, "claude")
        (_skill_dir(tmp_path) / "references" / "claude-feature-map.md").unlink()
        result = check_orchestration_prompt_skill_current(tmp_path)
        assert not result.ok

    def test_flags_stale_unmarked_skill(self, tmp_path):
        (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
        d = _skill_dir(tmp_path)
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("# legacy hand-authored, no marker\n", encoding="utf-8")
        result = check_orchestration_prompt_skill_current(tmp_path)
        assert not result.ok
        assert "stale" in result.message

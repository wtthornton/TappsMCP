"""Tests for skills generation (Story 12.8, Epic 27).

Verifies that generate_skills() creates SKILL.md files per platform with
correct frontmatter format differences between Claude Code and Cursor.
"""

from __future__ import annotations

from tapps_mcp.pipeline.platform_generators import generate_skills
from tapps_mcp.pipeline.platform_skills import CLAUDE_SKILLS, DEPRECATED_TAPPS_SKILLS


class TestClaudeSkills:
    """Tests for Claude Code skill generation."""

    def test_creates_orchestration_skills(self, tmp_path):
        generate_skills(tmp_path, "claude")
        base = tmp_path / ".claude" / "skills"
        assert (base / "tapps-finish-task" / "SKILL.md").exists()
        assert (base / "tapps-review-pipeline" / "SKILL.md").exists()
        assert (base / "tapps-research" / "SKILL.md").exists()
        assert (base / "tapps-security" / "SKILL.md").exists()
        assert (base / "tapps-memory" / "SKILL.md").exists()
        for deprecated in DEPRECATED_TAPPS_SKILLS:
            assert not (base / deprecated / "SKILL.md").exists()

    def test_finish_task_has_allowed_tools(self, tmp_path):
        generate_skills(tmp_path, "claude")
        content = (tmp_path / ".claude" / "skills" / "tapps-finish-task" / "SKILL.md").read_text()
        assert "allowed-tools:" in content
        assert "mcp__nlt-build__tapps_validate_changed" in content
        assert "mcp__nlt-build__tapps_checklist" in content

    def test_finish_task_has_name(self, tmp_path):
        generate_skills(tmp_path, "claude")
        content = (tmp_path / ".claude" / "skills" / "tapps-finish-task" / "SKILL.md").read_text()
        assert "name: tapps-finish-task" in content

    def test_all_skills_have_frontmatter(self, tmp_path):
        generate_skills(tmp_path, "claude")
        base = tmp_path / ".claude" / "skills"
        for skill in [
            "tapps-finish-task",
            "tapps-review-pipeline",
            "tapps-research",
            "tapps-security",
            "tapps-memory",
        ]:
            content = (base / skill / "SKILL.md").read_text()
            assert content.startswith("---\n"), f"{skill} missing frontmatter"
            assert "name:" in content
            assert "description:" in content

    def test_review_pipeline_references_validate_and_checklist(self, tmp_path):
        generate_skills(tmp_path, "claude")
        base = tmp_path / ".claude" / "skills"
        content = (base / "tapps-review-pipeline" / "SKILL.md").read_text()
        assert "mcp__nlt-build__tapps_validate_changed" in content
        assert "mcp__nlt-build__tapps_checklist" in content
        assert "tapps-review-fixer" in content

    def test_research_skill_references_tools(self, tmp_path):
        generate_skills(tmp_path, "claude")
        base = tmp_path / ".claude" / "skills"
        content = (base / "tapps-research" / "SKILL.md").read_text()
        assert "mcp__nlt-build__tapps_lookup_docs" in content

    def test_security_skill_references_tools(self, tmp_path):
        generate_skills(tmp_path, "claude")
        base = tmp_path / ".claude" / "skills"
        content = (base / "tapps-security" / "SKILL.md").read_text()
        assert "mcp__nlt-build__tapps_security_scan" in content
        assert "mcp__nlt-build__tapps_dependency_scan" in content

    def test_memory_skill_references_tools(self, tmp_path):
        generate_skills(tmp_path, "claude")
        base = tmp_path / ".claude" / "skills"
        content = (base / "tapps-memory" / "SKILL.md").read_text()
        assert "mcp__nlt-build__tapps_session_start" in content
        assert "mcp__nlt-memory__tapps_session_notes" in content


class TestCursorSkills:
    """Tests for Cursor skill generation."""

    def test_creates_orchestration_skills(self, tmp_path):
        generate_skills(tmp_path, "cursor")
        base = tmp_path / ".cursor" / "skills"
        assert (base / "tapps-finish-task" / "SKILL.md").exists()
        assert (base / "tapps-review-pipeline" / "SKILL.md").exists()
        for deprecated in DEPRECATED_TAPPS_SKILLS:
            assert not (base / deprecated / "SKILL.md").exists()

    def test_review_pipeline_uses_short_tool_names(self, tmp_path):
        generate_skills(tmp_path, "cursor")
        base = tmp_path / ".cursor" / "skills"
        content = (base / "tapps-review-pipeline" / "SKILL.md").read_text()
        assert "tapps_validate_changed" in content
        assert "tapps_checklist" in content
        assert "mcp__tapps-mcp__" not in content

    def test_finish_task_has_mcp_tools_list(self, tmp_path):
        generate_skills(tmp_path, "cursor")
        content = (tmp_path / ".cursor" / "skills" / "tapps-finish-task" / "SKILL.md").read_text()
        assert "mcp_tools:" in content
        assert "  - tapps_validate_changed" in content
        assert "  - tapps_checklist" in content

    def test_cursor_body_uses_short_tool_names(self, tmp_path):
        generate_skills(tmp_path, "cursor")
        content = (tmp_path / ".cursor" / "skills" / "tapps-finish-task" / "SKILL.md").read_text()
        assert "tapps_validate_changed" in content
        assert "mcp__tapps-mcp__" not in content

    def test_research_skill_references_tools(self, tmp_path):
        generate_skills(tmp_path, "cursor")
        base = tmp_path / ".cursor" / "skills"
        content = (base / "tapps-research" / "SKILL.md").read_text()
        assert "tapps_lookup_docs" in content
        assert "mcp__tapps-mcp__" not in content

    def test_security_skill_references_tools(self, tmp_path):
        generate_skills(tmp_path, "cursor")
        base = tmp_path / ".cursor" / "skills"
        content = (base / "tapps-security" / "SKILL.md").read_text()
        assert "tapps_security_scan" in content
        assert "tapps_dependency_scan" in content
        assert "mcp__tapps-mcp__" not in content

    def test_memory_skill_references_tools(self, tmp_path):
        generate_skills(tmp_path, "cursor")
        base = tmp_path / ".cursor" / "skills"
        content = (base / "tapps-memory" / "SKILL.md").read_text()
        assert "tapps_session_notes" in content
        assert "mcp__tapps-mcp__" not in content


class TestSkipExisting:
    """Tests for skip-on-exists behavior."""

    def test_skips_existing_skill(self, tmp_path):
        skill_dir = tmp_path / ".claude" / "skills" / "tapps-finish-task"
        skill_dir.mkdir(parents=True)
        custom = "# My custom skill\n"
        (skill_dir / "SKILL.md").write_text(custom)

        result = generate_skills(tmp_path, "claude")

        assert "tapps-finish-task" in result["skipped"]
        assert (skill_dir / "SKILL.md").read_text() == custom
        assert (tmp_path / ".claude" / "skills" / "tapps-review-pipeline" / "SKILL.md").exists()

    def test_refreshes_session_transfer_skills_without_overwrite(self, tmp_path):
        from tapps_mcp.pipeline.platform_skills import SESSION_TRANSFER_SKILL_NAMES
        from tapps_mcp.pipeline.skill_managed_block import (
            PROJECT_REGION_HEADING,
            extract_block,
        )

        for skill_name in SESSION_TRANSFER_SKILL_NAMES:
            skill_dir = tmp_path / ".claude" / "skills" / skill_name
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("# stale handoff\n", encoding="utf-8")

        result = generate_skills(tmp_path, "claude")

        for skill_name in SESSION_TRANSFER_SKILL_NAMES:
            assert skill_name in result["updated"]
            content = (tmp_path / ".claude" / "skills" / skill_name / "SKILL.md").read_text()
            # TAP-6948 s3: no markers on disk yet, so refresh migrates the
            # stale body into the preserved project region below a fresh
            # managed block instead of overwriting it wholesale.
            assert extract_block(content) is not None
            assert PROJECT_REGION_HEADING in content
            assert "# stale handoff" in content
        assert "tapps-finish-task" in result["created"]

    def test_creates_directories(self, tmp_path):
        assert not (tmp_path / ".claude" / "skills").exists()
        generate_skills(tmp_path, "claude")
        assert (tmp_path / ".claude" / "skills" / "tapps-finish-task").is_dir()

    def test_result_dict_tracks_created(self, tmp_path):
        result = generate_skills(tmp_path, "claude")
        # Derived from the registry, not a literal: the hardcoded count went
        # stale twice (16 → 24) as skills were added.
        assert len(result["created"]) == len(CLAUDE_SKILLS)
        assert len(result["skipped"]) == 0

    def test_unknown_platform_returns_error(self, tmp_path):
        result = generate_skills(tmp_path, "unknown")
        assert "error" in result


class TestCustomizationsBlock:
    """TAP-6948 s3: unmanaged skills carry a preserved customizations region."""

    def test_skill_without_prior_content_gains_an_empty_region(self, tmp_path):
        from tapps_mcp.pipeline.platform_skills import SMART_MERGE_SKILL_NAMES
        from tapps_mcp.pipeline.skill_managed_block import MARKER_END, extract_block

        generate_skills(tmp_path, "claude")
        content = (tmp_path / ".claude" / "skills" / "tapps-finish-task" / "SKILL.md").read_text(
            encoding="utf-8"
        )

        assert "tapps-finish-task" not in SMART_MERGE_SKILL_NAMES
        assert extract_block(content) is not None
        below_end = content[content.find(MARKER_END) + len(MARKER_END) :]
        assert below_end.strip() == ""

    def test_local_customization_survives_a_force_refresh_byte_for_byte(self, tmp_path):
        generate_skills(tmp_path, "claude")
        target = tmp_path / ".claude" / "skills" / "tapps-finish-task" / "SKILL.md"
        custom = "\n\n<!-- project note: we always run this after lunch -->\n"
        target.write_text(target.read_text(encoding="utf-8") + custom, encoding="utf-8")

        generate_skills(tmp_path, "claude", overwrite=True)

        # Byte-for-byte: the customization survives even though the managed
        # block itself did not change (so this refresh is a no-op on the
        # platform body — "unchanged" or "refreshed" both preserve the tail).
        assert target.read_text(encoding="utf-8").endswith(custom)

    def test_covered_skill_count_is_derived_not_hardcoded(self, tmp_path):
        from tapps_mcp.pipeline.platform_skills import (
            CLAUDE_SKILLS,
            SMART_MERGE_SKILL_NAMES,
        )
        from tapps_mcp.pipeline.skill_managed_block import extract_block

        generate_skills(tmp_path, "claude")
        expected_unmanaged = set(CLAUDE_SKILLS) - SMART_MERGE_SKILL_NAMES
        assert expected_unmanaged, "registry must contain at least one unmanaged skill"

        marker_bearing = {
            skill_name
            for skill_name in expected_unmanaged
            if extract_block(
                (tmp_path / ".claude" / "skills" / skill_name / "SKILL.md").read_text(
                    encoding="utf-8"
                )
            )
            is not None
        }
        assert marker_bearing == expected_unmanaged

    def test_legacy_unmarked_skill_migrates_old_body_below_new_block(self, tmp_path):
        from tapps_mcp.pipeline.skill_managed_block import PROJECT_REGION_HEADING, extract_block

        skill_dir = tmp_path / ".claude" / "skills" / "tapps-security"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: tapps-security\n---\n\nhand-authored body\n", encoding="utf-8"
        )

        result = generate_skills(tmp_path, "claude", overwrite=True)

        assert "tapps-security" in result["updated"]
        content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        assert extract_block(content) is not None
        assert PROJECT_REGION_HEADING in content
        assert "hand-authored body" in content

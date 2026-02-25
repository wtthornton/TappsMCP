"""Tests for skills generation (Story 12.8).

Verifies that generate_skills() creates 3 SKILL.md files per platform with
correct frontmatter format differences between Claude Code and Cursor.
"""

from __future__ import annotations

from tapps_mcp.pipeline.platform_generators import generate_skills


class TestClaudeSkills:
    """Tests for Claude Code skill generation."""

    def test_creates_all_skills(self, tmp_path):
        generate_skills(tmp_path, "claude")
        base = tmp_path / ".claude" / "skills"
        assert (base / "tapps-score" / "SKILL.md").exists()
        assert (base / "tapps-gate" / "SKILL.md").exists()
        assert (base / "tapps-validate" / "SKILL.md").exists()
        assert (base / "tapps-review-pipeline" / "SKILL.md").exists()

    def test_score_skill_has_tools_string(self, tmp_path):
        """Claude Code SKILL.md has tools as a comma-separated string."""
        generate_skills(tmp_path, "claude")
        content = (tmp_path / ".claude" / "skills" / "tapps-score" / "SKILL.md").read_text()
        assert "tools:" in content
        assert "mcp__tapps-mcp__tapps_score_file" in content

    def test_score_skill_has_name(self, tmp_path):
        generate_skills(tmp_path, "claude")
        content = (tmp_path / ".claude" / "skills" / "tapps-score" / "SKILL.md").read_text()
        assert "name: tapps-score" in content

    def test_score_skill_body_references_mcp_tools(self, tmp_path):
        generate_skills(tmp_path, "claude")
        content = (tmp_path / ".claude" / "skills" / "tapps-score" / "SKILL.md").read_text()
        assert "mcp__tapps-mcp__tapps_score_file" in content
        assert "mcp__tapps-mcp__tapps_quick_check" in content

    def test_gate_skill_references_quality_gate(self, tmp_path):
        generate_skills(tmp_path, "claude")
        content = (tmp_path / ".claude" / "skills" / "tapps-gate" / "SKILL.md").read_text()
        assert "mcp__tapps-mcp__tapps_quality_gate" in content

    def test_validate_skill_references_validate_changed(self, tmp_path):
        generate_skills(tmp_path, "claude")
        content = (tmp_path / ".claude" / "skills" / "tapps-validate" / "SKILL.md").read_text()
        assert "mcp__tapps-mcp__tapps_validate_changed" in content

    def test_all_skills_have_frontmatter(self, tmp_path):
        generate_skills(tmp_path, "claude")
        base = tmp_path / ".claude" / "skills"
        for skill in ["tapps-score", "tapps-gate", "tapps-validate", "tapps-review-pipeline"]:
            content = (base / skill / "SKILL.md").read_text()
            assert content.startswith("---\n"), f"{skill} missing frontmatter"
            assert "name:" in content
            assert "description:" in content

    def test_review_pipeline_references_validate_and_checklist(self, tmp_path):
        generate_skills(tmp_path, "claude")
        base = tmp_path / ".claude" / "skills"
        content = (base / "tapps-review-pipeline" / "SKILL.md").read_text()
        assert "mcp__tapps-mcp__tapps_validate_changed" in content
        assert "mcp__tapps-mcp__tapps_checklist" in content
        assert "tapps-review-fixer" in content


class TestCursorSkills:
    """Tests for Cursor skill generation."""

    def test_creates_all_skills(self, tmp_path):
        generate_skills(tmp_path, "cursor")
        base = tmp_path / ".cursor" / "skills"
        assert (base / "tapps-score" / "SKILL.md").exists()
        assert (base / "tapps-gate" / "SKILL.md").exists()
        assert (base / "tapps-validate" / "SKILL.md").exists()
        assert (base / "tapps-review-pipeline" / "SKILL.md").exists()

    def test_review_pipeline_uses_short_tool_names(self, tmp_path):
        generate_skills(tmp_path, "cursor")
        base = tmp_path / ".cursor" / "skills"
        content = (base / "tapps-review-pipeline" / "SKILL.md").read_text()
        assert "tapps_validate_changed" in content
        assert "tapps_checklist" in content
        assert "mcp__tapps-mcp__" not in content

    def test_score_skill_has_mcp_tools_list(self, tmp_path):
        """Cursor SKILL.md has mcp_tools as a YAML list."""
        generate_skills(tmp_path, "cursor")
        content = (tmp_path / ".cursor" / "skills" / "tapps-score" / "SKILL.md").read_text()
        assert "mcp_tools:" in content
        assert "  - tapps_score_file" in content
        assert "  - tapps_quick_check" in content

    def test_score_skill_has_name(self, tmp_path):
        generate_skills(tmp_path, "cursor")
        content = (tmp_path / ".cursor" / "skills" / "tapps-score" / "SKILL.md").read_text()
        assert "name: tapps-score" in content

    def test_cursor_body_uses_short_tool_names(self, tmp_path):
        """Cursor skills use short names (no mcp__tapps-mcp__ prefix)."""
        generate_skills(tmp_path, "cursor")
        content = (tmp_path / ".cursor" / "skills" / "tapps-score" / "SKILL.md").read_text()
        assert "tapps_quick_check" in content
        assert "mcp__tapps-mcp__" not in content

    def test_gate_skill_references_quality_gate(self, tmp_path):
        generate_skills(tmp_path, "cursor")
        content = (tmp_path / ".cursor" / "skills" / "tapps-gate" / "SKILL.md").read_text()
        assert "tapps_quality_gate" in content

    def test_validate_skill_references_validate_changed(self, tmp_path):
        generate_skills(tmp_path, "cursor")
        content = (tmp_path / ".cursor" / "skills" / "tapps-validate" / "SKILL.md").read_text()
        assert "tapps_validate_changed" in content


class TestSkipExisting:
    """Tests for skip-on-exists behavior."""

    def test_skips_existing_skill(self, tmp_path):
        skill_dir = tmp_path / ".claude" / "skills" / "tapps-score"
        skill_dir.mkdir(parents=True)
        custom = "# My custom skill\n"
        (skill_dir / "SKILL.md").write_text(custom)

        result = generate_skills(tmp_path, "claude")

        assert "tapps-score" in result["skipped"]
        assert (skill_dir / "SKILL.md").read_text() == custom
        # Other skills should still be created
        assert (tmp_path / ".claude" / "skills" / "tapps-gate" / "SKILL.md").exists()
        assert (tmp_path / ".claude" / "skills" / "tapps-validate" / "SKILL.md").exists()

    def test_creates_directories(self, tmp_path):
        """Creates skill subdirectories even when parent doesn't exist."""
        assert not (tmp_path / ".claude" / "skills").exists()
        generate_skills(tmp_path, "claude")
        assert (tmp_path / ".claude" / "skills" / "tapps-score").is_dir()

    def test_result_dict_tracks_created(self, tmp_path):
        result = generate_skills(tmp_path, "claude")
        assert len(result["created"]) == 4
        assert len(result["skipped"]) == 0

    def test_unknown_platform_returns_error(self, tmp_path):
        result = generate_skills(tmp_path, "unknown")
        assert "error" in result

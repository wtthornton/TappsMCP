"""Tests for subagent definition generation (Story 12.6).

Verifies that generate_subagent_definitions() creates 3 agent .md files per
platform with correct YAML frontmatter format differences between Claude Code
and Cursor.
"""

from __future__ import annotations

from tapps_mcp.pipeline.platform_generators import generate_subagent_definitions


class TestClaudeAgents:
    """Tests for Claude Code subagent generation."""

    def test_creates_all_agents(self, tmp_path):
        generate_subagent_definitions(tmp_path, "claude")
        agents_dir = tmp_path / ".claude" / "agents"
        assert (agents_dir / "tapps-reviewer.md").exists()
        assert (agents_dir / "tapps-researcher.md").exists()
        assert (agents_dir / "tapps-validator.md").exists()
        assert (agents_dir / "tapps-review-fixer.md").exists()

    def test_reviewer_has_comma_separated_tools(self, tmp_path):
        generate_subagent_definitions(tmp_path, "claude")
        content = (tmp_path / ".claude" / "agents" / "tapps-reviewer.md").read_text()
        assert "tools: Read, Glob, Grep" in content

    def test_reviewer_has_model_sonnet(self, tmp_path):
        generate_subagent_definitions(tmp_path, "claude")
        content = (tmp_path / ".claude" / "agents" / "tapps-reviewer.md").read_text()
        assert "model: sonnet" in content

    def test_reviewer_has_permission_mode(self, tmp_path):
        generate_subagent_definitions(tmp_path, "claude")
        content = (tmp_path / ".claude" / "agents" / "tapps-reviewer.md").read_text()
        assert "permissionMode: dontAsk" in content

    def test_reviewer_has_memory_project(self, tmp_path):
        generate_subagent_definitions(tmp_path, "claude")
        content = (tmp_path / ".claude" / "agents" / "tapps-reviewer.md").read_text()
        assert "memory: project" in content

    def test_researcher_has_model_haiku(self, tmp_path):
        generate_subagent_definitions(tmp_path, "claude")
        content = (tmp_path / ".claude" / "agents" / "tapps-researcher.md").read_text()
        assert "model: haiku" in content

    def test_researcher_has_memory_project(self, tmp_path):
        generate_subagent_definitions(tmp_path, "claude")
        content = (tmp_path / ".claude" / "agents" / "tapps-researcher.md").read_text()
        assert "memory: project" in content

    def test_validator_has_model_sonnet(self, tmp_path):
        generate_subagent_definitions(tmp_path, "claude")
        content = (tmp_path / ".claude" / "agents" / "tapps-validator.md").read_text()
        assert "model: sonnet" in content

    def test_validator_has_permission_mode(self, tmp_path):
        generate_subagent_definitions(tmp_path, "claude")
        content = (tmp_path / ".claude" / "agents" / "tapps-validator.md").read_text()
        assert "permissionMode: dontAsk" in content

    def test_reviewer_body_references_mcp_tools(self, tmp_path):
        generate_subagent_definitions(tmp_path, "claude")
        content = (tmp_path / ".claude" / "agents" / "tapps-reviewer.md").read_text()
        assert "mcp__tapps-mcp__tapps_quick_check" in content

    def test_agents_have_yaml_frontmatter(self, tmp_path):
        generate_subagent_definitions(tmp_path, "claude")
        for name in [
            "tapps-reviewer.md",
            "tapps-researcher.md",
            "tapps-validator.md",
            "tapps-review-fixer.md",
        ]:
            content = (tmp_path / ".claude" / "agents" / name).read_text()
            assert content.startswith("---\n"), f"{name} missing YAML frontmatter"
            # Should have closing ---
            assert content.count("---") >= 2, f"{name} missing closing ---"

    def test_review_fixer_has_write_and_edit_tools(self, tmp_path):
        generate_subagent_definitions(tmp_path, "claude")
        content = (tmp_path / ".claude" / "agents" / "tapps-review-fixer.md").read_text()
        assert "Write" in content
        assert "Edit" in content
        assert "Bash" in content

    def test_review_fixer_references_score_and_gate(self, tmp_path):
        generate_subagent_definitions(tmp_path, "claude")
        content = (tmp_path / ".claude" / "agents" / "tapps-review-fixer.md").read_text()
        assert "tapps_score_file" in content
        assert "tapps_quality_gate" in content

    def test_review_fixer_has_model_sonnet(self, tmp_path):
        generate_subagent_definitions(tmp_path, "claude")
        content = (tmp_path / ".claude" / "agents" / "tapps-review-fixer.md").read_text()
        assert "model: sonnet" in content


class TestCursorAgents:
    """Tests for Cursor subagent generation."""

    def test_creates_all_agents(self, tmp_path):
        generate_subagent_definitions(tmp_path, "cursor")
        agents_dir = tmp_path / ".cursor" / "agents"
        assert (agents_dir / "tapps-reviewer.md").exists()
        assert (agents_dir / "tapps-researcher.md").exists()
        assert (agents_dir / "tapps-validator.md").exists()
        assert (agents_dir / "tapps-review-fixer.md").exists()

    def test_review_fixer_has_edit_tools(self, tmp_path):
        generate_subagent_definitions(tmp_path, "cursor")
        content = (tmp_path / ".cursor" / "agents" / "tapps-review-fixer.md").read_text()
        assert "edit_file" in content
        assert "run_terminal_command" in content

    def test_review_fixer_uses_short_tool_names(self, tmp_path):
        generate_subagent_definitions(tmp_path, "cursor")
        content = (tmp_path / ".cursor" / "agents" / "tapps-review-fixer.md").read_text()
        assert "tapps_score_file" in content
        assert "mcp__tapps-mcp__" not in content

    def test_reviewer_uses_yaml_list_tools(self, tmp_path):
        """Cursor uses YAML array for tools, not comma-separated string."""
        generate_subagent_definitions(tmp_path, "cursor")
        content = (tmp_path / ".cursor" / "agents" / "tapps-reviewer.md").read_text()
        # Should have tools as a YAML list, not a comma-separated string
        assert "tools:\n" in content
        assert "  - code_search" in content
        assert "  - read_file" in content

    def test_reviewer_has_model_sonnet(self, tmp_path):
        generate_subagent_definitions(tmp_path, "cursor")
        content = (tmp_path / ".cursor" / "agents" / "tapps-reviewer.md").read_text()
        assert "model: sonnet" in content

    def test_researcher_has_model_haiku(self, tmp_path):
        generate_subagent_definitions(tmp_path, "cursor")
        content = (tmp_path / ".cursor" / "agents" / "tapps-researcher.md").read_text()
        assert "model: haiku" in content

    def test_cursor_no_permission_mode(self, tmp_path):
        """Cursor doesn't support permissionMode; uses readonly instead."""
        generate_subagent_definitions(tmp_path, "cursor")
        content = (tmp_path / ".cursor" / "agents" / "tapps-reviewer.md").read_text()
        assert "permissionMode" not in content
        assert "readonly:" in content

    def test_cursor_no_memory_field(self, tmp_path):
        """Cursor doesn't support the memory field."""
        generate_subagent_definitions(tmp_path, "cursor")
        content = (tmp_path / ".cursor" / "agents" / "tapps-reviewer.md").read_text()
        assert "memory:" not in content

    def test_cursor_body_uses_short_tool_names(self, tmp_path):
        """Cursor agents use short tool names (no mcp__tapps-mcp__ prefix)."""
        generate_subagent_definitions(tmp_path, "cursor")
        content = (tmp_path / ".cursor" / "agents" / "tapps-reviewer.md").read_text()
        assert "tapps_quick_check" in content
        assert "mcp__tapps-mcp__" not in content


class TestSkipExisting:
    """Tests for skip-on-exists behavior."""

    def test_skips_existing_claude_agent(self, tmp_path):
        agents_dir = tmp_path / ".claude" / "agents"
        agents_dir.mkdir(parents=True)
        custom = "# My custom reviewer\n"
        (agents_dir / "tapps-reviewer.md").write_text(custom)

        result = generate_subagent_definitions(tmp_path, "claude")

        assert "tapps-reviewer.md" in result["skipped"]
        assert (agents_dir / "tapps-reviewer.md").read_text() == custom
        # Other agents should still be created
        assert (agents_dir / "tapps-researcher.md").exists()
        assert (agents_dir / "tapps-validator.md").exists()

    def test_result_dict_tracks_created_and_skipped(self, tmp_path):
        result = generate_subagent_definitions(tmp_path, "claude")
        assert len(result["created"]) == 4
        assert len(result["skipped"]) == 0

    def test_unknown_platform_returns_error(self, tmp_path):
        result = generate_subagent_definitions(tmp_path, "unknown")
        assert "error" in result

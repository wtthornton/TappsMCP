"""Tests for documentation automation generators (Epic 86)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.pipeline.platform_docs_automation import (
    CLAUDE_DOC_AGENTS,
    CURSOR_DOC_AGENTS,
    DOCS_SKILLS,
    generate_docs_agents,
    generate_docs_automation,
    generate_docs_skills,
)


# ---------------------------------------------------------------------------
# Template tests
# ---------------------------------------------------------------------------


class TestDocAgentTemplates:
    def test_claude_agents_have_required_keys(self) -> None:
        assert "tapps-docs-reviewer.md" in CLAUDE_DOC_AGENTS
        assert "tapps-docs-validator.md" in CLAUDE_DOC_AGENTS

    def test_cursor_agents_have_required_keys(self) -> None:
        assert "tapps-docs-reviewer.md" in CURSOR_DOC_AGENTS
        assert "tapps-docs-validator.md" in CURSOR_DOC_AGENTS

    def test_agents_contain_frontmatter(self) -> None:
        for name, content in CLAUDE_DOC_AGENTS.items():
            assert content.startswith("---\n"), f"{name} missing frontmatter"
            assert "name:" in content, f"{name} missing name field"
            assert "description:" in content, f"{name} missing description field"

    def test_agents_reference_docsmcp_tools(self) -> None:
        for name, content in CLAUDE_DOC_AGENTS.items():
            assert "docs-mcp" in content or "docs_check" in content, (
                f"{name} does not reference DocsMCP tools"
            )


class TestDocSkillTemplates:
    def test_all_skills_defined(self) -> None:
        assert "tapps-docs-report" in DOCS_SKILLS
        assert "tapps-docs-validate" in DOCS_SKILLS
        assert "tapps-docs-generate" in DOCS_SKILLS

    def test_skills_contain_frontmatter(self) -> None:
        for name, content in DOCS_SKILLS.items():
            assert content.startswith("---\n"), f"{name} missing frontmatter"
            assert "name:" in content, f"{name} missing name"
            assert "allowed-tools:" in content, f"{name} missing allowed-tools"

    def test_skills_reference_docsmcp_tools(self) -> None:
        for name, content in DOCS_SKILLS.items():
            assert "docs-mcp" in content, f"{name} does not reference docs-mcp tools"


# ---------------------------------------------------------------------------
# Agent generation tests
# ---------------------------------------------------------------------------


class TestGenerateDocsAgents:
    def test_claude_agents_created(self, tmp_path: Path) -> None:
        result = generate_docs_agents(tmp_path, "claude")

        assert len(result["created"]) == 2
        assert "tapps-docs-reviewer.md" in result["created"]
        assert "tapps-docs-validator.md" in result["created"]

        # Verify files exist
        agents_dir = tmp_path / ".claude" / "agents"
        assert (agents_dir / "tapps-docs-reviewer.md").exists()
        assert (agents_dir / "tapps-docs-validator.md").exists()

    def test_cursor_agents_created(self, tmp_path: Path) -> None:
        result = generate_docs_agents(tmp_path, "cursor")

        assert len(result["created"]) == 2
        agents_dir = tmp_path / ".cursor" / "agents"
        assert (agents_dir / "tapps-docs-reviewer.md").exists()

    def test_existing_agents_skipped(self, tmp_path: Path) -> None:
        # First run
        generate_docs_agents(tmp_path, "claude")
        # Second run
        result = generate_docs_agents(tmp_path, "claude")

        assert len(result["skipped"]) == 2
        assert len(result["created"]) == 0

    def test_overwrite_mode(self, tmp_path: Path) -> None:
        generate_docs_agents(tmp_path, "claude")
        result = generate_docs_agents(tmp_path, "claude", overwrite=True)

        assert len(result["updated"]) == 2
        assert len(result["skipped"]) == 0

    def test_unknown_platform(self, tmp_path: Path) -> None:
        result = generate_docs_agents(tmp_path, "unknown")
        assert "error" in result


# ---------------------------------------------------------------------------
# Skill generation tests
# ---------------------------------------------------------------------------


class TestGenerateDocsSkills:
    def test_claude_skills_created(self, tmp_path: Path) -> None:
        result = generate_docs_skills(tmp_path, "claude")

        assert len(result["created"]) == 3
        assert "tapps-docs-report" in result["created"]
        assert "tapps-docs-validate" in result["created"]
        assert "tapps-docs-generate" in result["created"]

        # Verify files exist
        skills_dir = tmp_path / ".claude" / "skills"
        assert (skills_dir / "tapps-docs-report" / "SKILL.md").exists()
        assert (skills_dir / "tapps-docs-validate" / "SKILL.md").exists()
        assert (skills_dir / "tapps-docs-generate" / "SKILL.md").exists()

    def test_cursor_skills_created(self, tmp_path: Path) -> None:
        result = generate_docs_skills(tmp_path, "cursor")

        assert len(result["created"]) == 3
        skills_dir = tmp_path / ".cursor" / "skills"
        assert (skills_dir / "tapps-docs-report" / "SKILL.md").exists()

    def test_existing_skills_skipped(self, tmp_path: Path) -> None:
        generate_docs_skills(tmp_path, "claude")
        result = generate_docs_skills(tmp_path, "claude")

        assert len(result["skipped"]) == 3
        assert len(result["created"]) == 0

    def test_overwrite_mode(self, tmp_path: Path) -> None:
        generate_docs_skills(tmp_path, "claude")
        result = generate_docs_skills(tmp_path, "claude", overwrite=True)

        assert len(result["updated"]) == 3

    def test_unknown_platform(self, tmp_path: Path) -> None:
        result = generate_docs_skills(tmp_path, "unknown")
        assert "error" in result


# ---------------------------------------------------------------------------
# Combined automation tests
# ---------------------------------------------------------------------------


class TestGenerateDocsAutomation:
    def test_combined_output(self, tmp_path: Path) -> None:
        result = generate_docs_automation(tmp_path, "claude")

        assert "agents" in result
        assert "skills" in result
        assert len(result["agents"]["created"]) == 2
        assert len(result["skills"]["created"]) == 3

    def test_idempotent(self, tmp_path: Path) -> None:
        generate_docs_automation(tmp_path, "claude")
        result = generate_docs_automation(tmp_path, "claude")

        assert len(result["agents"]["skipped"]) == 2
        assert len(result["skills"]["skipped"]) == 3

    def test_both_platforms(self, tmp_path: Path) -> None:
        result_claude = generate_docs_automation(tmp_path, "claude")
        result_cursor = generate_docs_automation(tmp_path, "cursor")

        assert len(result_claude["agents"]["created"]) == 2
        assert len(result_cursor["agents"]["created"]) == 2

        # Both should have their own dirs
        assert (tmp_path / ".claude" / "agents" / "tapps-docs-reviewer.md").exists()
        assert (tmp_path / ".cursor" / "agents" / "tapps-docs-reviewer.md").exists()

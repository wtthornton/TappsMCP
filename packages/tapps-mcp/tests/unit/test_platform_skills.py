"""Tests for platform_skills.py skill template frontmatter.

Verifies that all Claude Code skill templates use the correct 2026
frontmatter fields: allowed-tools, argument-hint, disable-model-invocation,
context, model, and agent. Epic 76: description length 1-1024 chars,
allowed-tools space-delimited, skills spec validator.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tapps_mcp.pipeline.platform_skills import (
    CLAUDE_SKILLS,
    CURSOR_SKILLS,
    generate_skills,
)
from tapps_mcp.pipeline.skills_validator import (
    get_description_from_frontmatter_raw,
    validate_skill_frontmatter,
)

# ---------------------------------------------------------------------------
# Helper to extract frontmatter from a skill template string
# ---------------------------------------------------------------------------


def _get_frontmatter(template: str) -> str:
    """Return the YAML frontmatter block (between --- markers)."""
    parts = template.split("---", 2)
    assert len(parts) >= 3, "Template missing frontmatter delimiters"
    return parts[1]


# ---------------------------------------------------------------------------
# Claude skill frontmatter: allowed-tools (renamed from tools)
# ---------------------------------------------------------------------------


class TestClaudeAllowedTools:
    """All Claude skills must use allowed-tools, not tools."""

    def test_no_tools_field_in_any_skill(self) -> None:
        for name, content in CLAUDE_SKILLS.items():
            fm = _get_frontmatter(content)
            assert "\ntools:" not in fm, f"{name} still uses 'tools:' instead of 'allowed-tools:'"

    def test_all_skills_have_allowed_tools(self) -> None:
        for name, content in CLAUDE_SKILLS.items():
            fm = _get_frontmatter(content)
            assert "allowed-tools:" in fm, f"{name} missing 'allowed-tools:' field"


# ---------------------------------------------------------------------------
# Claude skill frontmatter: argument-hint
# ---------------------------------------------------------------------------


class TestClaudeArgumentHint:
    """Skills that accept arguments must have argument-hint."""

    @pytest.mark.parametrize(
        ("skill_name", "expected_hint"),
        [
            ("tapps-score", "[file-path]"),
            ("tapps-gate", "[file-path]"),
            ("tapps-research", "[library] [topic]"),
            ("tapps-memory", "[action] [key]"),
            ("tapps-security", "[file-path]"),
        ],
    )
    def test_argument_hint_present(self, skill_name: str, expected_hint: str) -> None:
        fm = _get_frontmatter(CLAUDE_SKILLS[skill_name])
        assert f'argument-hint: "{expected_hint}"' in fm

    def test_validate_no_argument_hint(self) -> None:
        fm = _get_frontmatter(CLAUDE_SKILLS["tapps-validate"])
        assert "argument-hint:" not in fm

    def test_review_pipeline_no_argument_hint(self) -> None:
        fm = _get_frontmatter(CLAUDE_SKILLS["tapps-review-pipeline"])
        assert "argument-hint:" not in fm


# ---------------------------------------------------------------------------
# Claude skill frontmatter: disable-model-invocation
# ---------------------------------------------------------------------------


class TestClaudeDisableModelInvocation:
    """Workflow-only skills must have disable-model-invocation: true."""

    @pytest.mark.parametrize("skill_name", ["tapps-gate", "tapps-validate"])
    def test_disable_model_invocation_present(self, skill_name: str) -> None:
        fm = _get_frontmatter(CLAUDE_SKILLS[skill_name])
        assert "disable-model-invocation: true" in fm

    @pytest.mark.parametrize(
        "skill_name",
        [
            "tapps-score",
            "tapps-review-pipeline",
            "tapps-research",
            "tapps-security",
            "tapps-memory",
        ],
    )
    def test_disable_model_invocation_absent(self, skill_name: str) -> None:
        fm = _get_frontmatter(CLAUDE_SKILLS[skill_name])
        assert "disable-model-invocation:" not in fm


# ---------------------------------------------------------------------------
# Claude skill frontmatter: context
# ---------------------------------------------------------------------------


class TestClaudeContext:
    """Forked-context skills must have context: fork."""

    @pytest.mark.parametrize("skill_name", ["tapps-review-pipeline", "tapps-research"])
    def test_context_fork_present(self, skill_name: str) -> None:
        fm = _get_frontmatter(CLAUDE_SKILLS[skill_name])
        assert "context: fork" in fm

    @pytest.mark.parametrize(
        "skill_name",
        ["tapps-score", "tapps-gate", "tapps-validate", "tapps-security", "tapps-memory"],
    )
    def test_context_absent(self, skill_name: str) -> None:
        fm = _get_frontmatter(CLAUDE_SKILLS[skill_name])
        assert "context:" not in fm


# ---------------------------------------------------------------------------
# Claude skill frontmatter: model
# ---------------------------------------------------------------------------


class TestClaudeModel:
    """All skills should use full model IDs."""

    def test_research_has_model_sonnet(self) -> None:
        fm = _get_frontmatter(CLAUDE_SKILLS["tapps-research"])
        assert "model: claude-sonnet-4-6" in fm

    @pytest.mark.parametrize(
        "skill_name,expected_model",
        [
            ("tapps-score", "claude-haiku-4-5-20251001"),
            ("tapps-gate", "claude-haiku-4-5-20251001"),
            ("tapps-validate", "claude-haiku-4-5-20251001"),
            ("tapps-review-pipeline", "claude-sonnet-4-6"),
            ("tapps-security", "claude-sonnet-4-6"),
            ("tapps-memory", "claude-sonnet-4-6"),
        ],
    )
    def test_model_present(self, skill_name: str, expected_model: str) -> None:
        fm = _get_frontmatter(CLAUDE_SKILLS[skill_name])
        assert f"model: {expected_model}" in fm


# ---------------------------------------------------------------------------
# Claude skill frontmatter: agent
# ---------------------------------------------------------------------------


class TestClaudeAgent:
    """Review pipeline should use general-purpose agent."""

    def test_review_pipeline_has_agent(self) -> None:
        fm = _get_frontmatter(CLAUDE_SKILLS["tapps-review-pipeline"])
        assert "agent: general-purpose" in fm

    @pytest.mark.parametrize(
        "skill_name",
        [
            "tapps-score",
            "tapps-gate",
            "tapps-validate",
            "tapps-research",
            "tapps-security",
            "tapps-memory",
        ],
    )
    def test_agent_absent(self, skill_name: str) -> None:
        fm = _get_frontmatter(CLAUDE_SKILLS[skill_name])
        assert "agent:" not in fm


# ---------------------------------------------------------------------------
# Cursor skills: unchanged (should NOT have allowed-tools)
# ---------------------------------------------------------------------------


class TestCursorSkillsUnchanged:
    """Cursor skills should still use mcp_tools, not allowed-tools."""

    def test_cursor_skills_use_mcp_tools(self) -> None:
        for name, content in CURSOR_SKILLS.items():
            fm = _get_frontmatter(content)
            assert "mcp_tools:" in fm, f"Cursor {name} should use 'mcp_tools:'"
            assert "allowed-tools:" not in fm, f"Cursor {name} should NOT use 'allowed-tools:'"


# ---------------------------------------------------------------------------
# Generation tests
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Epic 76.1: Description length 1-1024 chars (agentskills.io)
# ---------------------------------------------------------------------------


class TestSkillDescriptionLength:
    """All skills must have description length 1-1024 per Agent Skills spec."""

    @pytest.mark.parametrize("skill_name", list(CLAUDE_SKILLS))
    def test_claude_skill_description_length(self, skill_name: str) -> None:
        content = CLAUDE_SKILLS[skill_name]
        fm = _get_frontmatter(content)
        desc = get_description_from_frontmatter_raw(fm)
        assert len(desc) >= 1, f"{skill_name}: description empty"
        assert len(desc) <= 1024, f"{skill_name}: description exceeds 1024 chars (got {len(desc)})"

    @pytest.mark.parametrize("skill_name", list(CURSOR_SKILLS))
    def test_cursor_skill_description_length(self, skill_name: str) -> None:
        content = CURSOR_SKILLS[skill_name]
        fm = _get_frontmatter(content)
        desc = get_description_from_frontmatter_raw(fm)
        assert len(desc) >= 1, f"{skill_name}: description empty"
        assert len(desc) <= 1024, f"{skill_name}: description exceeds 1024 chars (got {len(desc)})"


# ---------------------------------------------------------------------------
# Epic 76.4: Skills spec validator
# ---------------------------------------------------------------------------


class TestSkillsSpecValidator:
    """All built-in skills pass the spec validator."""

    def _parse_fm(self, content: str) -> dict:
        fm = _get_frontmatter(content)
        return yaml.safe_load(fm) or {}

    @pytest.mark.parametrize("skill_name", list(CLAUDE_SKILLS))
    def test_claude_skills_pass_validator(self, skill_name: str) -> None:
        content = CLAUDE_SKILLS[skill_name]
        fm = self._parse_fm(content)
        errors = validate_skill_frontmatter(skill_name, fm)
        assert not errors, f"{skill_name}: {errors}"

    @pytest.mark.parametrize("skill_name", list(CURSOR_SKILLS))
    def test_cursor_skills_pass_validator(self, skill_name: str) -> None:
        content = CURSOR_SKILLS[skill_name]
        fm = self._parse_fm(content)
        errors = validate_skill_frontmatter(skill_name, fm, check_allowed_tools_format=False)
        assert not errors, f"{skill_name}: {errors}"


# ---------------------------------------------------------------------------
# Generation tests
# ---------------------------------------------------------------------------


class TestGenerateSkills:
    """Verify generate_skills writes correct frontmatter to disk."""

    def test_generated_claude_skill_has_allowed_tools(self, tmp_path: Path) -> None:
        generate_skills(tmp_path, "claude")
        content = (tmp_path / ".claude" / "skills" / "tapps-score" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        assert "allowed-tools:" in content
        assert "\ntools:" not in content

    def test_generated_claude_gate_has_disable_model(self, tmp_path: Path) -> None:
        generate_skills(tmp_path, "claude")
        content = (tmp_path / ".claude" / "skills" / "tapps-gate" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        assert "disable-model-invocation: true" in content

    def test_generated_claude_research_has_context_fork(self, tmp_path: Path) -> None:
        generate_skills(tmp_path, "claude")
        content = (tmp_path / ".claude" / "skills" / "tapps-research" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        assert "context: fork" in content
        assert "model: claude-sonnet-4-6" in content


# ---------------------------------------------------------------------------
# TAP-980 Phase A + TAP-977: linear-issue upgrade + tapps-finish-task
# ---------------------------------------------------------------------------


class TestLinearIssueSkillUpdated:
    """The linear-issue skill must grant save_issue and docs_generate_epic."""

    def test_linear_issue_has_save_issue(self) -> None:
        assert "mcp__plugin_linear_linear__save_issue" in CLAUDE_SKILLS["linear-issue"]

    def test_linear_issue_has_docs_generate_epic(self) -> None:
        assert "mcp__docs-mcp__docs_generate_epic" in CLAUDE_SKILLS["linear-issue"]

    def test_linear_issue_description_is_mandatory(self) -> None:
        content = CLAUDE_SKILLS["linear-issue"]
        assert "MANDATORY for all Linear writes" in content

    def test_linear_issue_documents_markdown_workarounds(self) -> None:
        content = CLAUDE_SKILLS["linear-issue"]
        # Skill body has "Use numbered lists, not bulleted lists" — match case-insensitively.
        assert "numbered lists, not bulleted" in content.lower()
        assert "Wrap file paths in backticks" in content

    def test_linear_issue_argument_hint_covers_epic(self) -> None:
        content = CLAUDE_SKILLS["linear-issue"]
        assert "create-epic" in content

    def test_generated_linear_issue_has_save_issue(self, tmp_path: Path) -> None:
        generate_skills(tmp_path, "claude")
        content = (
            tmp_path / ".claude" / "skills" / "linear-issue" / "SKILL.md"
        ).read_text(encoding="utf-8")
        assert "mcp__plugin_linear_linear__save_issue" in content


class TestFinishTaskSkill:
    """TAP-977: tapps-finish-task bundles validate -> checklist -> memory."""

    def test_claude_skill_registered(self) -> None:
        assert "tapps-finish-task" in CLAUDE_SKILLS

    def test_cursor_skill_registered(self) -> None:
        assert "tapps-finish-task" in CURSOR_SKILLS

    def test_allowed_tools_includes_validate_changed(self) -> None:
        content = CLAUDE_SKILLS["tapps-finish-task"]
        assert "mcp__tapps-mcp__tapps_validate_changed" in content

    def test_allowed_tools_includes_checklist(self) -> None:
        content = CLAUDE_SKILLS["tapps-finish-task"]
        assert "mcp__tapps-mcp__tapps_checklist" in content

    def test_allowed_tools_includes_memory(self) -> None:
        content = CLAUDE_SKILLS["tapps-finish-task"]
        assert "mcp__tapps-mcp__tapps_memory" in content

    def test_body_references_three_required_steps(self) -> None:
        content = CLAUDE_SKILLS["tapps-finish-task"]
        assert "Validate changed files" in content
        assert "Verify the checklist" in content
        assert "Save learnings" in content

    def test_generated_claude_finish_task_skill(self, tmp_path: Path) -> None:
        generate_skills(tmp_path, "claude")
        target = tmp_path / ".claude" / "skills" / "tapps-finish-task" / "SKILL.md"
        assert target.exists()
        content = target.read_text(encoding="utf-8")
        assert "tapps_validate_changed" in content
        assert "tapps_checklist" in content

    def test_generated_cursor_finish_task_skill(self, tmp_path: Path) -> None:
        generate_skills(tmp_path, "cursor")
        target = tmp_path / ".cursor" / "skills" / "tapps-finish-task" / "SKILL.md"
        assert target.exists()

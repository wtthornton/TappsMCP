"""Tests for platform_skills.py skill template frontmatter.

Verifies that all Claude Code skill templates use the correct 2026
frontmatter fields: allowed-tools, argument-hint, disable-model-invocation,
context, model, and agent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.pipeline.platform_skills import (
    CLAUDE_SKILLS,
    CURSOR_SKILLS,
    generate_skills,
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
            assert "\ntools:" not in fm, (
                f"{name} still uses 'tools:' instead of 'allowed-tools:'"
            )

    def test_all_skills_have_allowed_tools(self) -> None:
        for name, content in CLAUDE_SKILLS.items():
            fm = _get_frontmatter(content)
            assert "allowed-tools:" in fm, (
                f"{name} missing 'allowed-tools:' field"
            )


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
            ("tapps-research", "[question]"),
            ("tapps-memory", "[action] [key]"),
            ("tapps-security", "[file-path]"),
        ],
    )
    def test_argument_hint_present(
        self, skill_name: str, expected_hint: str
    ) -> None:
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
        ["tapps-score", "tapps-review-pipeline", "tapps-research",
         "tapps-security", "tapps-memory"],
    )
    def test_disable_model_invocation_absent(self, skill_name: str) -> None:
        fm = _get_frontmatter(CLAUDE_SKILLS[skill_name])
        assert "disable-model-invocation:" not in fm


# ---------------------------------------------------------------------------
# Claude skill frontmatter: context
# ---------------------------------------------------------------------------


class TestClaudeContext:
    """Forked-context skills must have context: fork."""

    @pytest.mark.parametrize(
        "skill_name", ["tapps-review-pipeline", "tapps-research"]
    )
    def test_context_fork_present(self, skill_name: str) -> None:
        fm = _get_frontmatter(CLAUDE_SKILLS[skill_name])
        assert "context: fork" in fm

    @pytest.mark.parametrize(
        "skill_name",
        ["tapps-score", "tapps-gate", "tapps-validate",
         "tapps-security", "tapps-memory"],
    )
    def test_context_absent(self, skill_name: str) -> None:
        fm = _get_frontmatter(CLAUDE_SKILLS[skill_name])
        assert "context:" not in fm


# ---------------------------------------------------------------------------
# Claude skill frontmatter: model
# ---------------------------------------------------------------------------


class TestClaudeModel:
    """Research skill should use haiku model."""

    def test_research_has_model_haiku(self) -> None:
        fm = _get_frontmatter(CLAUDE_SKILLS["tapps-research"])
        assert "model: haiku" in fm

    @pytest.mark.parametrize(
        "skill_name",
        ["tapps-score", "tapps-gate", "tapps-validate",
         "tapps-review-pipeline", "tapps-security", "tapps-memory"],
    )
    def test_model_absent(self, skill_name: str) -> None:
        fm = _get_frontmatter(CLAUDE_SKILLS[skill_name])
        assert "model:" not in fm


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
        ["tapps-score", "tapps-gate", "tapps-validate",
         "tapps-research", "tapps-security", "tapps-memory"],
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
            assert "mcp_tools:" in fm, (
                f"Cursor {name} should use 'mcp_tools:'"
            )
            assert "allowed-tools:" not in fm, (
                f"Cursor {name} should NOT use 'allowed-tools:'"
            )


# ---------------------------------------------------------------------------
# Generation tests
# ---------------------------------------------------------------------------


class TestGenerateSkills:
    """Verify generate_skills writes correct frontmatter to disk."""

    def test_generated_claude_skill_has_allowed_tools(
        self, tmp_path: Path
    ) -> None:
        generate_skills(tmp_path, "claude")
        content = (
            tmp_path / ".claude" / "skills" / "tapps-score" / "SKILL.md"
        ).read_text(encoding="utf-8")
        assert "allowed-tools:" in content
        assert "\ntools:" not in content

    def test_generated_claude_gate_has_disable_model(
        self, tmp_path: Path
    ) -> None:
        generate_skills(tmp_path, "claude")
        content = (
            tmp_path / ".claude" / "skills" / "tapps-gate" / "SKILL.md"
        ).read_text(encoding="utf-8")
        assert "disable-model-invocation: true" in content

    def test_generated_claude_research_has_context_fork(
        self, tmp_path: Path
    ) -> None:
        generate_skills(tmp_path, "claude")
        content = (
            tmp_path / ".claude" / "skills" / "tapps-research" / "SKILL.md"
        ).read_text(encoding="utf-8")
        assert "context: fork" in content
        assert "model: haiku" in content

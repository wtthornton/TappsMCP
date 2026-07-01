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
    DEPRECATED_TAPPS_SKILLS,
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
# TAP-3930: deprecated wrapper skills removed from templates
# ---------------------------------------------------------------------------


class TestDeprecatedSkillsRemoved:
    """v3.12.0 removed single-tool wrapper skills from generated output."""

    @pytest.mark.parametrize("skill_name", sorted(DEPRECATED_TAPPS_SKILLS))
    def test_deprecated_absent_from_claude_templates(self, skill_name: str) -> None:
        assert skill_name not in CLAUDE_SKILLS

    @pytest.mark.parametrize("skill_name", sorted(DEPRECATED_TAPPS_SKILLS))
    def test_deprecated_absent_from_cursor_templates(self, skill_name: str) -> None:
        assert skill_name not in CURSOR_SKILLS


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
        # orchestration-prompt, like continuous-learning-v2, is a host-agnostic
        # prose/meta skill with no tool-grant frontmatter (shared body across hosts).
        no_tool_grant_skills = {"continuous-learning-v2", "orchestration-prompt"}
        for name, content in CLAUDE_SKILLS.items():
            if name in no_tool_grant_skills:
                continue
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
            ("tapps-research", "[library] [topic]"),
            ("tapps-memory", "[save|search|get] [key]"),
            ("tapps-security", "[file-path]"),
        ],
    )
    def test_argument_hint_present(self, skill_name: str, expected_hint: str) -> None:
        fm = _get_frontmatter(CLAUDE_SKILLS[skill_name])
        assert f'argument-hint: "{expected_hint}"' in fm

    def test_finish_task_has_argument_hint(self) -> None:
        fm = _get_frontmatter(CLAUDE_SKILLS["tapps-finish-task"])
        assert "argument-hint:" in fm
        assert "feature|bugfix" in fm

    def test_review_pipeline_no_argument_hint(self) -> None:
        fm = _get_frontmatter(CLAUDE_SKILLS["tapps-review-pipeline"])
        assert "argument-hint:" not in fm


# ---------------------------------------------------------------------------
# Claude skill frontmatter: disable-model-invocation
# ---------------------------------------------------------------------------


class TestClaudeDisableModelInvocation:
    """Handoff skills disable model invocation; orchestration skills do not."""

    @pytest.mark.parametrize(
        "skill_name",
        ["tapps-handoff-session", "tapps-engagement"],
    )
    def test_disable_model_invocation_present(self, skill_name: str) -> None:
        fm = _get_frontmatter(CLAUDE_SKILLS[skill_name])
        assert "disable-model-invocation: true" in fm

    @pytest.mark.parametrize(
        "skill_name",
        [
            "tapps-finish-task",
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
        ["tapps-finish-task", "tapps-security", "tapps-memory"],
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
            ("tapps-finish-task", "claude-haiku-4-5-20251001"),
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
            "tapps-finish-task",
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
        # Prose/meta skills carry no tool-grant frontmatter on either host.
        no_tool_grant_skills = {"continuous-learning-v2", "orchestration-prompt"}
        for name, content in CURSOR_SKILLS.items():
            if name in no_tool_grant_skills:
                continue
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

    def test_generated_claude_finish_task_has_allowed_tools(self, tmp_path: Path) -> None:
        generate_skills(tmp_path, "claude")
        content = (tmp_path / ".claude" / "skills" / "tapps-finish-task" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        assert "allowed-tools:" in content
        assert "mcp__nlt-build__tapps_validate_changed" in content
        assert "\ntools:" not in content

    def test_generated_claude_handoff_has_disable_model(self, tmp_path: Path) -> None:
        generate_skills(tmp_path, "claude")
        content = (
            tmp_path / ".claude" / "skills" / "tapps-handoff-session" / "SKILL.md"
        ).read_text(encoding="utf-8")
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
        assert "mcp__nlt-linear-issues__docs_generate_epic" in CLAUDE_SKILLS["linear-issue"]

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


class TestLinearReadSkill:
    """TAP-1260: linear-read skill encodes the cache-first dance for multi-issue reads."""

    def test_claude_skill_registered(self) -> None:
        assert "linear-read" in CLAUDE_SKILLS

    def test_cursor_skill_registered(self) -> None:
        assert "linear-read" in CURSOR_SKILLS

    def test_claude_allowed_tools_include_snapshot_and_list(self) -> None:
        content = CLAUDE_SKILLS["linear-read"]
        assert "mcp__nlt-linear-issues__tapps_linear_snapshot_get" in content
        assert "mcp__nlt-linear-issues__tapps_linear_snapshot_put" in content
        assert "mcp__plugin_linear_linear__list_issues" in content
        assert "mcp__plugin_linear_linear__get_issue" in content

    def test_skill_documents_six_poll_antipattern(self) -> None:
        content = CLAUDE_SKILLS["linear-read"]
        assert "6-poll kickoff" in content
        # Confirm the collapse-to-one-call replacement is shown.
        assert 'snapshot_get(team=<team>, project=<project>, state="open")' in content

    def test_skill_documents_unfiltered_scroll_antipattern(self) -> None:
        content = CLAUDE_SKILLS["linear-read"]
        assert "unfiltered scroll" in content.lower()

    def test_skill_routes_single_issue_to_get_issue(self) -> None:
        content = CLAUDE_SKILLS["linear-read"]
        assert "get_issue" in content
        # Skip-the-skill instruction for id-only lookups must be present.
        assert "Single-issue lookup" in content or "single-issue" in content.lower()

    def test_skill_is_user_invocable(self) -> None:
        content = CLAUDE_SKILLS["linear-read"]
        assert "user-invocable: true" in content

    def test_generated_linear_read_lands_at_expected_path(self, tmp_path: Path) -> None:
        generate_skills(tmp_path, "claude")
        target = tmp_path / ".claude" / "skills" / "linear-read" / "SKILL.md"
        assert target.exists()
        content = target.read_text(encoding="utf-8")
        assert "mcp__nlt-linear-issues__tapps_linear_snapshot_get" in content


class TestFinishTaskSkill:
    """TAP-977: tapps-finish-task bundles validate -> checklist -> memory."""

    def test_claude_skill_registered(self) -> None:
        assert "tapps-finish-task" in CLAUDE_SKILLS

    def test_cursor_skill_registered(self) -> None:
        assert "tapps-finish-task" in CURSOR_SKILLS

    def test_allowed_tools_includes_validate_changed(self) -> None:
        content = CLAUDE_SKILLS["tapps-finish-task"]
        assert "mcp__nlt-build__tapps_validate_changed" in content

    def test_allowed_tools_includes_checklist(self) -> None:
        content = CLAUDE_SKILLS["tapps-finish-task"]
        assert "mcp__nlt-build__tapps_checklist" in content

    def test_allowed_tools_includes_lookup_docs(self) -> None:
        content = CLAUDE_SKILLS["tapps-finish-task"]
        assert "mcp__nlt-build__tapps_lookup_docs" in content

    def test_cursor_mcp_tools_includes_lookup_docs(self) -> None:
        content = CURSOR_SKILLS["tapps-finish-task"]
        assert "tapps_lookup_docs" in content

    def test_finish_task_clears_doc_lookup_gaps(self) -> None:
        for content in (CLAUDE_SKILLS["tapps-finish-task"], CURSOR_SKILLS["tapps-finish-task"]):
            assert "library_uses_without_lookup_docs" in content
            assert "lookup_docs_underused" in content
            assert "libraries_without_lookup" in content
            assert "usage_gaps" in content
            assert "Doc gaps:" in content

    def test_finish_task_uses_cli_memory_save(self) -> None:
        content = CLAUDE_SKILLS["tapps-finish-task"]
        assert "mcp__tapps-mcp__tapps_memory" not in content
        assert "tapps-mcp memory save" in content
        assert "Bash" in _get_frontmatter(content)

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


class TestSessionHandoffSkills:
    """Session transfer skills: handoff-session + continue-session."""

    def test_registered_in_both_platforms(self) -> None:
        for skills in (CLAUDE_SKILLS, CURSOR_SKILLS):
            assert "tapps-handoff-session" in skills
            assert "tapps-continue-session" in skills

    def test_handoff_references_session_handoff_file(self) -> None:
        assert "session-handoff.md" in CLAUDE_SKILLS["tapps-handoff-session"]
        assert "tapps_handoff_save" in CURSOR_SKILLS["tapps-handoff-session"]

    def test_handoff_allowed_tools_include_handoff_save(self) -> None:
        content = CLAUDE_SKILLS["tapps-handoff-session"]
        assert "mcp__nlt-memory__tapps_handoff_save" in content
        assert "mcp__nlt-build__tapps_session_start" in content
        fm = _get_frontmatter(CURSOR_SKILLS["tapps-handoff-session"])
        assert "tapps_handoff_save" in fm
        assert "tapps_session_start" in fm

    def test_handoff_single_atomic_mcp_path(self) -> None:
        for skills in (CLAUDE_SKILLS, CURSOR_SKILLS):
            content = skills["tapps-handoff-session"]
            assert "tapps_handoff_save" in content
            assert "session_end=true" in content
            assert "do **not** also call" in content
            assert "Changed files" in content

    def test_handoff_requires_real_utc_timestamp(self) -> None:
        for skills in (CLAUDE_SKILLS, CURSOR_SKILLS):
            content = skills["tapps-handoff-session"]
            assert "date -u +%Y-%m-%dT%H:%M:%SZ" in content
            assert "T00:00:00Z" in content

    def test_handoff_includes_git_head_and_cli_fallbacks(self) -> None:
        for skills in (CLAUDE_SKILLS, CURSOR_SKILLS):
            content = skills["tapps-handoff-session"]
            assert "git rev-parse --short HEAD" in content
            assert "handoff write" in content
            assert "uv run tapps-mcp memory save" in content
            assert "allow_lint_warnings=true" in content

    def test_continue_session_cli_bootstrap_fallback(self) -> None:
        for skills in (CLAUDE_SKILLS, CURSOR_SKILLS):
            content = skills["tapps-continue-session"]
            assert "doctor --quick" in content
            assert ".tapps-mcp.yaml" in content

    def test_handoff_does_not_grant_removed_tapps_memory_mcp(self) -> None:
        """TAP-1994 removed tapps_memory from MCP catalog; handoff uses CLI mirror."""
        for skills in (CLAUDE_SKILLS, CURSOR_SKILLS):
            content = skills["tapps-handoff-session"]
            assert "mcp__tapps-mcp__tapps_memory" not in content
            assert "tapps-mcp memory save" in content
        fm = _get_frontmatter(CURSOR_SKILLS["tapps-handoff-session"])
        assert "tapps_memory" not in fm

    def test_memory_skill_routes_via_cli_not_mcp(self) -> None:
        for skills in (CLAUDE_SKILLS, CURSOR_SKILLS):
            content = skills["tapps-memory"]
            assert "mcp__tapps-mcp__tapps_memory" not in content
            assert "tapps-mcp memory" in content
            assert "tapps_session_notes" in content
        cursor_fm = _get_frontmatter(CURSOR_SKILLS["tapps-memory"])
        assert "tapps_memory" not in cursor_fm
        claude_fm = _get_frontmatter(CLAUDE_SKILLS["tapps-memory"])
        assert "mcp__tapps-mcp__tapps_memory" not in claude_fm
        assert "Bash" in claude_fm

    def test_cursor_ships_linear_release_update(self) -> None:
        assert "linear-release-update" in CURSOR_SKILLS
        assert "tapps_release_update" in CURSOR_SKILLS["linear-release-update"]

    def test_continue_references_session_start(self) -> None:
        assert "tapps_session_start" in CURSOR_SKILLS["tapps-continue-session"]
        assert "session-handoff.md" in CLAUDE_SKILLS["tapps-continue-session"]

    def test_handoff_requires_p0_gate(self) -> None:
        for skills in (CLAUDE_SKILLS, CURSOR_SKILLS):
            assert "P0 gate" in skills["tapps-handoff-session"]

    def test_continue_has_memory_recall_and_p0_fallback(self) -> None:
        for skills in (CLAUDE_SKILLS, CURSOR_SKILLS):
            content = skills["tapps-continue-session"]
            assert "memory recall" in content
            assert "memory search" in content
            assert "P0 fallback" in content

    def test_handoff_brain_mirror_uses_full_markdown(self) -> None:
        for skills in (CLAUDE_SKILLS, CURSOR_SKILLS):
            content = skills["tapps-handoff-session"]
            assert "tapps_handoff_save" in content
            assert "handoff write" in content
            assert "cat .tapps-mcp/session-handoff.md" in content
            assert "full markdown body" in content

    def test_continue_session_body_parity(self) -> None:
        """Cursor and Claude continue-session share the same core steps (TAP-3581)."""
        markers = (
            "Load handoff (priority order)",
            "P0 fallback",
            "memory recall",
            "Emit continue block",
            "Proceed on P0",
            "linear-read",
        )
        claude_body = CLAUDE_SKILLS["tapps-continue-session"].split("---", 2)[-1]
        cursor_body = CURSOR_SKILLS["tapps-continue-session"].split("---", 2)[-1]
        for marker in markers:
            assert marker in claude_body
            assert marker in cursor_body

    def test_generated_handoff_and_continue_skills(self, tmp_path: Path) -> None:
        generate_skills(tmp_path, "cursor")
        assert (tmp_path / ".cursor" / "skills" / "tapps-handoff-session" / "SKILL.md").exists()
        assert (tmp_path / ".cursor" / "skills" / "tapps-continue-session" / "SKILL.md").exists()

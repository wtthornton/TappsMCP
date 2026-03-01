"""Tests for platform_generators split modules.

Verifies that the facade re-exports work, the split modules contain the
expected data structures, and the generator functions produce correct output.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tapps_mcp.pipeline.platform_generators import (
    _CLAUDE_HOOK_SCRIPTS,
    _CLAUDE_HOOK_SCRIPTS_PS,
    _CLAUDE_HOOKS_CONFIG,
    _CLAUDE_HOOKS_CONFIG_PS,
    _CURSOR_HOOK_SCRIPTS,
    _CURSOR_HOOK_SCRIPTS_PS,
    _CURSOR_HOOKS_CONFIG,
    _CURSOR_HOOKS_CONFIG_PS,
    generate_agent_teams_hooks,
    generate_bugbot_rules,
    generate_ci_workflow,
    generate_claude_hooks,
    generate_claude_plugin_bundle,
    generate_copilot_instructions,
    generate_cursor_hooks,
    generate_cursor_plugin_bundle,
    generate_cursor_rules,
    generate_skills,
    generate_subagent_definitions,
    get_agent_teams_claude_md_section,
    get_ci_claude_md_section,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    AGENT_TEAMS_CLAUDE_MD_SECTION,
    AGENT_TEAMS_HOOKS_CONFIG,
    AGENT_TEAMS_HOOK_SCRIPTS,
    CLAUDE_HOOK_SCRIPTS as HT_CLAUDE_HOOK_SCRIPTS,
    CURSOR_HOOK_SCRIPTS as HT_CURSOR_HOOK_SCRIPTS,
)
from tapps_mcp.pipeline.platform_subagents import (
    CLAUDE_AGENTS,
    CURSOR_AGENTS,
)
from tapps_mcp.pipeline.platform_skills import (
    CLAUDE_SKILLS,
    CURSOR_SKILLS,
)


# ---------------------------------------------------------------------------
# Facade re-export tests
# ---------------------------------------------------------------------------


class TestFacadeReExports:
    """Verify that platform_generators re-exports match split modules."""

    def test_claude_hook_scripts_re_exported(self) -> None:
        assert _CLAUDE_HOOK_SCRIPTS is HT_CLAUDE_HOOK_SCRIPTS

    def test_cursor_hook_scripts_re_exported(self) -> None:
        assert _CURSOR_HOOK_SCRIPTS is HT_CURSOR_HOOK_SCRIPTS

    def test_agent_teams_hooks_re_exported(self) -> None:
        assert AGENT_TEAMS_HOOK_SCRIPTS is AGENT_TEAMS_HOOK_SCRIPTS

    def test_facade_generate_skills_callable(self) -> None:
        assert callable(generate_skills)

    def test_facade_generate_subagents_callable(self) -> None:
        assert callable(generate_subagent_definitions)


# ---------------------------------------------------------------------------
# Hook template structure tests
# ---------------------------------------------------------------------------


class TestHookTemplates:
    """Verify hook template dicts have expected keys and content."""

    def test_claude_sh_scripts_count(self) -> None:
        assert len(_CLAUDE_HOOK_SCRIPTS) == 7

    def test_claude_ps1_scripts_count(self) -> None:
        assert len(_CLAUDE_HOOK_SCRIPTS_PS) == 7

    def test_cursor_sh_scripts_count(self) -> None:
        assert len(_CURSOR_HOOK_SCRIPTS) == 2

    def test_cursor_ps1_scripts_count(self) -> None:
        assert len(_CURSOR_HOOK_SCRIPTS_PS) == 2

    def test_claude_scripts_have_shebang(self) -> None:
        for name, content in _CLAUDE_HOOK_SCRIPTS.items():
            assert content.startswith("#!/usr/bin/env bash"), f"{name} missing shebang"

    def test_claude_ps_scripts_no_shebang(self) -> None:
        for name, content in _CLAUDE_HOOK_SCRIPTS_PS.items():
            assert not content.startswith("#!"), f"{name} should not have shebang"

    def test_claude_hooks_config_has_session_start(self) -> None:
        assert "SessionStart" in _CLAUDE_HOOKS_CONFIG

    def test_claude_hooks_config_ps_has_session_start(self) -> None:
        assert "SessionStart" in _CLAUDE_HOOKS_CONFIG_PS

    def test_cursor_hooks_config_has_before_mcp(self) -> None:
        assert "beforeMCPExecution" in _CURSOR_HOOKS_CONFIG

    def test_cursor_hooks_config_ps_has_before_mcp(self) -> None:
        assert "beforeMCPExecution" in _CURSOR_HOOKS_CONFIG_PS

    def test_agent_teams_scripts_count(self) -> None:
        assert len(AGENT_TEAMS_HOOK_SCRIPTS) == 2

    def test_agent_teams_config_has_teammate_idle(self) -> None:
        assert "TeammateIdle" in AGENT_TEAMS_HOOKS_CONFIG

    def test_agent_teams_claude_md_section_not_empty(self) -> None:
        assert len(AGENT_TEAMS_CLAUDE_MD_SECTION) > 100


# ---------------------------------------------------------------------------
# Subagent template tests
# ---------------------------------------------------------------------------


class TestSubagentTemplates:
    """Verify subagent template dicts."""

    def test_claude_agents_count(self) -> None:
        assert len(CLAUDE_AGENTS) == 4

    def test_cursor_agents_count(self) -> None:
        assert len(CURSOR_AGENTS) == 4

    def test_claude_agents_have_frontmatter(self) -> None:
        for name, content in CLAUDE_AGENTS.items():
            assert content.startswith("---"), f"{name} missing frontmatter"

    def test_cursor_agents_have_frontmatter(self) -> None:
        for name, content in CURSOR_AGENTS.items():
            assert content.startswith("---"), f"{name} missing frontmatter"

    def test_generate_claude_agents(self, tmp_path: Path) -> None:
        result = generate_subagent_definitions(tmp_path, "claude")
        assert len(result["created"]) == 4
        assert (tmp_path / ".claude" / "agents" / "tapps-reviewer.md").exists()

    def test_generate_cursor_agents(self, tmp_path: Path) -> None:
        result = generate_subagent_definitions(tmp_path, "cursor")
        assert len(result["created"]) == 4
        assert (tmp_path / ".cursor" / "agents" / "tapps-reviewer.md").exists()

    def test_generate_unknown_platform(self, tmp_path: Path) -> None:
        result = generate_subagent_definitions(tmp_path, "unknown")
        assert "error" in result


# ---------------------------------------------------------------------------
# Skill template tests
# ---------------------------------------------------------------------------


class TestSkillTemplates:
    """Verify skill template dicts and generation."""

    def test_claude_skills_count(self) -> None:
        assert len(CLAUDE_SKILLS) == 7

    def test_cursor_skills_count(self) -> None:
        assert len(CURSOR_SKILLS) == 7

    def test_generate_claude_skills(self, tmp_path: Path) -> None:
        result = generate_skills(tmp_path, "claude")
        assert len(result["created"]) == 7
        assert (tmp_path / ".claude" / "skills" / "tapps-score" / "SKILL.md").exists()

    def test_generate_skills_high_engagement(self, tmp_path: Path) -> None:
        result = generate_skills(tmp_path, "claude", engagement_level="high")
        skill_file = tmp_path / ".claude" / "skills" / "tapps-score" / "SKILL.md"
        content = skill_file.read_text(encoding="utf-8")
        assert "MANDATORY" in content

    def test_generate_skills_low_engagement(self, tmp_path: Path) -> None:
        result = generate_skills(tmp_path, "claude", engagement_level="low")
        skill_file = tmp_path / ".claude" / "skills" / "tapps-score" / "SKILL.md"
        content = skill_file.read_text(encoding="utf-8")
        assert "Optional" in content

    def test_generate_skills_skips_existing(self, tmp_path: Path) -> None:
        generate_skills(tmp_path, "claude")
        result = generate_skills(tmp_path, "claude")
        assert len(result["skipped"]) == 7
        assert len(result["created"]) == 0


# ---------------------------------------------------------------------------
# Bundle generator tests
# ---------------------------------------------------------------------------


class TestBundleGenerators:
    """Verify plugin bundle generators."""

    def test_claude_bundle_creates_plugin_json(self, tmp_path: Path) -> None:
        generate_claude_plugin_bundle(tmp_path)
        assert (tmp_path / ".claude-plugin" / "plugin.json").exists()

    def test_cursor_bundle_creates_plugin_json(self, tmp_path: Path) -> None:
        generate_cursor_plugin_bundle(tmp_path)
        assert (tmp_path / ".cursor-plugin" / "plugin.json").exists()

    def test_claude_bundle_has_mcp_json(self, tmp_path: Path) -> None:
        generate_claude_plugin_bundle(tmp_path)
        assert (tmp_path / ".mcp.json").exists()

    def test_cursor_bundle_has_logo(self, tmp_path: Path) -> None:
        generate_cursor_plugin_bundle(tmp_path)
        assert (tmp_path / "logo.png").exists()


# ---------------------------------------------------------------------------
# Misc generator tests
# ---------------------------------------------------------------------------


class TestMiscGenerators:
    """Verify cursor rules, copilot, bugbot, CI generators."""

    def test_cursor_rules_creates_three_files(self, tmp_path: Path) -> None:
        result = generate_cursor_rules(tmp_path)
        assert len(result["created"]) == 3

    def test_copilot_instructions_creates_file(self, tmp_path: Path) -> None:
        result = generate_copilot_instructions(tmp_path)
        assert Path(result["file"]).exists()

    def test_bugbot_rules_creates_file(self, tmp_path: Path) -> None:
        result = generate_bugbot_rules(tmp_path)
        assert Path(result["file"]).exists()

    def test_ci_workflow_creates_file(self, tmp_path: Path) -> None:
        result = generate_ci_workflow(tmp_path)
        assert Path(result["file"]).exists()

    def test_ci_workflow_is_valid_yaml(self, tmp_path: Path) -> None:
        import yaml

        generate_ci_workflow(tmp_path)
        target = tmp_path / ".github" / "workflows" / "tapps-quality.yml"
        data = yaml.safe_load(target.read_text())
        assert "jobs" in data

    def test_agent_teams_hooks_creates_scripts(self, tmp_path: Path) -> None:
        result = generate_agent_teams_hooks(tmp_path)
        assert len(result["scripts_created"]) == 2

    def test_agent_teams_claude_md_section(self) -> None:
        section = get_agent_teams_claude_md_section()
        assert "quality watchdog" in section

    def test_ci_claude_md_section(self) -> None:
        section = get_ci_claude_md_section()
        assert "CI Integration" in section

    def test_claude_hooks_creates_scripts(self, tmp_path: Path) -> None:
        result = generate_claude_hooks(tmp_path, force_windows=False)
        assert len(result["scripts_created"]) == 7

    def test_cursor_hooks_creates_scripts(self, tmp_path: Path) -> None:
        result = generate_cursor_hooks(tmp_path, force_windows=False)
        assert len(result["scripts_created"]) == 2

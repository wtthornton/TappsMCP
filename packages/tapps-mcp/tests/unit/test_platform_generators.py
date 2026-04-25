"""Tests for platform_generators split modules.

Verifies that the facade re-exports work, the split modules contain the
expected data structures, and the generator functions produce correct output.
"""

from __future__ import annotations

import json
from pathlib import Path

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
    AGENT_TEAMS_HOOK_SCRIPTS,
    AGENT_TEAMS_HOOKS_CONFIG,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    CLAUDE_HOOK_SCRIPTS as HT_CLAUDE_HOOK_SCRIPTS,
)
from tapps_mcp.pipeline.platform_hook_templates import (
    CURSOR_HOOK_SCRIPTS as HT_CURSOR_HOOK_SCRIPTS,
)
from tapps_mcp.pipeline.platform_skills import (
    CLAUDE_SKILLS,
    CURSOR_SKILLS,
)
from tapps_mcp.pipeline.platform_subagents import (
    CLAUDE_AGENTS,
    CURSOR_AGENTS,
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
        # 8 original + 3 Epic 36 + 1 memory-capture (Epic 34.5) +
        # 1 post-validate + 1 post-report + 1 user-prompt-submit (TAP-975)
        assert len(_CLAUDE_HOOK_SCRIPTS) == 16

    def test_claude_ps1_scripts_count(self) -> None:
        # 8 original + 3 Epic 36 + 1 memory-capture (Epic 34.5) +
        # 1 post-validate + 1 post-report + 1 user-prompt-submit (TAP-975)
        assert len(_CLAUDE_HOOK_SCRIPTS_PS) == 16

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
        assert len(CLAUDE_SKILLS) == 14  # 13 tapps-* (incl. tapps-finish-task) + linear-issue

    def test_cursor_skills_count(self) -> None:
        assert len(CURSOR_SKILLS) == 14  # 13 tapps-* (incl. tapps-finish-task) + linear-issue

    def test_generate_claude_skills(self, tmp_path: Path) -> None:
        result = generate_skills(tmp_path, "claude")
        assert len(result["created"]) == 14
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
        assert len(result["skipped"]) == 14  # 13 tapps-* (incl. tapps-finish-task) + linear-issue
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

    def test_cursor_rules_creates_four_files(self, tmp_path: Path) -> None:
        result = generate_cursor_rules(tmp_path)
        assert len(result["created"]) == 4

    def test_copilot_instructions_creates_file(self, tmp_path: Path) -> None:
        result = generate_copilot_instructions(tmp_path)
        assert Path(result["file"]).exists()

    def test_bugbot_rules_creates_file(self, tmp_path: Path) -> None:
        result = generate_bugbot_rules(tmp_path)
        assert Path(result["file"]).exists()

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
        # Medium engagement (default): SessionStart events (2 scripts),
        # PostToolUse, Stop, TaskCompleted, PreCompact, SubagentStart,
        # SubagentStop, plus TAP-975 UserPromptSubmit script.
        result = generate_claude_hooks(tmp_path, force_windows=False)
        assert len(result["scripts_created"]) == 13
        assert result["engagement_level"] == "medium"

    def test_cursor_hooks_creates_scripts(self, tmp_path: Path) -> None:
        result = generate_cursor_hooks(tmp_path, force_windows=False)
        assert len(result["scripts_created"]) == 2


# ---------------------------------------------------------------------------
# Epic 36 — Hook & Platform Generation Expansion
# ---------------------------------------------------------------------------


class TestEpic36NewHookTemplates:
    """Tests for SubagentStop, SessionEnd, and PostToolUseFailure hooks."""

    def test_subagent_stop_script_exists(self) -> None:
        assert "tapps-subagent-stop.sh" in _CLAUDE_HOOK_SCRIPTS

    def test_session_end_script_exists(self) -> None:
        assert "tapps-session-end.sh" in _CLAUDE_HOOK_SCRIPTS

    def test_tool_failure_script_exists(self) -> None:
        assert "tapps-tool-failure.sh" in _CLAUDE_HOOK_SCRIPTS

    def test_subagent_stop_ps1_exists(self) -> None:
        assert "tapps-subagent-stop.ps1" in _CLAUDE_HOOK_SCRIPTS_PS

    def test_session_end_ps1_exists(self) -> None:
        assert "tapps-session-end.ps1" in _CLAUDE_HOOK_SCRIPTS_PS

    def test_tool_failure_ps1_exists(self) -> None:
        assert "tapps-tool-failure.ps1" in _CLAUDE_HOOK_SCRIPTS_PS

    def test_subagent_stop_hook_is_advisory(self) -> None:
        """SubagentStop does NOT support exit 2 — must exit 0."""
        content = _CLAUDE_HOOK_SCRIPTS["tapps-subagent-stop.sh"]
        assert "exit 0" in content
        assert "exit 2" not in content

    def test_session_end_hook_is_advisory(self) -> None:
        """SessionEnd does NOT support exit 2 — must exit 0."""
        content = _CLAUDE_HOOK_SCRIPTS["tapps-session-end.sh"]
        assert "exit 0" in content
        assert "exit 2" not in content

    def test_tool_failure_hook_is_advisory(self) -> None:
        """PostToolUseFailure does NOT support exit 2 — must exit 0."""
        content = _CLAUDE_HOOK_SCRIPTS["tapps-tool-failure.sh"]
        assert "exit 0" in content
        assert "exit 2" not in content

    def test_tool_failure_filters_tapps_tools(self) -> None:
        """PostToolUseFailure hook only logs TappsMCP tools."""
        content = _CLAUDE_HOOK_SCRIPTS["tapps-tool-failure.sh"]
        assert "mcp__tapps" in content

    def test_tool_failure_mentions_tapps_doctor(self) -> None:
        """TAP-976: stderr hint should point at tapps_doctor."""
        bash = _CLAUDE_HOOK_SCRIPTS["tapps-tool-failure.sh"]
        ps = _CLAUDE_HOOK_SCRIPTS_PS["tapps-tool-failure.ps1"]
        assert "tapps_doctor" in bash
        assert "tapps_doctor" in ps

    def test_tool_failure_writes_jsonl_log(self) -> None:
        """TAP-976: failures append to .tapps-mcp/.failure-log.jsonl."""
        bash = _CLAUDE_HOOK_SCRIPTS["tapps-tool-failure.sh"]
        ps = _CLAUDE_HOOK_SCRIPTS_PS["tapps-tool-failure.ps1"]
        assert ".failure-log.jsonl" in bash
        assert ".failure-log.jsonl" in ps

    def test_session_end_checks_marker(self) -> None:
        """SessionEnd hook checks for validation marker file."""
        content = _CLAUDE_HOOK_SCRIPTS["tapps-session-end.sh"]
        assert ".validation-marker" in content

    def test_hooks_config_has_new_events(self) -> None:
        """Hook config includes the three new events."""
        assert "SubagentStop" in _CLAUDE_HOOKS_CONFIG
        assert "SessionEnd" in _CLAUDE_HOOKS_CONFIG
        assert "PostToolUseFailure" in _CLAUDE_HOOKS_CONFIG

    def test_hooks_config_ps_has_new_events(self) -> None:
        """PS hook config includes the three new events."""
        assert "SubagentStop" in _CLAUDE_HOOKS_CONFIG_PS
        assert "SessionEnd" in _CLAUDE_HOOKS_CONFIG_PS
        assert "PostToolUseFailure" in _CLAUDE_HOOKS_CONFIG_PS

    def test_tool_failure_has_matcher(self) -> None:
        """PostToolUseFailure config includes tool name matcher."""
        entries = _CLAUDE_HOOKS_CONFIG["PostToolUseFailure"]
        assert len(entries) == 1
        assert entries[0].get("matcher") == "mcp__tapps-mcp__.*"


class TestEpic36EngagementLevelBlocking:
    """Tests for engagement-level blocking hooks (Story 36.5)."""

    def test_blocking_scripts_exist(self) -> None:
        from tapps_mcp.pipeline.platform_hook_templates import (
            CLAUDE_HOOK_SCRIPTS_BLOCKING,
        )

        assert "tapps-task-completed.sh" in CLAUDE_HOOK_SCRIPTS_BLOCKING
        assert "tapps-stop.sh" in CLAUDE_HOOK_SCRIPTS_BLOCKING

    def test_blocking_ps_scripts_exist(self) -> None:
        from tapps_mcp.pipeline.platform_hook_templates import (
            CLAUDE_HOOK_SCRIPTS_BLOCKING_PS,
        )

        assert "tapps-task-completed.ps1" in CLAUDE_HOOK_SCRIPTS_BLOCKING_PS
        assert "tapps-stop.ps1" in CLAUDE_HOOK_SCRIPTS_BLOCKING_PS

    def test_blocking_task_completed_uses_exit_2(self) -> None:
        from tapps_mcp.pipeline.platform_hook_templates import (
            CLAUDE_HOOK_SCRIPTS_BLOCKING,
        )

        content = CLAUDE_HOOK_SCRIPTS_BLOCKING["tapps-task-completed.sh"]
        assert "exit 2" in content
        assert "BLOCKED" in content

    def test_blocking_stop_uses_exit_2(self) -> None:
        from tapps_mcp.pipeline.platform_hook_templates import (
            CLAUDE_HOOK_SCRIPTS_BLOCKING,
        )

        content = CLAUDE_HOOK_SCRIPTS_BLOCKING["tapps-stop.sh"]
        assert "exit 2" in content
        assert "stop_hook_active" in content

    def test_blocking_task_completed_checks_marker(self) -> None:
        from tapps_mcp.pipeline.platform_hook_templates import (
            CLAUDE_HOOK_SCRIPTS_BLOCKING,
        )

        content = CLAUDE_HOOK_SCRIPTS_BLOCKING["tapps-task-completed.sh"]
        assert ".validation-marker" in content

    def test_blocking_task_completed_stale_detection(self) -> None:
        """Blocking task-completed checks for stale marker (>1h)."""
        from tapps_mcp.pipeline.platform_hook_templates import (
            CLAUDE_HOOK_SCRIPTS_BLOCKING,
        )

        content = CLAUDE_HOOK_SCRIPTS_BLOCKING["tapps-task-completed.sh"]
        assert "3600" in content


class TestEpic36PromptHook:
    """Tests for prompt-type hook configuration (Story 36.4)."""

    def test_prompt_hook_config_exists(self) -> None:
        from tapps_mcp.pipeline.platform_hook_templates import (
            PROMPT_HOOK_CONFIG,
        )

        assert "PostToolUse" in PROMPT_HOOK_CONFIG

    def test_prompt_hook_uses_haiku(self) -> None:
        from tapps_mcp.pipeline.platform_hook_templates import (
            PROMPT_HOOK_CONFIG,
        )

        entry = PROMPT_HOOK_CONFIG["PostToolUse"][0]
        assert entry["type"] == "prompt"
        assert entry["model"] == "haiku"

    def test_prompt_hook_has_timeout(self) -> None:
        from tapps_mcp.pipeline.platform_hook_templates import (
            PROMPT_HOOK_CONFIG,
        )

        entry = PROMPT_HOOK_CONFIG["PostToolUse"][0]
        assert entry["timeout"] == 15

    def test_prompt_hook_matcher(self) -> None:
        from tapps_mcp.pipeline.platform_hook_templates import (
            PROMPT_HOOK_CONFIG,
        )

        entry = PROMPT_HOOK_CONFIG["PostToolUse"][0]
        assert entry["matcher"] == "Edit|Write"


class TestEpic36EngagementHookEvents:
    """Tests for engagement-level hook event sets (Story 36.6)."""

    def test_high_has_all_events(self) -> None:
        from tapps_mcp.pipeline.platform_hook_templates import (
            ENGAGEMENT_HOOK_EVENTS,
        )

        high = ENGAGEMENT_HOOK_EVENTS["high"]
        assert "SubagentStop" in high
        assert "SessionEnd" in high
        assert "PostToolUseFailure" in high
        assert "Stop" in high
        assert "TaskCompleted" in high
        # TAP-975: UserPromptSubmit pipeline-state reminder added at high+medium.
        assert "UserPromptSubmit" in high
        assert len(high) == 10

    def test_medium_has_standard_events(self) -> None:
        from tapps_mcp.pipeline.platform_hook_templates import (
            ENGAGEMENT_HOOK_EVENTS,
        )

        medium = ENGAGEMENT_HOOK_EVENTS["medium"]
        assert "SessionStart" in medium
        assert "SubagentStop" in medium
        assert "SessionEnd" not in medium
        assert "PostToolUseFailure" not in medium
        assert "UserPromptSubmit" in medium  # TAP-975
        assert len(medium) == 8

    def test_low_is_minimal(self) -> None:
        from tapps_mcp.pipeline.platform_hook_templates import (
            ENGAGEMENT_HOOK_EVENTS,
        )

        low = ENGAGEMENT_HOOK_EVENTS["low"]
        assert low == {"SessionStart"}


class TestEpic36GenerateHooksEngagement:
    """Tests for generate_claude_hooks with engagement levels."""

    def test_high_engagement_creates_blocking_scripts(
        self,
        tmp_path: Path,
    ) -> None:
        result = generate_claude_hooks(
            tmp_path,
            force_windows=False,
            engagement_level="high",
        )
        assert result["engagement_level"] == "high"
        # High engagement includes all 9 events
        hooks_dir = tmp_path / ".claude" / "hooks"
        assert (hooks_dir / "tapps-subagent-stop.sh").exists()
        assert (hooks_dir / "tapps-session-end.sh").exists()
        assert (hooks_dir / "tapps-tool-failure.sh").exists()
        # Blocking scripts should overwrite advisory ones
        stop_content = (hooks_dir / "tapps-stop.sh").read_text()
        assert "BLOCKED" in stop_content
        assert "exit 2" in stop_content
        task_content = (hooks_dir / "tapps-task-completed.sh").read_text()
        assert "BLOCKED" in task_content
        assert "exit 2" in task_content

    def test_medium_engagement_advisory_only(
        self,
        tmp_path: Path,
    ) -> None:
        result = generate_claude_hooks(
            tmp_path,
            force_windows=False,
            engagement_level="medium",
        )
        assert result["engagement_level"] == "medium"
        hooks_dir = tmp_path / ".claude" / "hooks"
        # SubagentStop should exist at medium
        assert (hooks_dir / "tapps-subagent-stop.sh").exists()
        # SessionEnd and PostToolUseFailure should NOT exist at medium
        assert not (hooks_dir / "tapps-session-end.sh").exists()
        assert not (hooks_dir / "tapps-tool-failure.sh").exists()
        # Stop hook should be advisory (exit 0, no BLOCKED)
        stop_content = (hooks_dir / "tapps-stop.sh").read_text()
        assert "BLOCKED" not in stop_content

    def test_low_engagement_minimal_hooks(
        self,
        tmp_path: Path,
    ) -> None:
        result = generate_claude_hooks(
            tmp_path,
            force_windows=False,
            engagement_level="low",
        )
        assert result["engagement_level"] == "low"
        hooks_dir = tmp_path / ".claude" / "hooks"
        # Only SessionStart hooks should be created
        assert (hooks_dir / "tapps-session-start.sh").exists()
        assert (hooks_dir / "tapps-session-compact.sh").exists()
        # No other hooks
        assert not (hooks_dir / "tapps-stop.sh").exists()
        assert not (hooks_dir / "tapps-task-completed.sh").exists()
        assert not (hooks_dir / "tapps-subagent-stop.sh").exists()

    def test_prompt_hooks_opt_in(self, tmp_path: Path) -> None:
        result = generate_claude_hooks(
            tmp_path,
            force_windows=False,
            prompt_hooks=True,
        )
        assert result["prompt_hooks"] is True
        settings_file = tmp_path / ".claude" / "settings.json"
        config = json.loads(settings_file.read_text())
        # Should have a prompt-type entry in PostToolUse
        post_tool_use = config["hooks"]["PostToolUse"]
        has_prompt = any(e.get("type") == "prompt" for e in post_tool_use)
        assert has_prompt

    def test_prompt_hooks_default_off(self, tmp_path: Path) -> None:
        result = generate_claude_hooks(
            tmp_path,
            force_windows=False,
            prompt_hooks=False,
        )
        assert result["prompt_hooks"] is False
        settings_file = tmp_path / ".claude" / "settings.json"
        config = json.loads(settings_file.read_text())
        post_tool_use = config["hooks"]["PostToolUse"]
        has_prompt = any(e.get("type") == "prompt" for e in post_tool_use)
        assert not has_prompt

    def test_settings_json_has_new_events_at_high(
        self,
        tmp_path: Path,
    ) -> None:
        generate_claude_hooks(
            tmp_path,
            force_windows=False,
            engagement_level="high",
        )
        settings_file = tmp_path / ".claude" / "settings.json"
        config = json.loads(settings_file.read_text())
        hooks = config["hooks"]
        assert "SubagentStop" in hooks
        assert "SessionEnd" in hooks
        assert "PostToolUseFailure" in hooks

    def test_settings_json_no_new_events_at_low(
        self,
        tmp_path: Path,
    ) -> None:
        generate_claude_hooks(
            tmp_path,
            force_windows=False,
            engagement_level="low",
        )
        settings_file = tmp_path / ".claude" / "settings.json"
        config = json.loads(settings_file.read_text())
        hooks = config["hooks"]
        assert "SessionStart" in hooks
        assert "SubagentStop" not in hooks
        assert "Stop" not in hooks


class TestEpic36ValidationMarker:
    """Tests for the validation marker file mechanism."""

    def test_validate_ok_writes_both_markers(self, tmp_path: Path) -> None:
        from tapps_mcp.server_pipeline_tools import _write_validate_ok_marker

        _write_validate_ok_marker(tmp_path)
        # Legacy marker
        legacy = tmp_path / ".tapps-mcp" / "sessions" / "last_validate_ok"
        assert legacy.exists()
        # New marker for Claude hooks
        new_marker = tmp_path / ".tapps-mcp" / ".validation-marker"
        assert new_marker.exists()

    def test_validation_marker_contains_timestamp(
        self,
        tmp_path: Path,
    ) -> None:
        from tapps_mcp.server_pipeline_tools import _write_validate_ok_marker

        _write_validate_ok_marker(tmp_path)
        marker = tmp_path / ".tapps-mcp" / ".validation-marker"
        ts = float(marker.read_text())
        import time

        # Timestamp should be recent (within last 5 seconds)
        assert time.time() - ts < 5

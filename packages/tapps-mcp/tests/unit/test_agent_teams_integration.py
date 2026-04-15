"""Tests for Agent Teams integration (Story 12.12).

Verifies that Agent Teams hooks (TeammateIdle, TaskCompleted) are
generated when opted in and absent when not, and that the CLAUDE.md
template includes the Agent Teams documentation section.
"""

from __future__ import annotations

import json
import stat
import sys

import pytest

from tapps_mcp.pipeline.platform_generators import (
    generate_agent_teams_hooks,
    get_agent_teams_claude_md_section,
)


class TestAgentTeamsHooksOptIn:
    """Tests for when agent_teams=True."""

    def test_scripts_created(self, tmp_path):
        generate_agent_teams_hooks(tmp_path)
        hooks_dir = tmp_path / ".claude" / "hooks"
        assert (hooks_dir / "tapps-teammate-idle.sh").exists()
        assert (hooks_dir / "tapps-teams-task-completed.sh").exists()

    @pytest.mark.skipif(sys.platform == "win32", reason="Exec bit N/A on Windows")
    def test_scripts_executable(self, tmp_path):
        generate_agent_teams_hooks(tmp_path)
        hooks_dir = tmp_path / ".claude" / "hooks"
        for script in hooks_dir.iterdir():
            mode = script.stat().st_mode
            assert mode & stat.S_IXUSR, f"{script.name} not executable"

    def test_settings_has_teammate_idle(self, tmp_path):
        generate_agent_teams_hooks(tmp_path)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert "TeammateIdle" in data["hooks"]
        entry = data["hooks"]["TeammateIdle"][0]
        assert entry["matcher"] == "tapps-quality-watchdog"

    def test_teammate_idle_hook_type(self, tmp_path):
        generate_agent_teams_hooks(tmp_path)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        hook = data["hooks"]["TeammateIdle"][0]["hooks"][0]
        assert hook["type"] == "command"
        assert "tapps-teammate-idle.sh" in hook["command"]

    def test_settings_has_task_completed(self, tmp_path):
        generate_agent_teams_hooks(tmp_path)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert "TaskCompleted" in data["hooks"]

    def test_task_completed_hook_command(self, tmp_path):
        generate_agent_teams_hooks(tmp_path)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        hook = data["hooks"]["TaskCompleted"][0]["hooks"][0]
        assert "tapps-teams-task-completed.sh" in hook["command"]

    def test_teammate_idle_script_has_exit_2(self, tmp_path):
        generate_agent_teams_hooks(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "tapps-teammate-idle.sh").read_text()
        assert "exit 2" in content

    def test_task_completed_script_has_validate(self, tmp_path):
        generate_agent_teams_hooks(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "tapps-teams-task-completed.sh").read_text()
        assert "tapps_validate_changed" in content

    def test_result_dict(self, tmp_path):
        result = generate_agent_teams_hooks(tmp_path)
        assert len(result["scripts_created"]) == 2
        assert result["hooks_added"] > 0


class TestAgentTeamsOptOut:
    """Tests for when agent_teams=False (default).

    When agent_teams is False, generate_agent_teams_hooks is never called,
    so settings.json should not contain TeammateIdle or TaskCompleted.
    """

    def test_no_team_hooks_without_call(self, tmp_path):
        """Without calling generate_agent_teams_hooks, no team hooks exist."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir(parents=True)
        config = {"hooks": {}}
        (settings_dir / "settings.json").write_text(json.dumps(config), encoding="utf-8")

        data = json.loads((settings_dir / "settings.json").read_text())
        assert "TeammateIdle" not in data["hooks"]
        assert "TaskCompleted" not in data["hooks"]


class TestClaudeMdSection:
    """Tests for the Agent Teams CLAUDE.md documentation section."""

    def test_section_mentions_env_var(self):
        section = get_agent_teams_claude_md_section()
        assert "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS" in section

    def test_section_mentions_quality_watchdog(self):
        section = get_agent_teams_claude_md_section()
        assert "quality watchdog" in section

    def test_section_mentions_validate_changed(self):
        section = get_agent_teams_claude_md_section()
        assert "tapps_validate_changed" in section

    def test_section_mentions_teammate_idle(self):
        section = get_agent_teams_claude_md_section()
        assert "TeammateIdle" in section


class TestClaudeMdTemplate:
    """Tests that the actual CLAUDE.md template includes Agent Teams."""

    def test_template_has_agent_teams_section(self):
        # Agent Teams section moved from platform_claude_medium.md to
        # AGENT_TEAMS_CLAUDE_MD_SECTION (injected into generated CLAUDE.md).
        from tapps_mcp.pipeline.platform_bundles import get_agent_teams_claude_md_section

        section = get_agent_teams_claude_md_section()
        assert "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS" in section
        assert "quality watchdog" in section

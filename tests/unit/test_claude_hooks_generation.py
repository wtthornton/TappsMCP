"""Tests for Claude Code hooks generation (Story 12.5).

Verifies that generate_claude_hooks() creates 7 shell scripts in .claude/hooks/
and merges hook entries into .claude/settings.json.
"""

from __future__ import annotations

import json
import os
import stat

from tapps_mcp.pipeline.platform_generators import generate_claude_hooks


class TestClaudeHooksScripts:
    """Tests for hook script file creation."""

    def test_hooks_dir_created(self, tmp_path):
        generate_claude_hooks(tmp_path)
        assert (tmp_path / ".claude" / "hooks").is_dir()

    def test_all_seven_scripts_created(self, tmp_path):
        generate_claude_hooks(tmp_path)
        hooks_dir = tmp_path / ".claude" / "hooks"
        expected = [
            "tapps-session-start.sh",
            "tapps-session-compact.sh",
            "tapps-post-edit.sh",
            "tapps-stop.sh",
            "tapps-task-completed.sh",
            "tapps-pre-compact.sh",
            "tapps-subagent-start.sh",
        ]
        for name in expected:
            assert (hooks_dir / name).exists(), f"Missing: {name}"

    def test_scripts_are_executable(self, tmp_path):
        generate_claude_hooks(tmp_path)
        hooks_dir = tmp_path / ".claude" / "hooks"
        for script in hooks_dir.iterdir():
            mode = script.stat().st_mode
            assert mode & stat.S_IXUSR, f"{script.name} not executable"

    def test_stop_script_checks_stop_hook_active(self, tmp_path):
        generate_claude_hooks(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "tapps-stop.sh").read_text()
        assert "stop_hook_active" in content

    def test_stop_script_has_exit_0(self, tmp_path):
        generate_claude_hooks(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "tapps-stop.sh").read_text()
        assert "exit 0" in content

    def test_stop_script_has_exit_2(self, tmp_path):
        generate_claude_hooks(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "tapps-stop.sh").read_text()
        assert "exit 2" in content

    def test_task_completed_has_exit_2(self, tmp_path):
        generate_claude_hooks(tmp_path)
        content = (tmp_path / ".claude" / "hooks" / "tapps-task-completed.sh").read_text()
        assert "exit 2" in content

    def test_scripts_start_with_shebang(self, tmp_path):
        generate_claude_hooks(tmp_path)
        hooks_dir = tmp_path / ".claude" / "hooks"
        for script in hooks_dir.iterdir():
            content = script.read_text()
            assert content.startswith("#!/usr/bin/env bash"), f"{script.name} missing shebang"


class TestClaudeHooksConfig:
    """Tests for settings.json hooks configuration."""

    def test_settings_json_created(self, tmp_path):
        generate_claude_hooks(tmp_path)
        assert (tmp_path / ".claude" / "settings.json").exists()

    def test_settings_has_hooks_key(self, tmp_path):
        generate_claude_hooks(tmp_path)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert "hooks" in data

    def test_stop_event_configured(self, tmp_path):
        generate_claude_hooks(tmp_path)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert "Stop" in data["hooks"]
        assert len(data["hooks"]["Stop"]) > 0

    def test_session_start_has_two_matchers(self, tmp_path):
        generate_claude_hooks(tmp_path)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        entries = data["hooks"]["SessionStart"]
        matchers = {e.get("matcher") for e in entries}
        assert "startup|resume" in matchers
        assert "compact" in matchers

    def test_post_tool_use_matches_edit_write(self, tmp_path):
        generate_claude_hooks(tmp_path)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        entries = data["hooks"]["PostToolUse"]
        matchers = [e.get("matcher") for e in entries]
        assert "Edit|Write" in matchers

    def test_task_completed_configured(self, tmp_path):
        generate_claude_hooks(tmp_path)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert "TaskCompleted" in data["hooks"]
        assert len(data["hooks"]["TaskCompleted"]) > 0

    def test_pre_compact_configured(self, tmp_path):
        generate_claude_hooks(tmp_path)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert "PreCompact" in data["hooks"]
        assert len(data["hooks"]["PreCompact"]) > 0

    def test_subagent_start_configured(self, tmp_path):
        generate_claude_hooks(tmp_path)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert "SubagentStart" in data["hooks"]
        assert len(data["hooks"]["SubagentStart"]) > 0

    def test_all_six_events_present(self, tmp_path):
        generate_claude_hooks(tmp_path)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        expected_events = {
            "SessionStart", "PostToolUse", "Stop",
            "TaskCompleted", "PreCompact", "SubagentStart",
        }
        assert expected_events == set(data["hooks"].keys())


class TestClaudeHooksMerge:
    """Tests for merging hooks into existing settings.json."""

    def test_preserves_existing_hooks(self, tmp_path):
        """Pre-existing hook entries are preserved."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir(parents=True)
        existing = {
            "hooks": {
                "PostToolUse": [
                    {"matcher": "Bash", "hooks": [{"type": "command", "command": "my-script.sh"}]},
                ],
            },
        }
        (settings_dir / "settings.json").write_text(json.dumps(existing), encoding="utf-8")

        generate_claude_hooks(tmp_path)

        data = json.loads((settings_dir / "settings.json").read_text())
        post_tool = data["hooks"]["PostToolUse"]
        matchers = [e.get("matcher") for e in post_tool]
        assert "Bash" in matchers, "Pre-existing Bash matcher should be preserved"
        assert "Edit|Write" in matchers, "TappsMCP matcher should be added"

    def test_preserves_existing_permissions(self, tmp_path):
        """Existing permissions key is not removed."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir(parents=True)
        existing = {"permissions": {"allow": ["mcp__tapps-mcp__*"]}}
        (settings_dir / "settings.json").write_text(json.dumps(existing), encoding="utf-8")

        generate_claude_hooks(tmp_path)

        data = json.loads((settings_dir / "settings.json").read_text())
        assert "mcp__tapps-mcp__*" in data["permissions"]["allow"]
        assert "hooks" in data

    def test_idempotent(self, tmp_path):
        """Running twice doesn't duplicate entries."""
        generate_claude_hooks(tmp_path)
        generate_claude_hooks(tmp_path)

        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        # SessionStart should still have exactly 2 entries
        assert len(data["hooks"]["SessionStart"]) == 2

    def test_result_dict(self, tmp_path):
        """Returns a summary dict with scripts_created and hooks_action."""
        result = generate_claude_hooks(tmp_path)
        assert "scripts_created" in result
        assert len(result["scripts_created"]) == 7
        assert result["hooks_action"] == "created"
        assert result["hooks_added"] > 0

"""Tests for Claude Code hooks generation (Story 12.5).

Verifies that generate_claude_hooks() creates 7 shell scripts in .claude/hooks/
and merges hook entries into .claude/settings.json.

Includes tests for both bash (Unix) and PowerShell (Windows) variants.
"""

from __future__ import annotations

import json
import stat
import sys

import pytest

from tapps_mcp.pipeline.platform_generators import generate_claude_hooks


class TestClaudeHooksScripts:
    """Tests for hook script file creation (bash / Unix)."""

    def test_hooks_dir_created(self, tmp_path):
        generate_claude_hooks(tmp_path, force_windows=False)
        assert (tmp_path / ".claude" / "hooks").is_dir()

    def test_all_scripts_created(self, tmp_path):
        generate_claude_hooks(tmp_path, force_windows=False)
        hooks_dir = tmp_path / ".claude" / "hooks"
        expected = [
            "tapps-session-start.sh",
            "tapps-session-compact.sh",
            "tapps-post-edit.sh",
            "tapps-stop.sh",
            "tapps-task-completed.sh",
            "tapps-pre-compact.sh",
            "tapps-subagent-start.sh",
            "tapps-subagent-stop.sh",
            "tapps-memory-capture.sh",
        ]
        for name in expected:
            assert (hooks_dir / name).exists(), f"Missing: {name}"

    @pytest.mark.skipif(sys.platform == "win32", reason="Exec bit N/A on Windows")
    def test_scripts_are_executable(self, tmp_path):
        generate_claude_hooks(tmp_path, force_windows=False)
        hooks_dir = tmp_path / ".claude" / "hooks"
        for script in hooks_dir.iterdir():
            mode = script.stat().st_mode
            assert mode & stat.S_IXUSR, f"{script.name} not executable"

    def test_stop_script_checks_stop_hook_active(self, tmp_path):
        generate_claude_hooks(tmp_path, force_windows=False)
        content = (tmp_path / ".claude" / "hooks" / "tapps-stop.sh").read_text()
        assert "stop_hook_active" in content

    def test_stop_script_has_exit_0(self, tmp_path):
        generate_claude_hooks(tmp_path, force_windows=False)
        content = (tmp_path / ".claude" / "hooks" / "tapps-stop.sh").read_text()
        assert "exit 0" in content

    def test_stop_script_is_non_blocking(self, tmp_path):
        generate_claude_hooks(tmp_path, force_windows=False)
        content = (tmp_path / ".claude" / "hooks" / "tapps-stop.sh").read_text()
        # Stop hook should NOT block (exit 0, not exit 2)
        assert "exit 2" not in content
        assert content.strip().endswith("exit 0")

    def test_task_completed_is_non_blocking(self, tmp_path):
        generate_claude_hooks(tmp_path, force_windows=False)
        content = (tmp_path / ".claude" / "hooks" / "tapps-task-completed.sh").read_text()
        # Task completed hook should NOT block (exit 0, not exit 2)
        assert "exit 2" not in content
        assert content.strip().endswith("exit 0")

    def test_scripts_start_with_shebang(self, tmp_path):
        generate_claude_hooks(tmp_path, force_windows=False)
        hooks_dir = tmp_path / ".claude" / "hooks"
        for script in hooks_dir.iterdir():
            content = script.read_text()
            assert content.startswith("#!/usr/bin/env bash"), f"{script.name} missing shebang"

    def test_bash_scripts_use_python_fallback(self, tmp_path):
        """Bash hooks should fall back from python3 to python for Windows Git Bash."""
        generate_claude_hooks(tmp_path, force_windows=False)
        hooks_dir = tmp_path / ".claude" / "hooks"
        # Check scripts that invoke Python
        for name in ["tapps-post-edit.sh", "tapps-stop.sh"]:
            content = (hooks_dir / name).read_text()
            assert "command -v python3" in content, f"{name} should probe python3"
            assert "command -v python" in content, f"{name} should fall back to python"

    def test_post_edit_does_not_use_grep(self, tmp_path):
        """Post-edit hook should not depend on external grep."""
        generate_claude_hooks(tmp_path, force_windows=False)
        content = (tmp_path / ".claude" / "hooks" / "tapps-post-edit.sh").read_text()
        assert "grep" not in content

    def test_session_start_script_has_required_directive(self, tmp_path):
        """Session-start hook should use directive language."""
        generate_claude_hooks(tmp_path, force_windows=False)
        content = (tmp_path / ".claude" / "hooks" / "tapps-session-start.sh").read_text()
        assert "REQUIRED" in content
        assert "tapps_session_start" in content

    def test_session_start_ps1_has_required_directive(self, tmp_path):
        """PowerShell session-start hook should use directive language."""
        generate_claude_hooks(tmp_path, force_windows=True)
        content = (tmp_path / ".claude" / "hooks" / "tapps-session-start.ps1").read_text()
        assert "REQUIRED" in content
        assert "tapps_session_start" in content


class TestClaudeHooksConfig:
    """Tests for settings.json hooks configuration (bash / Unix)."""

    def test_settings_json_created(self, tmp_path):
        generate_claude_hooks(tmp_path, force_windows=False)
        assert (tmp_path / ".claude" / "settings.json").exists()

    def test_settings_has_hooks_key(self, tmp_path):
        generate_claude_hooks(tmp_path, force_windows=False)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert "hooks" in data

    def test_stop_event_configured(self, tmp_path):
        generate_claude_hooks(tmp_path, force_windows=False)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert "Stop" in data["hooks"]
        assert len(data["hooks"]["Stop"]) > 0

    def test_session_start_has_two_matchers(self, tmp_path):
        generate_claude_hooks(tmp_path, force_windows=False)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        entries = data["hooks"]["SessionStart"]
        matchers = {e.get("matcher") for e in entries}
        assert "startup|resume" in matchers
        assert "compact" in matchers

    def test_post_tool_use_matches_edit_write(self, tmp_path):
        generate_claude_hooks(tmp_path, force_windows=False)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        entries = data["hooks"]["PostToolUse"]
        matchers = [e.get("matcher") for e in entries]
        assert "Edit|Write" in matchers

    def test_task_completed_configured(self, tmp_path):
        generate_claude_hooks(tmp_path, force_windows=False)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert "TaskCompleted" in data["hooks"]
        assert len(data["hooks"]["TaskCompleted"]) > 0

    def test_pre_compact_configured(self, tmp_path):
        generate_claude_hooks(tmp_path, force_windows=False)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert "PreCompact" in data["hooks"]
        assert len(data["hooks"]["PreCompact"]) > 0

    def test_subagent_start_configured(self, tmp_path):
        generate_claude_hooks(tmp_path, force_windows=False)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert "SubagentStart" in data["hooks"]
        assert len(data["hooks"]["SubagentStart"]) > 0

    def test_all_events_present(self, tmp_path):
        generate_claude_hooks(tmp_path, force_windows=False)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        expected_events = {
            "SessionStart",
            "PostToolUse",
            "Stop",
            "TaskCompleted",
            "PreCompact",
            "SubagentStart",
            "SubagentStop",
        }
        assert expected_events == set(data["hooks"].keys())

    def test_bash_config_points_to_sh_files(self, tmp_path):
        generate_claude_hooks(tmp_path, force_windows=False)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        for event_entries in data["hooks"].values():
            for entry in event_entries:
                for hook in entry.get("hooks", []):
                    cmd = hook.get("command", "")
                    assert cmd.endswith(".sh"), f"Bash config should use .sh: {cmd}"


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

        generate_claude_hooks(tmp_path, force_windows=False)

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

        generate_claude_hooks(tmp_path, force_windows=False)

        data = json.loads((settings_dir / "settings.json").read_text())
        assert "mcp__tapps-mcp__*" in data["permissions"]["allow"]
        assert "hooks" in data

    def test_idempotent(self, tmp_path):
        """Running twice doesn't duplicate entries."""
        generate_claude_hooks(tmp_path, force_windows=False)
        generate_claude_hooks(tmp_path, force_windows=False)

        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        # SessionStart should still have exactly 2 entries
        assert len(data["hooks"]["SessionStart"]) == 2

    def test_result_dict(self, tmp_path):
        """Returns a summary dict with scripts_created and hooks_action."""
        result = generate_claude_hooks(tmp_path, force_windows=False)
        assert "scripts_created" in result
        assert len(result["scripts_created"]) == 10  # medium engagement (includes memory hooks)
        assert result["hooks_action"] == "created"
        assert result["hooks_added"] > 0


# ---------------------------------------------------------------------------
# PowerShell / Windows variant tests
# ---------------------------------------------------------------------------


class TestClaudeHooksScriptsWindows:
    """Tests for PowerShell hook script creation (Windows)."""

    def test_hooks_dir_created(self, tmp_path):
        generate_claude_hooks(tmp_path, force_windows=True)
        assert (tmp_path / ".claude" / "hooks").is_dir()

    def test_all_ps1_scripts_created(self, tmp_path):
        generate_claude_hooks(tmp_path, force_windows=True)
        hooks_dir = tmp_path / ".claude" / "hooks"
        expected = [
            "tapps-session-start.ps1",
            "tapps-session-compact.ps1",
            "tapps-post-edit.ps1",
            "tapps-stop.ps1",
            "tapps-task-completed.ps1",
            "tapps-pre-compact.ps1",
            "tapps-subagent-start.ps1",
            "tapps-subagent-stop.ps1",
            "tapps-memory-capture.ps1",
        ]
        for name in expected:
            assert (hooks_dir / name).exists(), f"Missing: {name}"

    def test_no_sh_scripts_created(self, tmp_path):
        """Windows mode should not create .sh scripts."""
        generate_claude_hooks(tmp_path, force_windows=True)
        hooks_dir = tmp_path / ".claude" / "hooks"
        sh_files = list(hooks_dir.glob("*.sh"))
        assert len(sh_files) == 0, f"Unexpected .sh files: {sh_files}"

    def test_ps1_scripts_have_no_shebang(self, tmp_path):
        """PowerShell scripts should not have a bash shebang."""
        generate_claude_hooks(tmp_path, force_windows=True)
        hooks_dir = tmp_path / ".claude" / "hooks"
        for script in hooks_dir.iterdir():
            content = script.read_text()
            assert not content.startswith("#!"), f"{script.name} has unexpected shebang"

    def test_stop_script_checks_stop_hook_active(self, tmp_path):
        generate_claude_hooks(tmp_path, force_windows=True)
        content = (tmp_path / ".claude" / "hooks" / "tapps-stop.ps1").read_text()
        assert "stop_hook_active" in content

    def test_stop_script_exits_0(self, tmp_path):
        generate_claude_hooks(tmp_path, force_windows=True)
        content = (tmp_path / ".claude" / "hooks" / "tapps-stop.ps1").read_text()
        assert "exit 0" in content

    def test_post_edit_detects_py_files(self, tmp_path):
        generate_claude_hooks(tmp_path, force_windows=True)
        content = (tmp_path / ".claude" / "hooks" / "tapps-post-edit.ps1").read_text()
        assert ".py" in content
        assert "ConvertFrom-Json" in content

    def test_pre_compact_backs_up_context(self, tmp_path):
        generate_claude_hooks(tmp_path, force_windows=True)
        content = (tmp_path / ".claude" / "hooks" / "tapps-pre-compact.ps1").read_text()
        assert "pre-compact-context.json" in content

    def test_result_dict(self, tmp_path):
        result = generate_claude_hooks(tmp_path, force_windows=True)
        assert "scripts_created" in result
        assert len(result["scripts_created"]) == 10  # medium engagement (includes memory hooks)
        assert all(n.endswith(".ps1") for n in result["scripts_created"])
        assert result["hooks_action"] == "created"
        assert result["hooks_added"] > 0


class TestClaudeHooksConfigWindows:
    """Tests for settings.json hooks configuration (Windows / PowerShell)."""

    def test_settings_has_hooks_key(self, tmp_path):
        generate_claude_hooks(tmp_path, force_windows=True)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert "hooks" in data

    def test_all_events_present(self, tmp_path):
        generate_claude_hooks(tmp_path, force_windows=True)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        expected_events = {
            "SessionStart",
            "PostToolUse",
            "Stop",
            "TaskCompleted",
            "PreCompact",
            "SubagentStart",
            "SubagentStop",
        }
        assert expected_events == set(data["hooks"].keys())

    def test_config_commands_use_powershell(self, tmp_path):
        """All hook commands should invoke powershell with .ps1 files."""
        generate_claude_hooks(tmp_path, force_windows=True)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        for event_entries in data["hooks"].values():
            for entry in event_entries:
                for hook in entry.get("hooks", []):
                    cmd = hook.get("command", "")
                    assert "powershell" in cmd, f"Should use powershell: {cmd}"
                    assert ".ps1" in cmd, f"Should reference .ps1: {cmd}"
                    assert "-NoProfile" in cmd
                    assert "-ExecutionPolicy Bypass" in cmd

    def test_session_start_has_two_matchers(self, tmp_path):
        generate_claude_hooks(tmp_path, force_windows=True)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        entries = data["hooks"]["SessionStart"]
        matchers = {e.get("matcher") for e in entries}
        assert "startup|resume" in matchers
        assert "compact" in matchers

    def test_idempotent(self, tmp_path):
        """Running twice doesn't duplicate entries."""
        generate_claude_hooks(tmp_path, force_windows=True)
        generate_claude_hooks(tmp_path, force_windows=True)

        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        assert len(data["hooks"]["SessionStart"]) == 2


# ---------------------------------------------------------------------------
# Cross-platform migration tests
# ---------------------------------------------------------------------------


class TestClaudeHooksPlatformMigration:
    """Tests for migrating hooks between .sh and .ps1 on platform change."""

    def _all_hook_commands(self, settings_data: dict) -> list[str]:
        """Extract all command strings from nested Claude hook entries."""
        commands = []
        for _event, matcher_entries in settings_data.get("hooks", {}).items():
            if not isinstance(matcher_entries, list):
                continue
            for me in matcher_entries:
                if not isinstance(me, dict):
                    continue
                for hook in me.get("hooks", []):
                    if isinstance(hook, dict) and "command" in hook:
                        commands.append(hook["command"])
        return commands

    def test_upgrade_replaces_sh_hooks_on_windows(self, tmp_path):
        """Init as Unix, then upgrade on Windows — settings should use PowerShell."""
        generate_claude_hooks(tmp_path, force_windows=False)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        cmds = self._all_hook_commands(data)
        assert all(c.endswith(".sh") for c in cmds), "Should start with .sh"

        result = generate_claude_hooks(tmp_path, force_windows=True)

        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        cmds = self._all_hook_commands(data)
        assert all("powershell" in c and ".ps1" in c for c in cmds), (
            f"All should use powershell after migration: {cmds}"
        )
        assert result["hooks_migrated"] > 0
        assert result["hooks_action"] == "migrated"

    def test_upgrade_replaces_ps1_hooks_on_unix(self, tmp_path):
        """Init as Windows, then upgrade on Unix — settings should use .sh."""
        generate_claude_hooks(tmp_path, force_windows=True)
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        cmds = self._all_hook_commands(data)
        assert all("powershell" in c for c in cmds)

        result = generate_claude_hooks(tmp_path, force_windows=False)

        data = json.loads((tmp_path / ".claude" / "settings.json").read_text())
        cmds = self._all_hook_commands(data)
        assert all(c.endswith(".sh") for c in cmds), (
            f"All should use .sh after migration: {cmds}"
        )
        assert result["hooks_migrated"] > 0

    def test_wrong_platform_scripts_cleaned_up(self, tmp_path):
        """Old .sh scripts should be removed when upgrading to Windows."""
        generate_claude_hooks(tmp_path, force_windows=False)
        hooks_dir = tmp_path / ".claude" / "hooks"
        assert len(list(hooks_dir.glob("tapps-*.sh"))) > 0

        result = generate_claude_hooks(tmp_path, force_windows=True)

        assert len(list(hooks_dir.glob("tapps-*.sh"))) == 0
        assert len(list(hooks_dir.glob("tapps-*.ps1"))) > 0
        assert len(result["scripts_removed"]) > 0

    def test_migration_preserves_non_tapps_settings(self, tmp_path):
        """Non-hook settings in settings.json should be preserved."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True)
        (claude_dir / "settings.json").write_text(
            json.dumps({"customSetting": True}), encoding="utf-8"
        )

        generate_claude_hooks(tmp_path, force_windows=False)
        generate_claude_hooks(tmp_path, force_windows=True)  # migrate

        data = json.loads((claude_dir / "settings.json").read_text())
        assert data["customSetting"] is True

    def test_migration_is_idempotent(self, tmp_path):
        """Running migration twice should not change anything the second time."""
        generate_claude_hooks(tmp_path, force_windows=False)
        generate_claude_hooks(tmp_path, force_windows=True)  # migrate
        result = generate_claude_hooks(tmp_path, force_windows=True)  # second run

        assert result["hooks_migrated"] == 0
        assert result["hooks_action"] == "skipped"

    def test_unsupported_hook_keys_stripped_on_write(self, tmp_path):
        """Existing settings with unsupported hook key (e.g. PostCompact) are stripped on write."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True)
        config = {
            "permissions": {"allow": ["mcp__tapps-mcp", "mcp__tapps-mcp__*"]},
            "hooks": {
                "SessionStart": [],
                "PostCompact": [{"matcher": "*", "hooks": [{"type": "command", "command": "echo x"}]}],
            },
        }
        (claude_dir / "settings.json").write_text(
            json.dumps(config, indent=2), encoding="utf-8"
        )
        generate_claude_hooks(tmp_path, force_windows=False)
        data = json.loads((claude_dir / "settings.json").read_text())
        assert "PostCompact" not in data.get("hooks", {})
        assert "SessionStart" in data.get("hooks", {})

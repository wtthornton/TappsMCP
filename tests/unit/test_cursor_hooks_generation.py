"""Tests for Cursor hooks generation (Story 12.7).

Verifies that generate_cursor_hooks() creates 3 shell scripts in .cursor/hooks/
and merges hook entries into .cursor/hooks.json using the Cursor-required format:
``{"version": 1, "hooks": {"eventName": [{"command": "..."}], ...}}``.

Includes tests for both bash (Unix) and PowerShell (Windows) variants.
"""

from __future__ import annotations

import json
import stat
import sys

import pytest

from tapps_mcp.pipeline.platform_generators import generate_cursor_hooks


class TestCursorHooksScripts:
    """Tests for hook script file creation (bash / Unix)."""

    def test_hooks_dir_created(self, tmp_path):
        generate_cursor_hooks(tmp_path, force_windows=False)
        assert (tmp_path / ".cursor" / "hooks").is_dir()

    def test_all_three_scripts_created(self, tmp_path):
        generate_cursor_hooks(tmp_path, force_windows=False)
        hooks_dir = tmp_path / ".cursor" / "hooks"
        expected = ["tapps-before-mcp.sh", "tapps-after-edit.sh", "tapps-stop.sh"]
        for name in expected:
            assert (hooks_dir / name).exists(), f"Missing: {name}"

    @pytest.mark.skipif(sys.platform == "win32", reason="Exec bit N/A on Windows")
    def test_scripts_are_executable(self, tmp_path):
        generate_cursor_hooks(tmp_path, force_windows=False)
        hooks_dir = tmp_path / ".cursor" / "hooks"
        for script in hooks_dir.iterdir():
            mode = script.stat().st_mode
            assert mode & stat.S_IXUSR, f"{script.name} not executable"

    def test_stop_script_uses_followup_message(self, tmp_path):
        generate_cursor_hooks(tmp_path, force_windows=False)
        content = (tmp_path / ".cursor" / "hooks" / "tapps-stop.sh").read_text()
        assert "followup_message" in content

    def test_stop_script_no_exit_2(self, tmp_path):
        """Cursor stop hook must not use exit 2 (not supported)."""
        generate_cursor_hooks(tmp_path, force_windows=False)
        content = (tmp_path / ".cursor" / "hooks" / "tapps-stop.sh").read_text()
        assert "exit 2" not in content

    def test_after_edit_no_exit_2(self, tmp_path):
        """afterFileEdit is fire-and-forget; must not use exit 2."""
        generate_cursor_hooks(tmp_path, force_windows=False)
        content = (tmp_path / ".cursor" / "hooks" / "tapps-after-edit.sh").read_text()
        assert "exit 2" not in content

    def test_scripts_start_with_shebang(self, tmp_path):
        generate_cursor_hooks(tmp_path, force_windows=False)
        hooks_dir = tmp_path / ".cursor" / "hooks"
        for script in hooks_dir.iterdir():
            content = script.read_text()
            assert content.startswith("#!/usr/bin/env bash"), f"{script.name} missing shebang"

    def test_bash_scripts_use_python_fallback(self, tmp_path):
        """Bash hooks should fall back from python3 to python for Git Bash on Windows."""
        generate_cursor_hooks(tmp_path, force_windows=False)
        hooks_dir = tmp_path / ".cursor" / "hooks"
        for name in ["tapps-before-mcp.sh", "tapps-after-edit.sh"]:
            content = (hooks_dir / name).read_text()
            assert "command -v python3" in content, f"{name} should probe python3"
            assert "command -v python" in content, f"{name} should fall back to python"

    def test_before_mcp_checks_session_start(self, tmp_path):
        """before-mcp hook should remind about tapps_session_start."""
        generate_cursor_hooks(tmp_path, force_windows=False)
        content = (tmp_path / ".cursor" / "hooks" / "tapps-before-mcp.sh").read_text()
        assert "tapps_session_start" in content
        assert "REMINDER" in content

    def test_before_mcp_ps1_checks_session_start(self, tmp_path):
        """PowerShell before-mcp hook should remind about tapps_session_start."""
        generate_cursor_hooks(tmp_path, force_windows=True)
        content = (tmp_path / ".cursor" / "hooks" / "tapps-before-mcp.ps1").read_text()
        assert "tapps_session_start" in content
        assert "REMINDER" in content


class TestCursorHooksConfig:
    """Tests for hooks.json configuration (bash / Unix)."""

    def test_hooks_json_created(self, tmp_path):
        generate_cursor_hooks(tmp_path, force_windows=False)
        assert (tmp_path / ".cursor" / "hooks.json").exists()

    def test_hooks_json_has_version(self, tmp_path):
        generate_cursor_hooks(tmp_path, force_windows=False)
        data = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())
        assert data["version"] == 1

    def test_hooks_json_has_hooks_object(self, tmp_path):
        generate_cursor_hooks(tmp_path, force_windows=False)
        data = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())
        assert "hooks" in data
        assert isinstance(data["hooks"], dict)

    def test_before_mcp_event_present(self, tmp_path):
        generate_cursor_hooks(tmp_path, force_windows=False)
        data = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())
        assert "beforeMCPExecution" in data["hooks"]

    def test_after_edit_event_present(self, tmp_path):
        generate_cursor_hooks(tmp_path, force_windows=False)
        data = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())
        assert "afterFileEdit" in data["hooks"]

    def test_stop_event_present(self, tmp_path):
        generate_cursor_hooks(tmp_path, force_windows=False)
        data = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())
        assert "stop" in data["hooks"]

    def test_three_events_total(self, tmp_path):
        generate_cursor_hooks(tmp_path, force_windows=False)
        data = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())
        assert len(data["hooks"]) == 3

    def test_each_event_is_array_of_commands(self, tmp_path):
        generate_cursor_hooks(tmp_path, force_windows=False)
        data = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())
        for event, entries in data["hooks"].items():
            assert isinstance(entries, list), f"{event} should be a list"
            for entry in entries:
                assert "command" in entry, f"{event} entry missing 'command'"

    def test_bash_config_points_to_sh_files(self, tmp_path):
        generate_cursor_hooks(tmp_path, force_windows=False)
        data = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())
        for event, entries in data["hooks"].items():
            for entry in entries:
                assert entry["command"].endswith(".sh"), (
                    f"Should use .sh: {entry['command']}"
                )


class TestCursorHooksMerge:
    """Tests for merging hooks into existing hooks.json."""

    def test_preserves_existing_event_new_format(self, tmp_path):
        """Pre-existing event in new object format is preserved, not replaced."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir(parents=True)
        existing = {
            "version": 1,
            "hooks": {
                "afterFileEdit": [{"command": "my-custom-script.sh"}],
            },
        }
        (cursor_dir / "hooks.json").write_text(json.dumps(existing), encoding="utf-8")

        generate_cursor_hooks(tmp_path, force_windows=False)

        data = json.loads((cursor_dir / "hooks.json").read_text())
        # afterFileEdit should keep the custom command
        assert data["hooks"]["afterFileEdit"] == [{"command": "my-custom-script.sh"}]
        # New events should be added
        assert "beforeMCPExecution" in data["hooks"]
        assert "stop" in data["hooks"]

    def test_migrates_old_array_format(self, tmp_path):
        """Old array-format hooks are migrated to object format."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir(parents=True)
        old_format = {
            "hooks": [
                {"event": "afterFileEdit", "command": "my-custom-script.sh"},
            ],
        }
        (cursor_dir / "hooks.json").write_text(
            json.dumps(old_format), encoding="utf-8"
        )

        generate_cursor_hooks(tmp_path, force_windows=False)

        data = json.loads((cursor_dir / "hooks.json").read_text())
        assert data["version"] == 1
        assert isinstance(data["hooks"], dict)
        # Migrated entry preserved
        assert data["hooks"]["afterFileEdit"] == [{"command": "my-custom-script.sh"}]
        # New events added
        assert "beforeMCPExecution" in data["hooks"]
        assert "stop" in data["hooks"]

    def test_idempotent(self, tmp_path):
        """Running twice doesn't duplicate entries."""
        generate_cursor_hooks(tmp_path, force_windows=False)
        generate_cursor_hooks(tmp_path, force_windows=False)

        data = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())
        assert len(data["hooks"]) == 3

    def test_result_dict(self, tmp_path):
        """Returns a summary dict."""
        result = generate_cursor_hooks(tmp_path, force_windows=False)
        assert "scripts_created" in result
        assert len(result["scripts_created"]) == 3
        assert result["hooks_action"] == "created"


# ---------------------------------------------------------------------------
# PowerShell / Windows variant tests
# ---------------------------------------------------------------------------


class TestCursorHooksScriptsWindows:
    """Tests for PowerShell hook script creation (Windows)."""

    def test_hooks_dir_created(self, tmp_path):
        generate_cursor_hooks(tmp_path, force_windows=True)
        assert (tmp_path / ".cursor" / "hooks").is_dir()

    def test_all_three_ps1_scripts_created(self, tmp_path):
        generate_cursor_hooks(tmp_path, force_windows=True)
        hooks_dir = tmp_path / ".cursor" / "hooks"
        expected = ["tapps-before-mcp.ps1", "tapps-after-edit.ps1", "tapps-stop.ps1"]
        for name in expected:
            assert (hooks_dir / name).exists(), f"Missing: {name}"

    def test_no_sh_scripts_created(self, tmp_path):
        """Windows mode should not create .sh scripts."""
        generate_cursor_hooks(tmp_path, force_windows=True)
        hooks_dir = tmp_path / ".cursor" / "hooks"
        sh_files = list(hooks_dir.glob("*.sh"))
        assert len(sh_files) == 0, f"Unexpected .sh files: {sh_files}"

    def test_ps1_scripts_have_no_shebang(self, tmp_path):
        generate_cursor_hooks(tmp_path, force_windows=True)
        hooks_dir = tmp_path / ".cursor" / "hooks"
        for script in hooks_dir.iterdir():
            content = script.read_text()
            assert not content.startswith("#!"), f"{script.name} has unexpected shebang"

    def test_stop_script_uses_followup_message(self, tmp_path):
        generate_cursor_hooks(tmp_path, force_windows=True)
        content = (tmp_path / ".cursor" / "hooks" / "tapps-stop.ps1").read_text()
        assert "followup_message" in content

    def test_after_edit_uses_convert_from_json(self, tmp_path):
        generate_cursor_hooks(tmp_path, force_windows=True)
        content = (tmp_path / ".cursor" / "hooks" / "tapps-after-edit.ps1").read_text()
        assert "ConvertFrom-Json" in content

    def test_after_edit_supports_both_payloads(self, tmp_path):
        """PS1 after-edit hook should handle both Cursor (file) and Claude (tool_input) payloads."""
        generate_cursor_hooks(tmp_path, force_windows=True)
        content = (tmp_path / ".cursor" / "hooks" / "tapps-after-edit.ps1").read_text()
        assert "data.file" in content
        assert "tool_input.file_path" in content

    def test_result_dict(self, tmp_path):
        result = generate_cursor_hooks(tmp_path, force_windows=True)
        assert "scripts_created" in result
        assert len(result["scripts_created"]) == 3
        assert all(n.endswith(".ps1") for n in result["scripts_created"])
        assert result["hooks_action"] == "created"
        assert result["hooks_added"] > 0


class TestCursorHooksConfigWindows:
    """Tests for hooks.json configuration (Windows / PowerShell)."""

    def test_hooks_json_has_version(self, tmp_path):
        generate_cursor_hooks(tmp_path, force_windows=True)
        data = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())
        assert data["version"] == 1

    def test_hooks_json_has_hooks_object(self, tmp_path):
        generate_cursor_hooks(tmp_path, force_windows=True)
        data = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())
        assert "hooks" in data
        assert isinstance(data["hooks"], dict)

    def test_three_events_total(self, tmp_path):
        generate_cursor_hooks(tmp_path, force_windows=True)
        data = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())
        assert len(data["hooks"]) == 3

    def test_config_commands_use_powershell(self, tmp_path):
        """All hook commands should invoke powershell with .ps1 files."""
        generate_cursor_hooks(tmp_path, force_windows=True)
        data = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())
        for event, entries in data["hooks"].items():
            for entry in entries:
                cmd = entry["command"]
                assert "powershell" in cmd, f"Should use powershell: {cmd}"
                assert ".ps1" in cmd, f"Should reference .ps1: {cmd}"
                assert "-NoProfile" in cmd
                assert "-ExecutionPolicy Bypass" in cmd

    def test_idempotent(self, tmp_path):
        """Running twice doesn't duplicate entries."""
        generate_cursor_hooks(tmp_path, force_windows=True)
        generate_cursor_hooks(tmp_path, force_windows=True)

        data = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())
        assert len(data["hooks"]) == 3

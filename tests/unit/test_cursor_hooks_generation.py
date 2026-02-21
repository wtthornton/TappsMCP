"""Tests for Cursor hooks generation (Story 12.7).

Verifies that generate_cursor_hooks() creates 3 shell scripts in .cursor/hooks/
and merges hook entries into .cursor/hooks.json.
"""

from __future__ import annotations

import json
import stat

from tapps_mcp.pipeline.platform_generators import generate_cursor_hooks


class TestCursorHooksScripts:
    """Tests for hook script file creation."""

    def test_hooks_dir_created(self, tmp_path):
        generate_cursor_hooks(tmp_path)
        assert (tmp_path / ".cursor" / "hooks").is_dir()

    def test_all_three_scripts_created(self, tmp_path):
        generate_cursor_hooks(tmp_path)
        hooks_dir = tmp_path / ".cursor" / "hooks"
        expected = ["tapps-before-mcp.sh", "tapps-after-edit.sh", "tapps-stop.sh"]
        for name in expected:
            assert (hooks_dir / name).exists(), f"Missing: {name}"

    def test_scripts_are_executable(self, tmp_path):
        generate_cursor_hooks(tmp_path)
        hooks_dir = tmp_path / ".cursor" / "hooks"
        for script in hooks_dir.iterdir():
            mode = script.stat().st_mode
            assert mode & stat.S_IXUSR, f"{script.name} not executable"

    def test_stop_script_uses_followup_message(self, tmp_path):
        generate_cursor_hooks(tmp_path)
        content = (tmp_path / ".cursor" / "hooks" / "tapps-stop.sh").read_text()
        assert "followup_message" in content

    def test_stop_script_no_exit_2(self, tmp_path):
        """Cursor stop hook must not use exit 2 (not supported)."""
        generate_cursor_hooks(tmp_path)
        content = (tmp_path / ".cursor" / "hooks" / "tapps-stop.sh").read_text()
        assert "exit 2" not in content

    def test_after_edit_no_exit_2(self, tmp_path):
        """afterFileEdit is fire-and-forget; must not use exit 2."""
        generate_cursor_hooks(tmp_path)
        content = (tmp_path / ".cursor" / "hooks" / "tapps-after-edit.sh").read_text()
        assert "exit 2" not in content

    def test_scripts_start_with_shebang(self, tmp_path):
        generate_cursor_hooks(tmp_path)
        hooks_dir = tmp_path / ".cursor" / "hooks"
        for script in hooks_dir.iterdir():
            content = script.read_text()
            assert content.startswith("#!/usr/bin/env bash"), f"{script.name} missing shebang"


class TestCursorHooksConfig:
    """Tests for hooks.json configuration."""

    def test_hooks_json_created(self, tmp_path):
        generate_cursor_hooks(tmp_path)
        assert (tmp_path / ".cursor" / "hooks.json").exists()

    def test_hooks_json_has_hooks_key(self, tmp_path):
        generate_cursor_hooks(tmp_path)
        data = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())
        assert "hooks" in data
        assert isinstance(data["hooks"], list)

    def test_before_mcp_event_present(self, tmp_path):
        generate_cursor_hooks(tmp_path)
        data = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())
        events = [e["event"] for e in data["hooks"]]
        assert "beforeMCPExecution" in events

    def test_after_edit_event_present(self, tmp_path):
        generate_cursor_hooks(tmp_path)
        data = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())
        events = [e["event"] for e in data["hooks"]]
        assert "afterFileEdit" in events

    def test_stop_event_present(self, tmp_path):
        generate_cursor_hooks(tmp_path)
        data = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())
        events = [e["event"] for e in data["hooks"]]
        assert "stop" in events

    def test_three_events_total(self, tmp_path):
        generate_cursor_hooks(tmp_path)
        data = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())
        assert len(data["hooks"]) == 3


class TestCursorHooksMerge:
    """Tests for merging hooks into existing hooks.json."""

    def test_preserves_existing_event(self, tmp_path):
        """Pre-existing event entry is preserved, not replaced."""
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir(parents=True)
        existing = {
            "hooks": [
                {"event": "afterFileEdit", "command": "my-custom-script.sh"},
            ],
        }
        (cursor_dir / "hooks.json").write_text(json.dumps(existing), encoding="utf-8")

        generate_cursor_hooks(tmp_path)

        data = json.loads((cursor_dir / "hooks.json").read_text())
        events = [e["event"] for e in data["hooks"]]
        # afterFileEdit should appear once (the pre-existing one, not replaced)
        assert events.count("afterFileEdit") == 1
        # The custom command should be preserved
        edit_entry = [e for e in data["hooks"] if e["event"] == "afterFileEdit"][0]
        assert edit_entry["command"] == "my-custom-script.sh"
        # New events should be added
        assert "beforeMCPExecution" in events
        assert "stop" in events

    def test_idempotent(self, tmp_path):
        """Running twice doesn't duplicate entries."""
        generate_cursor_hooks(tmp_path)
        generate_cursor_hooks(tmp_path)

        data = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())
        assert len(data["hooks"]) == 3

    def test_result_dict(self, tmp_path):
        """Returns a summary dict."""
        result = generate_cursor_hooks(tmp_path)
        assert "scripts_created" in result
        assert len(result["scripts_created"]) == 3
        assert result["hooks_action"] == "created"

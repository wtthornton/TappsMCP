"""Tests for _bootstrap_claude_settings in pipeline/init.py (Story 12.3).

Verifies that tapps_init creates/updates .claude/settings.json with the
permission wildcard entry for auto-approving TappsMCP tools.
"""

from __future__ import annotations

import json

from tapps_mcp.pipeline.init import _bootstrap_claude_settings


class TestBootstrapClaudeSettings:
    """Tests for .claude/settings.json permission pre-configuration."""

    def test_creates_new_settings_file(self, tmp_path):
        """Creates .claude/settings.json when it does not exist."""
        action = _bootstrap_claude_settings(tmp_path)
        assert action == "created"
        settings_file = tmp_path / ".claude" / "settings.json"
        assert settings_file.exists()
        data = json.loads(settings_file.read_text(encoding="utf-8"))
        assert "mcp__tapps-mcp__*" in data["permissions"]["allow"]

    def test_skips_when_wildcard_already_present(self, tmp_path):
        """Skips when the wildcard entry already exists."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        config = {"permissions": {"allow": ["mcp__tapps-mcp__*"]}}
        (settings_dir / "settings.json").write_text(
            json.dumps(config, indent=2) + "\n", encoding="utf-8"
        )

        action = _bootstrap_claude_settings(tmp_path)
        assert action == "skipped"

        # File should be unchanged
        data = json.loads((settings_dir / "settings.json").read_text(encoding="utf-8"))
        assert data["permissions"]["allow"] == ["mcp__tapps-mcp__*"]

    def test_appends_to_existing_allow_list(self, tmp_path):
        """Appends wildcard to existing allow list without removing existing entries."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        config = {"permissions": {"allow": ["Bash(*)"]}}
        (settings_dir / "settings.json").write_text(
            json.dumps(config, indent=2) + "\n", encoding="utf-8"
        )

        action = _bootstrap_claude_settings(tmp_path)
        assert action == "updated"

        data = json.loads((settings_dir / "settings.json").read_text(encoding="utf-8"))
        assert "Bash(*)" in data["permissions"]["allow"]
        assert "mcp__tapps-mcp__*" in data["permissions"]["allow"]

    def test_adds_permissions_key_when_missing(self, tmp_path):
        """Creates permissions.allow when settings.json has no permissions key."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        config = {"theme": "dark"}
        (settings_dir / "settings.json").write_text(
            json.dumps(config, indent=2) + "\n", encoding="utf-8"
        )

        action = _bootstrap_claude_settings(tmp_path)
        assert action == "updated"

        data = json.loads((settings_dir / "settings.json").read_text(encoding="utf-8"))
        assert data["theme"] == "dark"
        assert "mcp__tapps-mcp__*" in data["permissions"]["allow"]

    def test_creates_claude_directory(self, tmp_path):
        """Creates .claude/ directory when it does not exist."""
        assert not (tmp_path / ".claude").exists()
        action = _bootstrap_claude_settings(tmp_path)
        assert action == "created"
        assert (tmp_path / ".claude").is_dir()
        assert (tmp_path / ".claude" / "settings.json").exists()

    def test_file_ends_with_newline(self, tmp_path):
        """Generated settings file ends with a single newline."""
        _bootstrap_claude_settings(tmp_path)
        raw = (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
        assert raw.endswith("\n")
        assert not raw.endswith("\n\n")

    def test_idempotent_multiple_calls(self, tmp_path):
        """Multiple calls do not duplicate the wildcard entry."""
        _bootstrap_claude_settings(tmp_path)
        _bootstrap_claude_settings(tmp_path)
        _bootstrap_claude_settings(tmp_path)

        data = json.loads(
            (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
        )
        count = data["permissions"]["allow"].count("mcp__tapps-mcp__*")
        assert count == 1

    def test_preserves_existing_keys(self, tmp_path):
        """Preserves all existing top-level keys in settings.json."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        config = {
            "theme": "dark",
            "editor": {"fontSize": 14},
            "permissions": {
                "allow": ["Bash(*)"],
                "deny": ["rm -rf"],
            },
        }
        (settings_dir / "settings.json").write_text(
            json.dumps(config, indent=2) + "\n", encoding="utf-8"
        )

        action = _bootstrap_claude_settings(tmp_path)
        assert action == "updated"

        data = json.loads((settings_dir / "settings.json").read_text(encoding="utf-8"))
        assert data["theme"] == "dark"
        assert data["editor"]["fontSize"] == 14
        assert data["permissions"]["deny"] == ["rm -rf"]
        assert "Bash(*)" in data["permissions"]["allow"]
        assert "mcp__tapps-mcp__*" in data["permissions"]["allow"]

    def test_handles_empty_file(self, tmp_path):
        """Handles an empty settings.json file gracefully."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        (settings_dir / "settings.json").write_text("", encoding="utf-8")

        action = _bootstrap_claude_settings(tmp_path)
        assert action == "updated"

        data = json.loads((settings_dir / "settings.json").read_text(encoding="utf-8"))
        assert "mcp__tapps-mcp__*" in data["permissions"]["allow"]

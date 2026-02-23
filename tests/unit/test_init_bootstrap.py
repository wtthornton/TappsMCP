"""Tests for _bootstrap_claude_settings in pipeline/init.py (Story 12.3).

Verifies that tapps_init creates/updates .claude/settings.json with the
permission wildcard entry for auto-approving TappsMCP tools.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from tapps_mcp.pipeline.init import BootstrapConfig, _bootstrap_claude_settings, bootstrap_pipeline


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

        data = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
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


class TestAutoDetectClaudeSettings:
    """Tests for auto-detection of Claude Code in bootstrap_pipeline.

    When platform is not "claude" but .claude/ directory exists,
    bootstrap_pipeline should still ensure the permission wildcard.
    """

    def _run_bootstrap(self, tmp_path, platform="", dry_run=False):
        """Run bootstrap with mocked server verification and profile detection."""
        cfg = BootstrapConfig(
            platform=platform,
            create_handoff=False,
            create_runlog=False,
            create_agents_md=False,
            create_tech_stack_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
            warm_expert_rag_from_tech_stack=False,
            dry_run=dry_run,
        )
        with patch(
            "tapps_mcp.pipeline.init._run_server_verification",
            return_value={"ok": True},
        ), patch(
            "tapps_mcp.pipeline.init._detect_profile",
        ):
            return bootstrap_pipeline(tmp_path, config=cfg)

    def test_auto_adds_wildcard_when_claude_dir_exists_no_platform(self, tmp_path):
        """When .claude/ exists but platform is empty, permissions are still set."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        result = self._run_bootstrap(tmp_path, platform="")

        settings_file = claude_dir / "settings.json"
        assert settings_file.exists()
        data = json.loads(settings_file.read_text(encoding="utf-8"))
        assert "mcp__tapps-mcp__*" in data["permissions"]["allow"]
        assert result["claude_settings"]["action"] in ("created", "updated")

    def test_auto_adds_wildcard_when_claude_dir_exists_cursor_platform(self, tmp_path):
        """When .claude/ exists and platform is 'cursor', permissions are still set."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        with patch("tapps_mcp.pipeline.init._setup_platform"):
            result = self._run_bootstrap(tmp_path, platform="cursor")

        settings_file = claude_dir / "settings.json"
        assert settings_file.exists()
        data = json.loads(settings_file.read_text(encoding="utf-8"))
        assert "mcp__tapps-mcp__*" in data["permissions"]["allow"]
        assert result["claude_settings"]["action"] in ("created", "updated")

    def test_no_claude_dir_no_auto_settings(self, tmp_path):
        """When .claude/ doesn't exist and platform is empty, no settings created."""
        assert not (tmp_path / ".claude").exists()

        result = self._run_bootstrap(tmp_path, platform="")

        assert not (tmp_path / ".claude" / "settings.json").exists()
        assert "claude_settings" not in result

    def test_dry_run_skips_auto_settings(self, tmp_path):
        """In dry_run mode, auto-detection is skipped."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        result = self._run_bootstrap(tmp_path, platform="", dry_run=True)

        assert not (claude_dir / "settings.json").exists()
        assert "claude_settings" not in result

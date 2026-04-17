"""Tests for permission settings generation (Epic 33.4).

Verifies that generate_permission_settings and _bootstrap_claude_settings
correctly generate, merge, and deduplicate permission rules in
.claude/settings.json, including engagement-level-based extras.
"""

from __future__ import annotations

import json

from tapps_mcp.pipeline.init import (
    _CLAUDE_DENY_RULES,
    _CLAUDE_HIGH_ENGAGEMENT_PERMISSIONS,
    _CLAUDE_PERMISSION_ENTRIES,
    _CLAUDE_SETTINGS_SCHEMA,
    _bootstrap_claude_settings,
    generate_permission_settings,
)


class TestGeneratePermissionSettings:
    """Tests for the generate_permission_settings function."""

    def test_default_permissions(self, tmp_path):
        """Default (medium) engagement generates base MCP permissions only."""
        result = generate_permission_settings(tmp_path)
        allow = result["permissions"]["allow"]
        for entry in _CLAUDE_PERMISSION_ENTRIES:
            assert entry in allow
        for entry in _CLAUDE_HIGH_ENGAGEMENT_PERMISSIONS:
            assert entry not in allow

    def test_high_engagement_adds_extra_permissions(self, tmp_path):
        """High engagement adds Bash(uv run ruff/mypy) permissions."""
        result = generate_permission_settings(tmp_path, engagement_level="high")
        allow = result["permissions"]["allow"]
        for entry in _CLAUDE_PERMISSION_ENTRIES:
            assert entry in allow
        for entry in _CLAUDE_HIGH_ENGAGEMENT_PERMISSIONS:
            assert entry in allow

    def test_merge_preserves_existing_user_rules(self, tmp_path):
        """Merging with existing settings preserves user's custom entries."""
        existing = {
            "theme": "dark",
            "permissions": {
                "allow": ["Bash(*)"],
                "deny": ["rm -rf /"],
            },
        }
        result = generate_permission_settings(tmp_path, existing_settings=existing)
        assert result["theme"] == "dark"
        assert "Bash(*)" in result["permissions"]["allow"]
        assert "rm -rf /" in result["permissions"]["deny"]
        # Our standard deny rules should also be present
        assert "Bash(rm -rf *)" in result["permissions"]["deny"]
        for entry in _CLAUDE_PERMISSION_ENTRIES:
            assert entry in result["permissions"]["allow"]

    def test_deduplication_of_existing_permissions(self, tmp_path):
        """Does not duplicate entries already present in allow list."""
        existing = {
            "permissions": {
                "allow": ["mcp__tapps-mcp", "mcp__tapps-mcp__*"],
            },
        }
        result = generate_permission_settings(tmp_path, existing_settings=existing)
        allow = result["permissions"]["allow"]
        assert allow.count("mcp__tapps-mcp") == 1
        assert allow.count("mcp__tapps-mcp__*") == 1

    def test_no_existing_settings_creates_fresh(self, tmp_path):
        """When existing_settings is None, creates a fresh config."""
        result = generate_permission_settings(tmp_path)
        assert "permissions" in result
        assert "allow" in result["permissions"]
        assert len(result["permissions"]["allow"]) == len(_CLAUDE_PERMISSION_ENTRIES)

    def test_low_engagement_same_as_medium(self, tmp_path):
        """Low engagement produces the same base permissions as medium."""
        low = generate_permission_settings(tmp_path, engagement_level="low")
        medium = generate_permission_settings(tmp_path, engagement_level="medium")
        assert low == medium


class TestBootstrapClaudeSettingsEngagement:
    """Tests for engagement-level support in _bootstrap_claude_settings."""

    def test_creates_with_high_engagement(self, tmp_path):
        """Creating new settings at high engagement includes extra perms."""
        action = _bootstrap_claude_settings(tmp_path, engagement_level="high")
        assert action == "created"
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        allow = data["permissions"]["allow"]
        assert "Bash(uv run ruff *)" in allow
        assert "Bash(uv run mypy *)" in allow

    def test_creates_with_medium_engagement(self, tmp_path):
        """Creating new settings at medium engagement has no extra perms."""
        action = _bootstrap_claude_settings(tmp_path, engagement_level="medium")
        assert action == "created"
        data = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        allow = data["permissions"]["allow"]
        assert "Bash(uv run ruff *)" not in allow
        assert "Bash(uv run mypy *)" not in allow

    def test_updates_existing_with_high_engagement(self, tmp_path):
        """Updating existing settings at high engagement adds extra perms."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        config = {"permissions": {"allow": ["mcp__tapps-mcp", "mcp__tapps-mcp__*"]}}
        (settings_dir / "settings.json").write_text(
            json.dumps(config, indent=2) + "\n", encoding="utf-8"
        )

        action = _bootstrap_claude_settings(tmp_path, engagement_level="high")
        assert action == "updated"

        data = json.loads((settings_dir / "settings.json").read_text(encoding="utf-8"))
        allow = data["permissions"]["allow"]
        assert "Bash(uv run ruff *)" in allow
        assert "Bash(uv run mypy *)" in allow

    def test_skips_when_all_entries_present(self, tmp_path):
        """Skips when all desired entries (including high) are present."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        all_entries = list(_CLAUDE_PERMISSION_ENTRIES) + list(_CLAUDE_HIGH_ENGAGEMENT_PERMISSIONS)
        config = {
            "$schema": _CLAUDE_SETTINGS_SCHEMA,
            "enableAllProjectMcpServers": True,
            "env": {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"},
            "permissions": {
                "allow": all_entries,
                "deny": list(_CLAUDE_DENY_RULES),
            },
        }
        (settings_dir / "settings.json").write_text(
            json.dumps(config, indent=2) + "\n", encoding="utf-8"
        )

        action = _bootstrap_claude_settings(tmp_path, engagement_level="high")
        assert action == "skipped"

    def test_malformed_json_skips(self, tmp_path):
        """Malformed JSON in existing settings.json is left untouched."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        (settings_dir / "settings.json").write_text("{bad json", encoding="utf-8")

        action = _bootstrap_claude_settings(tmp_path, engagement_level="high")
        assert action == "skipped"
        # File should be unchanged
        raw = (settings_dir / "settings.json").read_text(encoding="utf-8")
        assert raw == "{bad json"

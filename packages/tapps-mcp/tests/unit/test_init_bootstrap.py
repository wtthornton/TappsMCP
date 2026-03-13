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
        """Creates .claude/settings.json with both permission entries."""
        action = _bootstrap_claude_settings(tmp_path)
        assert action == "created"
        settings_file = tmp_path / ".claude" / "settings.json"
        assert settings_file.exists()
        data = json.loads(settings_file.read_text(encoding="utf-8"))
        assert "mcp__tapps-mcp" in data["permissions"]["allow"]
        assert "mcp__tapps-mcp__*" in data["permissions"]["allow"]

    def test_skips_when_both_entries_present(self, tmp_path):
        """Skips when both permission entries already exist."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        # Must include all fields that generate_permission_settings adds
        # (schema, enableAllProjectMcpServers, deny rules) for it to be a no-op.
        from tapps_mcp.pipeline.init import generate_permission_settings

        config = generate_permission_settings(tmp_path)
        (settings_dir / "settings.json").write_text(
            json.dumps(config, indent=2) + "\n", encoding="utf-8"
        )

        action = _bootstrap_claude_settings(tmp_path)
        assert action == "skipped"

        # File should be unchanged
        data = json.loads((settings_dir / "settings.json").read_text(encoding="utf-8"))
        assert data["permissions"]["allow"] == ["mcp__tapps-mcp", "mcp__tapps-mcp__*"]

    def test_appends_to_existing_allow_list(self, tmp_path):
        """Appends both entries to existing allow list without removing existing ones."""
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
        assert "mcp__tapps-mcp" in data["permissions"]["allow"]
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
        assert "mcp__tapps-mcp" in data["permissions"]["allow"]
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
        """Multiple calls do not duplicate permission entries."""
        _bootstrap_claude_settings(tmp_path)
        _bootstrap_claude_settings(tmp_path)
        _bootstrap_claude_settings(tmp_path)

        data = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
        assert data["permissions"]["allow"].count("mcp__tapps-mcp") == 1
        assert data["permissions"]["allow"].count("mcp__tapps-mcp__*") == 1

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
        assert "rm -rf" in data["permissions"]["deny"]
        assert "Bash(*)" in data["permissions"]["allow"]
        assert "mcp__tapps-mcp" in data["permissions"]["allow"]
        assert "mcp__tapps-mcp__*" in data["permissions"]["allow"]

    def test_handles_empty_file(self, tmp_path):
        """Handles an empty settings.json file gracefully."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        (settings_dir / "settings.json").write_text("", encoding="utf-8")

        action = _bootstrap_claude_settings(tmp_path)
        assert action == "updated"

        data = json.loads((settings_dir / "settings.json").read_text(encoding="utf-8"))
        assert "mcp__tapps-mcp" in data["permissions"]["allow"]
        assert "mcp__tapps-mcp__*" in data["permissions"]["allow"]

    def test_upgrades_wildcard_only_to_both(self, tmp_path):
        """Adds bare entry when only wildcard exists (upgrade path)."""
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        config = {"permissions": {"allow": ["mcp__tapps-mcp__*"]}}
        (settings_dir / "settings.json").write_text(
            json.dumps(config, indent=2) + "\n", encoding="utf-8"
        )

        action = _bootstrap_claude_settings(tmp_path)
        assert action == "updated"

        data = json.loads((settings_dir / "settings.json").read_text(encoding="utf-8"))
        assert "mcp__tapps-mcp" in data["permissions"]["allow"]
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
        assert "mcp__tapps-mcp" in data["permissions"]["allow"]
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
        assert "mcp__tapps-mcp" in data["permissions"]["allow"]
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


class TestBootstrapConfigFromParams:
    """Tests for BootstrapConfig.from_params() classmethod (Story 67.4)."""

    def test_from_params_defaults(self):
        """from_params with explicit level returns config with that level."""
        cfg = BootstrapConfig.from_params(llm_engagement_level="high")
        assert cfg.llm_engagement_level == "high"
        # All other fields should be at their defaults
        assert cfg.create_handoff is True
        assert cfg.dry_run is False
        assert cfg.minimal is False

    def test_from_params_forwards_kwargs(self):
        """from_params forwards extra kwargs to BootstrapConfig constructor."""
        cfg = BootstrapConfig.from_params(
            llm_engagement_level="low",
            dry_run=True,
            minimal=True,
            platform="cursor",
        )
        assert cfg.llm_engagement_level == "low"
        assert cfg.dry_run is True
        assert cfg.minimal is True
        assert cfg.platform == "cursor"

    def test_from_params_none_level_falls_back_to_settings(self):
        """from_params with None level loads from settings."""
        with patch(
            "tapps_core.config.settings.load_settings",
        ) as mock_settings:
            mock_settings.return_value.llm_engagement_level = "high"
            cfg = BootstrapConfig.from_params(llm_engagement_level=None)
            assert cfg.llm_engagement_level == "high"
            mock_settings.assert_called_once()

    def test_from_params_omitted_level_falls_back_to_settings(self):
        """from_params without llm_engagement_level loads from settings."""
        with patch(
            "tapps_core.config.settings.load_settings",
        ) as mock_settings:
            mock_settings.return_value.llm_engagement_level = "low"
            cfg = BootstrapConfig.from_params()
            assert cfg.llm_engagement_level == "low"

    def test_bootstrap_pipeline_accepts_config(self, tmp_path):
        """bootstrap_pipeline works when passed a pre-built BootstrapConfig."""
        cfg = BootstrapConfig(
            create_handoff=True,
            create_runlog=False,
            create_agents_md=False,
            create_tech_stack_md=False,
            verify_server=False,
            warm_cache_from_tech_stack=False,
            warm_expert_rag_from_tech_stack=False,
        )
        result = bootstrap_pipeline(tmp_path, config=cfg)
        assert "docs/TAPPS_HANDOFF.md" in result["created"]
        assert result["success"]

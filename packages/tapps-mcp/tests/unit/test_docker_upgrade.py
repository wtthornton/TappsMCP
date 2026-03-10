"""Tests for Epic 46 Story 46.6: Docker-Aware Upgrade Preservation.

Verifies that:
- Docker config entries are preserved during upgrade merge
- Non-Docker upgrades still work normally
- The merge logic preserves Docker gateway args
- The upgrade result includes Docker status information
- The ``_is_docker_entry()`` helper correctly identifies Docker configs
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from tapps_mcp.distribution.setup_generator import (
    _is_docker_entry,
    _is_valid_tapps_command,
    _merge_config,
)


# ---------------------------------------------------------------------------
# _is_docker_entry tests
# ---------------------------------------------------------------------------


class TestIsDockerEntry:
    """Tests for the ``_is_docker_entry()`` helper."""

    def test_docker_gateway_entry(self) -> None:
        entry = {
            "command": "docker",
            "args": ["mcp", "gateway", "run", "--profile", "tapps-standard"],
        }
        assert _is_docker_entry(entry) is True

    def test_non_docker_entry(self) -> None:
        entry = {
            "command": "tapps-mcp",
            "args": ["serve"],
        }
        assert _is_docker_entry(entry) is False

    def test_exe_entry(self) -> None:
        entry = {
            "command": "/usr/local/bin/tapps-mcp",
            "args": ["serve"],
        }
        assert _is_docker_entry(entry) is False

    def test_empty_dict(self) -> None:
        assert _is_docker_entry({}) is False

    def test_not_a_dict(self) -> None:
        assert _is_docker_entry("docker") is False  # type: ignore[arg-type]

    def test_none_command(self) -> None:
        assert _is_docker_entry({"command": None}) is False


# ---------------------------------------------------------------------------
# _is_valid_tapps_command tests for Docker
# ---------------------------------------------------------------------------


class TestIsValidTappsCommandDocker:
    """Tests that ``_is_valid_tapps_command`` accepts ``"docker"``."""

    def test_docker_is_valid(self) -> None:
        assert _is_valid_tapps_command("docker") is True

    def test_tapps_mcp_still_valid(self) -> None:
        assert _is_valid_tapps_command("tapps-mcp") is True

    def test_exe_path_still_valid(self) -> None:
        assert _is_valid_tapps_command("/usr/local/bin/tapps-mcp.exe") is True

    def test_random_command_invalid(self) -> None:
        assert _is_valid_tapps_command("python") is False


# ---------------------------------------------------------------------------
# _merge_config Docker preservation tests
# ---------------------------------------------------------------------------


class TestMergeConfigDockerPreservation:
    """Tests that ``_merge_config`` preserves Docker entries in upgrade mode."""

    def test_upgrade_preserves_docker_entry_command_and_args(self) -> None:
        """When existing entry is Docker, command and args are preserved."""
        existing: dict[str, Any] = {
            "mcpServers": {
                "tapps-mcp": {
                    "command": "docker",
                    "args": ["mcp", "gateway", "run", "--profile", "tapps-custom"],
                    "env": {"OLD_VAR": "old"},
                },
            },
        }
        merged = _merge_config(existing, "claude-code", upgrade_mode=True)
        entry = merged["mcpServers"]["tapps-mcp"]

        assert entry["command"] == "docker"
        assert entry["args"] == ["mcp", "gateway", "run", "--profile", "tapps-custom"]
        # env and instructions should be updated to new values
        assert "TAPPS_MCP_PROJECT_ROOT" in entry["env"]

    def test_upgrade_preserves_non_docker_entry(self) -> None:
        """When existing entry is non-Docker, command/args still preserved."""
        existing: dict[str, Any] = {
            "mcpServers": {
                "tapps-mcp": {
                    "command": "/custom/path/tapps-mcp",
                    "args": ["serve", "--verbose"],
                    "env": {"TAPPS_MCP_PROJECT_ROOT": "."},
                },
            },
        }
        merged = _merge_config(existing, "claude-code", upgrade_mode=True)
        entry = merged["mcpServers"]["tapps-mcp"]

        assert entry["command"] == "/custom/path/tapps-mcp"
        assert entry["args"] == ["serve", "--verbose"]

    def test_non_upgrade_mode_replaces_docker_entry(self) -> None:
        """Without upgrade_mode, Docker entry is replaced with standard."""
        existing: dict[str, Any] = {
            "mcpServers": {
                "tapps-mcp": {
                    "command": "docker",
                    "args": ["mcp", "gateway", "run", "--profile", "tapps-custom"],
                },
            },
        }
        merged = _merge_config(existing, "claude-code", upgrade_mode=False)
        entry = merged["mcpServers"]["tapps-mcp"]

        # Should be replaced with standard entry (not Docker)
        assert entry["command"] != "docker"

    def test_upgrade_preserves_separate_docker_gateway_entry(self) -> None:
        """Separate ``tapps-mcp-docker`` entry is preserved during upgrade."""
        existing: dict[str, Any] = {
            "mcpServers": {
                "tapps-mcp": {
                    "command": "tapps-mcp",
                    "args": ["serve"],
                },
                "tapps-mcp-docker": {
                    "command": "docker",
                    "args": ["mcp", "gateway", "run", "--profile", "tapps-standard"],
                },
            },
        }
        merged = _merge_config(existing, "claude-code", upgrade_mode=True)

        assert "tapps-mcp-docker" in merged["mcpServers"]
        docker_entry = merged["mcpServers"]["tapps-mcp-docker"]
        assert docker_entry["command"] == "docker"
        assert "--profile" in docker_entry["args"]

    def test_upgrade_no_docker_gateway_entry_no_error(self) -> None:
        """Upgrade with no tapps-mcp-docker entry does not error."""
        existing: dict[str, Any] = {
            "mcpServers": {
                "tapps-mcp": {
                    "command": "tapps-mcp",
                    "args": ["serve"],
                },
            },
        }
        merged = _merge_config(existing, "claude-code", upgrade_mode=True)
        assert "tapps-mcp-docker" not in merged["mcpServers"]

    def test_upgrade_preserves_other_servers(self) -> None:
        """Other MCP server entries are untouched during merge."""
        existing: dict[str, Any] = {
            "mcpServers": {
                "tapps-mcp": {
                    "command": "docker",
                    "args": ["mcp", "gateway", "run", "--profile", "tapps-standard"],
                },
                "other-server": {
                    "command": "other-mcp",
                    "args": ["serve"],
                },
            },
        }
        merged = _merge_config(existing, "claude-code", upgrade_mode=True)
        assert "other-server" in merged["mcpServers"]
        assert merged["mcpServers"]["other-server"]["command"] == "other-mcp"

    def test_docker_entry_gets_instructions_on_claude(self) -> None:
        """Docker entries on Claude Code still get instructions field updated."""
        existing: dict[str, Any] = {
            "mcpServers": {
                "tapps-mcp": {
                    "command": "docker",
                    "args": ["mcp", "gateway", "run", "--profile", "tapps-custom"],
                },
            },
        }
        merged = _merge_config(existing, "claude-code", upgrade_mode=True)
        entry = merged["mcpServers"]["tapps-mcp"]
        # The new_entry is built for claude-code, which includes instructions
        assert "instructions" in entry

    def test_cursor_docker_entry_preserved(self) -> None:
        """Docker entry preservation works for Cursor host too."""
        existing: dict[str, Any] = {
            "mcpServers": {
                "tapps-mcp": {
                    "command": "docker",
                    "args": ["mcp", "gateway", "run", "--profile", "tapps-cursor"],
                },
            },
        }
        merged = _merge_config(existing, "cursor", upgrade_mode=True)
        entry = merged["mcpServers"]["tapps-mcp"]
        assert entry["command"] == "docker"
        assert entry["args"] == ["mcp", "gateway", "run", "--profile", "tapps-cursor"]


# ---------------------------------------------------------------------------
# upgrade_pipeline Docker status tests
# ---------------------------------------------------------------------------


class TestUpgradePipelineDockerStatus:
    """Tests that ``upgrade_pipeline`` includes Docker info when enabled."""

    def test_upgrade_includes_docker_status_when_enabled(self, tmp_path: Path) -> None:
        """Docker status dict is included when docker.enabled is True."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        # Create minimal project structure
        (tmp_path / ".claude").mkdir()
        (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")

        mock_settings = _make_mock_settings(
            docker_enabled=True,
            docker_transport="docker",
            docker_profile="tapps-standard",
            docker_companions=["context7", "filesystem"],
        )

        with (
            patch("tapps_core.config.settings.load_settings", return_value=mock_settings),
            patch("tapps_mcp.pipeline.upgrade._upgrade_agents_md", return_value={"action": "up-to-date"}),
            patch("tapps_mcp.pipeline.upgrade._upgrade_platform", return_value={"host": "claude-code", "components": {}}),
        ):
            result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)

        assert "docker" in result
        docker_info = result["docker"]
        assert docker_info["transport"] == "docker"
        assert docker_info["profile_preserved"] is True
        assert "companions_status" in docker_info
        companions_status = docker_info["companions_status"]
        assert companions_status["status"] == "configured"
        assert "context7" in companions_status["configured"]
        assert "filesystem" in companions_status["configured"]

    def test_upgrade_companions_reported_as_configured_not_installed(
        self, tmp_path: Path
    ) -> None:
        """Companions are reported as 'configured' not 'installed'."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        (tmp_path / ".claude").mkdir()

        mock_settings = _make_mock_settings(
            docker_enabled=True,
            docker_transport="docker",
            docker_profile="tapps-standard",
            docker_companions=["context7", "filesystem"],
        )

        with (
            patch("tapps_core.config.settings.load_settings", return_value=mock_settings),
            patch("tapps_mcp.pipeline.upgrade._upgrade_agents_md", return_value={"action": "up-to-date"}),
            patch("tapps_mcp.pipeline.upgrade._upgrade_platform", return_value={"host": "claude-code", "components": {}}),
        ):
            result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)

        companions_status = result["docker"]["companions_status"]
        # Must NOT have "installed" or "missing" keys (the old no-op pattern)
        assert "installed" not in companions_status
        assert "missing" not in companions_status
        # Must have "configured" with honest status
        assert companions_status["status"] == "configured"
        assert companions_status["configured"] == ["context7", "filesystem"]
        assert "note" in companions_status

    def test_upgrade_no_docker_key_when_disabled(self, tmp_path: Path) -> None:
        """Docker status dict is NOT included when docker.enabled is False."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        (tmp_path / ".claude").mkdir()
        (tmp_path / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")

        mock_settings = _make_mock_settings(docker_enabled=False)

        with (
            patch("tapps_core.config.settings.load_settings", return_value=mock_settings),
            patch("tapps_mcp.pipeline.upgrade._upgrade_agents_md", return_value={"action": "up-to-date"}),
            patch("tapps_mcp.pipeline.upgrade._upgrade_platform", return_value={"host": "claude-code", "components": {}}),
        ):
            result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)

        assert "docker" not in result

    def test_upgrade_docker_empty_companions(self, tmp_path: Path) -> None:
        """Docker status works with empty companions list."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        (tmp_path / ".claude").mkdir()

        mock_settings = _make_mock_settings(
            docker_enabled=True,
            docker_transport="auto",
            docker_profile="tapps-minimal",
            docker_companions=[],
        )

        with (
            patch("tapps_core.config.settings.load_settings", return_value=mock_settings),
            patch("tapps_mcp.pipeline.upgrade._upgrade_agents_md", return_value={"action": "up-to-date"}),
            patch("tapps_mcp.pipeline.upgrade._upgrade_platform", return_value={"host": "claude-code", "components": {}}),
        ):
            result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)

        assert result["docker"]["companions_status"]["configured"] == []
        assert result["docker"]["companions_status"]["status"] == "configured"

    def test_upgrade_docker_key_present_for_backward_compat(self, tmp_path: Path) -> None:
        """Result dict still contains 'docker' key for backward compat."""
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        (tmp_path / ".claude").mkdir()

        mock_settings = _make_mock_settings(
            docker_enabled=True,
            docker_transport="docker",
            docker_profile="tapps-standard",
            docker_companions=["context7"],
        )

        with (
            patch("tapps_core.config.settings.load_settings", return_value=mock_settings),
            patch("tapps_mcp.pipeline.upgrade._upgrade_agents_md", return_value={"action": "up-to-date"}),
            patch("tapps_mcp.pipeline.upgrade._upgrade_platform", return_value={"host": "claude-code", "components": {}}),
        ):
            result = upgrade_pipeline(tmp_path, platform="claude", dry_run=True)

        # "docker" key must exist for backward compat
        assert "docker" in result
        assert "transport" in result["docker"]
        assert "companions_status" in result["docker"]


# ---------------------------------------------------------------------------
# Backup targets include Docker config
# ---------------------------------------------------------------------------


class TestBackupTargetsDocker:
    """Tests that Docker-related files are included in upgrade backups."""

    def test_tapps_yaml_included_in_backup_targets(self, tmp_path: Path) -> None:
        """The .tapps-mcp.yaml file is collected as a backup target."""
        from tapps_mcp.pipeline.upgrade import _collect_upgrade_targets

        yaml_path = tmp_path / ".tapps-mcp.yaml"
        yaml_path.write_text("docker:\n  enabled: true\n", encoding="utf-8")

        targets = _collect_upgrade_targets(tmp_path)
        assert yaml_path in targets

    def test_tapps_yaml_not_collected_when_missing(self, tmp_path: Path) -> None:
        """Missing .tapps-mcp.yaml is not in backup targets (no error)."""
        from tapps_mcp.pipeline.upgrade import _collect_upgrade_targets

        targets = _collect_upgrade_targets(tmp_path)
        yaml_path = tmp_path / ".tapps-mcp.yaml"
        assert yaml_path not in targets


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_settings(
    *,
    docker_enabled: bool = False,
    docker_transport: str = "auto",
    docker_profile: str = "tapps-standard",
    docker_companions: list[str] | None = None,
    engagement_level: str = "medium",
) -> Any:
    """Create a mock settings object with Docker configuration."""
    from unittest.mock import MagicMock

    settings = MagicMock()
    settings.llm_engagement_level = engagement_level
    settings.docker.enabled = docker_enabled
    settings.docker.transport = docker_transport
    settings.docker.profile = docker_profile
    settings.docker.companions = docker_companions if docker_companions is not None else ["context7"]
    return settings

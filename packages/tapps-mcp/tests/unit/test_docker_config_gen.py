"""Tests for Docker config generation in distribution.setup_generator."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from tapps_mcp.distribution.setup_generator import (
    _build_docker_server_entry,
    _merge_config,
)


class TestBuildDockerServerEntry:
    """Tests for _build_docker_server_entry."""

    def test_default_profile(self) -> None:
        settings = MagicMock()
        settings.docker.profile = "tapps-standard"
        entry = _build_docker_server_entry(settings)
        assert entry["command"] == "docker"
        assert entry["args"] == ["mcp", "gateway", "run", "--profile", "tapps-standard"]

    def test_custom_profile(self) -> None:
        settings = MagicMock()
        settings.docker.profile = "my-custom-profile"
        entry = _build_docker_server_entry(settings)
        assert entry["args"] == ["mcp", "gateway", "run", "--profile", "my-custom-profile"]

    def test_entry_structure(self) -> None:
        settings = MagicMock()
        settings.docker.profile = "test"
        entry = _build_docker_server_entry(settings)
        assert set(entry.keys()) == {"command", "args"}
        assert isinstance(entry["command"], str)
        assert isinstance(entry["args"], list)


class TestMergeConfigDockerPreservation:
    """Tests for Docker entry preservation during upgrades."""

    def test_upgrade_preserves_docker_entry(self) -> None:
        """Docker gateway entry is preserved during upgrade_mode."""
        existing: dict[str, Any] = {
            "mcpServers": {
                "tapps-mcp": {"command": "tapps-mcp", "args": ["serve"]},
                "tapps-mcp-docker": {
                    "command": "docker",
                    "args": ["mcp", "gateway", "run", "--profile", "my-profile"],
                },
            }
        }
        merged = _merge_config(existing, "claude-code", upgrade_mode=True)
        assert "tapps-mcp-docker" in merged["mcpServers"]
        assert merged["mcpServers"]["tapps-mcp-docker"]["command"] == "docker"

    def test_no_docker_entry_no_error(self) -> None:
        """When no Docker entry exists, merge still works."""
        existing: dict[str, Any] = {
            "mcpServers": {
                "tapps-mcp": {"command": "tapps-mcp", "args": ["serve"]},
            }
        }
        merged = _merge_config(existing, "claude-code", upgrade_mode=True)
        assert "tapps-mcp-docker" not in merged["mcpServers"]

    def test_non_upgrade_mode_ignores_docker(self) -> None:
        """In non-upgrade mode, Docker entry is not specially preserved."""
        existing: dict[str, Any] = {
            "mcpServers": {
                "tapps-mcp": {"command": "tapps-mcp", "args": ["serve"]},
                "tapps-mcp-docker": {
                    "command": "docker",
                    "args": ["mcp", "gateway", "run"],
                },
            }
        }
        merged = _merge_config(existing, "claude-code", upgrade_mode=False)
        # Non-tapps-mcp keys are preserved by the existing merge logic
        assert "tapps-mcp-docker" in merged["mcpServers"]

    def test_upgrade_preserves_docker_custom_args(self) -> None:
        """Custom Docker args are preserved exactly during upgrade."""
        docker_entry: dict[str, Any] = {
            "command": "docker",
            "args": ["mcp", "gateway", "run", "--profile", "custom", "--verbose"],
            "env": {"MY_VAR": "value"},
        }
        existing: dict[str, Any] = {
            "mcpServers": {
                "tapps-mcp": {"command": "old-path", "args": ["serve"]},
                "tapps-mcp-docker": docker_entry,
            }
        }
        merged = _merge_config(existing, "claude-code", upgrade_mode=True)
        assert merged["mcpServers"]["tapps-mcp-docker"] == docker_entry

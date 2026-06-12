"""Tests for NLT MCP plugin config generation (Epic 109.4)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from tapps_mcp.distribution.nlt_mcp_config import (
    commented_servers_for_bundle,
    enabled_servers_for_bundle,
    normalize_mcp_bundle,
)
from tapps_mcp.distribution.setup_generator import (
    _generate_config,
    _load_mcp_config_json,
    _merge_nlt_config,
    _serialize_nlt_mcp_config,
    _strip_jsonc_comments,
)


class TestNltBundles:
    def test_default_bundle_is_developer(self) -> None:
        assert normalize_mcp_bundle(None) == "developer"
        assert normalize_mcp_bundle("full") == "developer"

    def test_developer_enables_two_servers(self) -> None:
        enabled = enabled_servers_for_bundle("developer")
        assert enabled == ("nlt-code-quality", "nlt-platform-admin")
        assert len(commented_servers_for_bundle("developer")) == 3

    def test_planning_adds_linear(self) -> None:
        enabled = enabled_servers_for_bundle("planning")
        assert "nlt-linear-issues" in enabled
        assert len(enabled) == 3

    def test_docs_bundle(self) -> None:
        enabled = enabled_servers_for_bundle("docs")
        assert "nlt-project-docs" in enabled

    def test_release_bundle(self) -> None:
        enabled = enabled_servers_for_bundle("release")
        assert "nlt-release-ship" in enabled


class TestNltMcpJsonGeneration:
    def test_generate_developer_bundle_cursor(self, tmp_path: Path) -> None:
        with patch(
            "tapps_mcp.distribution.setup_generator.shutil.which",
            return_value="/bin/tapps-mcp",
        ):
            ok = _generate_config("cursor", tmp_path, force=True, mcp_bundle="developer", use_nlt_plugin=True)
        assert ok is True
        config_path = tmp_path / ".cursor" / "mcp.json"
        assert config_path.exists()
        raw = config_path.read_text(encoding="utf-8")
        assert "nlt-code-quality" in raw
        assert "nlt-platform-admin" in raw
        assert "// Opt-in:" in raw
        assert "nlt-linear-issues" in raw

        data = _load_mcp_config_json(config_path)
        servers = data["mcpServers"]
        assert "nlt-code-quality" in servers
        assert "nlt-platform-admin" in servers
        assert "tapps-mcp" not in servers
        assert servers["nlt-code-quality"]["args"] == []
        assert str(servers["nlt-code-quality"]["command"]).endswith("nlt-code-quality-serve.sh")

    def test_planning_bundle_enables_linear(self, tmp_path: Path) -> None:
        with patch(
            "tapps_mcp.distribution.setup_generator.shutil.which",
            return_value="/bin/tapps-mcp",
        ):
            ok = _generate_config("cursor", tmp_path, force=True, mcp_bundle="planning", use_nlt_plugin=True)
        assert ok is True
        data = _load_mcp_config_json(tmp_path / ".cursor" / "mcp.json")
        servers = data["mcpServers"]
        assert "nlt-linear-issues" in servers
        assert "nlt-project-docs" not in servers

    def test_legacy_monolith_mode(self, tmp_path: Path) -> None:
        with patch(
            "tapps_mcp.distribution.setup_generator.shutil.which",
            return_value="/bin/tapps-mcp",
        ):
            ok = _generate_config(
                "cursor",
                tmp_path,
                force=True,
                use_nlt_plugin=False,
            )
        assert ok is True
        data = json.loads((tmp_path / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        assert "tapps-mcp" in data["mcpServers"]
        assert "nlt-code-quality" not in data["mcpServers"]

    def test_jsonc_roundtrip(self, tmp_path: Path) -> None:
        merged, enabled, commented = _merge_nlt_config({}, "cursor", mcp_bundle="developer")
        text = _serialize_nlt_mcp_config(
            merged,
            "cursor",
            enabled=enabled,
            commented=commented,
        )
        stripped = _strip_jsonc_comments(text)
        parsed = json.loads(stripped)
        assert "nlt-code-quality" in parsed["mcpServers"]

    def test_migrates_legacy_tapps_env(self, tmp_path: Path) -> None:
        existing = {
            "mcpServers": {
                "tapps-mcp": {
                    "command": "tapps-mcp",
                    "args": ["serve"],
                    "env": {"TAPPS_MCP_CONTEXT7_API_KEY": "keep-me"},
                }
            }
        }
        merged, _, _ = _merge_nlt_config(
            existing,
            "cursor",
            mcp_bundle="developer",
            project_root=tmp_path,
        )
        env = merged["mcpServers"]["nlt-code-quality"]["env"]
        assert env["TAPPS_MCP_CONTEXT7_API_KEY"] == "keep-me"

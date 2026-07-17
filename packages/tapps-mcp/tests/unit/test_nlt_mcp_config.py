"""Tests for NLT MCP plugin config generation (Epic 109.4)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from tapps_mcp.distribution.nlt_mcp_config import (
    bundle_matches_mcp_config,
    commented_servers_for_bundle,
    enabled_servers_for_bundle,
    mcp_config_servers_for_bundle,
    normalize_mcp_bundle,
)
from tapps_mcp.distribution.setup_generator import (
    _generate_config,
    _merge_nlt_config,
    _serialize_nlt_mcp_config,
)


class TestNltBundles:
    def test_default_bundle_is_full(self) -> None:
        # ADR-0018: deployment default is full (all six nlt-* servers).
        assert normalize_mcp_bundle(None) == "full"
        assert normalize_mcp_bundle("bogus") == "full"

    def test_full_bundle_enables_all_servers(self) -> None:
        assert normalize_mcp_bundle("full") == "full"
        enabled = enabled_servers_for_bundle("full")
        assert len(enabled) == 6
        assert commented_servers_for_bundle("full") == ()

    def test_developer_enables_build_memory_linear(self) -> None:
        enabled = enabled_servers_for_bundle("developer")
        assert enabled == ("nlt-build", "nlt-memory", "nlt-linear-issues")
        assert mcp_config_servers_for_bundle("developer") == enabled
        commented = commented_servers_for_bundle("developer")
        assert commented == ("nlt-setup", "nlt-project-docs", "nlt-release-ship")

    def test_minimal_enables_build_only(self) -> None:
        enabled = enabled_servers_for_bundle("minimal")
        assert enabled == ("nlt-build",)
        assert mcp_config_servers_for_bundle("minimal") == enabled
        commented = commented_servers_for_bundle("minimal")
        assert len(commented) == 5

    def test_planning_adds_linear(self) -> None:
        enabled = enabled_servers_for_bundle("planning")
        assert enabled == ("nlt-build", "nlt-linear-issues")

    def test_docs_bundle(self) -> None:
        enabled = enabled_servers_for_bundle("docs")
        assert "nlt-project-docs" in enabled

    def test_release_bundle(self) -> None:
        enabled = enabled_servers_for_bundle("release")
        assert "nlt-release-ship" in enabled

    def test_bundle_matches_mcp_config(self) -> None:
        dev_servers = {
            "nlt-build": {"command": "x"},
            "nlt-memory": {"command": "x"},
            "nlt-linear-issues": {"command": "x"},
        }
        full_servers = {sid: {"command": "x"} for sid in mcp_config_servers_for_bundle("full")}
        assert bundle_matches_mcp_config(dev_servers, "developer") is True
        assert bundle_matches_mcp_config(full_servers, "full") is True
        assert bundle_matches_mcp_config(full_servers, "developer") is False


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
        assert "nlt-build" in raw
        assert "// Opt-in:" not in raw
        assert "nlt-setup" not in raw
        assert "nlt-project-docs" not in raw
        assert "nlt-release-ship" not in raw
        assert "nlt-memory" in raw
        assert "nlt-linear-issues" in raw

        data = json.loads(raw)
        servers = data["mcpServers"]
        assert set(servers.keys()) == {
            "nlt-build",
            "nlt-memory",
            "nlt-linear-issues",
        }
        assert "tapps-mcp" not in servers
        assert servers["nlt-build"]["args"] == []
        assert str(servers["nlt-build"]["command"]).endswith("nlt-build-serve.sh")

    def test_partial_bundles_write_strict_json_all_hosts(self, tmp_path: Path) -> None:
        """TAP-4811: every partial bundle must produce json.loads-valid host configs."""
        hosts = ("cursor", "claude-code", "vscode")
        bundles = ("developer", "minimal", "planning", "docs", "release")
        with patch(
            "tapps_mcp.distribution.setup_generator.shutil.which",
            return_value="/bin/tapps-mcp",
        ):
            for bundle in bundles:
                for host in hosts:
                    root = tmp_path / f"{bundle}-{host}"
                    ok = _generate_config(
                        host,
                        root,
                        force=True,
                        mcp_bundle=bundle,
                        use_nlt_plugin=True,
                    )
                    assert ok is True, f"{bundle}/{host}"
                    if host == "cursor":
                        path = root / ".cursor" / "mcp.json"
                    elif host == "vscode":
                        path = root / ".vscode" / "mcp.json"
                    else:
                        path = root / ".mcp.json"
                    raw = path.read_text(encoding="utf-8")
                    assert "// Opt-in:" not in raw, f"{bundle}/{host} still has comments"
                    parsed = json.loads(raw)
                    servers_key = "servers" if host == "vscode" else "mcpServers"
                    enabled = set(enabled_servers_for_bundle(bundle))
                    assert set(parsed[servers_key].keys()) == enabled

    def test_planning_bundle_enables_linear(self, tmp_path: Path) -> None:
        with patch(
            "tapps_mcp.distribution.setup_generator.shutil.which",
            return_value="/bin/tapps-mcp",
        ):
            ok = _generate_config("cursor", tmp_path, force=True, mcp_bundle="planning", use_nlt_plugin=True)
        assert ok is True
        data = json.loads((tmp_path / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        servers = data["mcpServers"]
        assert "nlt-linear-issues" in servers
        assert "nlt-project-docs" not in servers
        assert set(servers.keys()) == {"nlt-build", "nlt-linear-issues"}

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
        assert "nlt-build" not in data["mcpServers"]

    def test_serialize_omits_commented_servers(self) -> None:
        merged, enabled, commented = _merge_nlt_config({}, "cursor", mcp_bundle="developer")
        assert commented  # opt-in list still computed for CLI hints
        text = _serialize_nlt_mcp_config(
            merged,
            "cursor",
            enabled=enabled,
            commented=commented,
        )
        assert "// Opt-in:" not in text
        parsed = json.loads(text)
        assert set(parsed["mcpServers"].keys()) == {
            "nlt-build",
            "nlt-memory",
            "nlt-linear-issues",
        }

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
        env = merged["mcpServers"]["nlt-build"]["env"]
        assert env["TAPPS_MCP_CONTEXT7_API_KEY"] == "keep-me"

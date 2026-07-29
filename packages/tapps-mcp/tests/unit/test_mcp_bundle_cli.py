"""Tests for mcp-bundle show/set and upgrade bundle resolution."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from tapps_mcp.distribution.mcp_bundle_cli import set_mcp_bundle, show_mcp_bundle
from tapps_mcp.distribution.nlt_mcp_config import (
    NLT_SERVER_TOTAL_COUNTS,
    match_bundle_for_servers,
    resolve_upgrade_mcp_bundle,
)


class TestNltServerTotalCounts:
    def test_build_memory_setup_include_session_start(self) -> None:
        assert NLT_SERVER_TOTAL_COUNTS["nlt-build"] == 19
        assert NLT_SERVER_TOTAL_COUNTS["nlt-memory"] == 5
        assert NLT_SERVER_TOTAL_COUNTS["nlt-setup"] == 8


class TestMatchAndResolveBundle:
    def test_match_developer(self) -> None:
        servers = {
            "nlt-build": {},
            "nlt-memory": {},
            "nlt-linear-issues": {},
        }
        assert match_bundle_for_servers(servers) == "developer"

    def test_match_custom_returns_none(self) -> None:
        servers = {
            "nlt-build": {},
            "nlt-memory": {},
            "nlt-setup": {},
        }
        assert match_bundle_for_servers(servers) is None

    def test_resolve_explicit_yaml_wins(self, tmp_path: Path) -> None:
        bundle, explicit, note = resolve_upgrade_mcp_bundle(
            tmp_path, settings_bundle="developer"
        )
        assert bundle == "developer"
        assert explicit is True
        assert "settings" in note

    def test_resolve_infers_from_disk(self, tmp_path: Path) -> None:
        cursor = tmp_path / ".cursor"
        cursor.mkdir()
        (cursor / "mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "nlt-build": {"command": "x", "args": []},
                        "nlt-memory": {"command": "x", "args": []},
                        "nlt-linear-issues": {"command": "x", "args": []},
                    }
                }
            ),
            encoding="utf-8",
        )
        bundle, explicit, note = resolve_upgrade_mcp_bundle(
            tmp_path, settings_bundle=None
        )
        assert bundle == "developer"
        assert explicit is False
        assert "inferred" in note

    def test_resolve_custom_preserves(self, tmp_path: Path) -> None:
        cursor = tmp_path / ".cursor"
        cursor.mkdir()
        (cursor / "mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "nlt-build": {"command": "x", "args": []},
                        "nlt-memory": {"command": "x", "args": []},
                        "nlt-setup": {"command": "x", "args": []},
                    }
                }
            ),
            encoding="utf-8",
        )
        bundle, explicit, note = resolve_upgrade_mcp_bundle(
            tmp_path, settings_bundle=None
        )
        assert bundle is None
        assert explicit is False
        assert "preserved" in note


class TestMcpBundleCli:
    def test_show_reads_yaml_and_disk(self, tmp_path: Path) -> None:
        (tmp_path / ".tapps-mcp.yaml").write_text("mcp_bundle: minimal\n", encoding="utf-8")
        cursor = tmp_path / ".cursor"
        cursor.mkdir()
        (cursor / "mcp.json").write_text(
            json.dumps({"mcpServers": {"nlt-build": {"command": "x", "args": []}}}),
            encoding="utf-8",
        )
        info = show_mcp_bundle(tmp_path)
        assert info["yaml_mcp_bundle"] == "minimal"
        assert info["on_disk_matches_bundle"] == "minimal"
        assert info["resolved"] == "minimal"

    def test_set_writes_yaml_and_generates(self, tmp_path: Path) -> None:
        with (
            patch(
                "tapps_mcp.distribution.setup_generator._generate_config",
                return_value=True,
            ) as gen,
            patch(
                "tapps_mcp.distribution.setup_generator._should_use_uv_launch",
                return_value=(False, None, None),
            ),
        ):
            result = set_mcp_bundle(tmp_path, "developer", hosts=("cursor",))
        assert result["yaml_written"] is True
        yaml_text = (tmp_path / ".tapps-mcp.yaml").read_text(encoding="utf-8")
        assert "mcp_bundle: developer" in yaml_text
        assert result["hosts_updated"] == ["cursor"]
        gen.assert_called_once()
        assert gen.call_args.kwargs["mcp_bundle"] == "developer"

    def test_set_dry_run_no_write(self, tmp_path: Path) -> None:
        result = set_mcp_bundle(tmp_path, "minimal", dry_run=True, hosts=("cursor",))
        assert result["dry_run"] is True
        assert not (tmp_path / ".tapps-mcp.yaml").exists()


class TestUpgradePreservesCustomBundle:
    def test_custom_on_disk_not_rewritten_to_full(self, tmp_path: Path) -> None:
        from tapps_mcp.pipeline.upgrade import upgrade_pipeline

        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
        cursor = tmp_path / ".cursor"
        cursor.mkdir()
        custom = {
            "nlt-build": {
                "type": "stdio",
                "command": ".cursor/bin/nlt-build-serve.sh",
                "args": [],
            },
            "nlt-memory": {
                "type": "stdio",
                "command": ".cursor/bin/nlt-memory-serve.sh",
                "args": [],
            },
            "nlt-setup": {
                "type": "stdio",
                "command": ".cursor/bin/nlt-setup-serve.sh",
                "args": [],
            },
        }
        (cursor / "mcp.json").write_text(
            json.dumps({"mcpServers": custom}),
            encoding="utf-8",
        )
        # No mcp_bundle in yaml → custom set must be preserved
        no_drift = MagicMock(drift_detected=False)
        with patch("tapps_mcp.diagnostics.check_install_drift", return_value=no_drift):
            result = upgrade_pipeline(tmp_path, platform="cursor")
        mcp_config = result["components"]["platforms"][0]["components"]["mcp_config"]
        assert "preserved" in str(mcp_config)
        data = json.loads((cursor / "mcp.json").read_text(encoding="utf-8"))
        assert set(data["mcpServers"].keys()) == {
            "nlt-build",
            "nlt-memory",
            "nlt-setup",
        }

"""Tests for fleet upgrade helpers."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tapps_mcp.distribution.nlt_mcp_config import needs_legacy_nlt_migration
from tapps_mcp.tools.fleet_upgrade import (
    format_fleet_upgrade_markdown,
    resolve_fleet_roots,
    upgrade_project_root,
)


class TestNeedsLegacyNltMigration:
    def test_legacy_without_nlt(self) -> None:
        servers = {
            "tapps-mcp": {"command": "tapps-mcp", "args": ["serve"]},
            "docs-mcp": {"command": "docsmcp", "args": ["serve"]},
        }
        assert needs_legacy_nlt_migration(servers) is True

    def test_nlt_present(self) -> None:
        servers = {
            "nlt-code-quality": {"command": "tapps-mcp", "args": ["serve"]},
        }
        assert needs_legacy_nlt_migration(servers) is False

    def test_other_servers_preserved_check(self) -> None:
        servers = {
            "agentforge": {"command": "agentforge", "args": []},
            "tapps-mcp": {"command": "tapps-mcp", "args": ["serve"]},
        }
        assert needs_legacy_nlt_migration(servers) is True


class TestFleetUpgradeHelpers:
    def test_resolve_explicit_roots(self, tmp_path: Path) -> None:
        bootstrapped = tmp_path / "proj-a"
        bootstrapped.mkdir()
        (bootstrapped / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")
        bare = tmp_path / "bare"
        bare.mkdir()

        found = resolve_fleet_roots(explicit_roots=[bootstrapped, bare])
        assert found == [bootstrapped.resolve()]

    def test_dry_run_upgrade_project(self, tmp_path: Path) -> None:
        root = tmp_path / "consumer"
        root.mkdir()
        (root / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")

        result = upgrade_project_root(root, dry_run=True, run_doctor=False)
        assert result.success is True
        assert result.upgrade_ok is True
        assert result.init_ok is True
        assert any("[dry-run]" in msg for msg in result.messages)

    def test_strip_context7_env_sets_docs_via_brain_during_init(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = tmp_path / "consumer"
        root.mkdir()
        (root / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")
        monkeypatch.delenv("TAPPS_MCP_DOCS_VIA_BRAIN", raising=False)
        calls: list[list[str]] = []

        def _capture(args: list[str], *, cwd: Path, dry_run: bool, command_prefix: str = "tapps-mcp"):
            calls.append(list(args))
            return True, "[dry-run] ok"

        monkeypatch.setattr(
            "tapps_mcp.tools.fleet_upgrade._run_cli",
            _capture,
        )
        upgrade_project_root(
            root,
            dry_run=True,
            run_doctor=False,
            strip_context7_env=True,
        )
        assert os.environ.get("TAPPS_MCP_DOCS_VIA_BRAIN") is None
        assert any("init" in args for args in calls)

    def test_import_legacy_doc_cache_invokes_brain_cli(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = tmp_path / "consumer"
        root.mkdir()
        (root / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")
        cache_dir = root / ".tapps-mcp-cache" / "pytest"
        cache_dir.mkdir(parents=True)
        calls: list[tuple[list[str], str]] = []

        def _capture(
            args: list[str],
            *,
            cwd: Path,
            dry_run: bool,
            command_prefix: str = "tapps-mcp",
        ):
            calls.append((list(args), command_prefix))
            return True, "[dry-run] ok"

        monkeypatch.setattr(
            "tapps_mcp.tools.fleet_upgrade._run_cli",
            _capture,
        )
        upgrade_project_root(
            root,
            dry_run=True,
            run_doctor=False,
            import_legacy_doc_cache=True,
        )
        assert any(prefix == "tapps-brain" and "import-dir" in args for args, prefix in calls)

    def test_format_markdown(self) -> None:
        report = {
            "bundle": "developer",
            "uv_mode": "off",
            "summary": {"total": 1, "ok": 1, "failed": 0},
            "projects": [
                {
                    "root": "/tmp/AgentForge",
                    "success": True,
                    "upgrade_ok": True,
                    "init_ok": True,
                    "doctor_ok": True,
                    "errors": [],
                }
            ],
        }
        md = format_fleet_upgrade_markdown(report)
        assert "AgentForge" in md
        assert "developer" in md

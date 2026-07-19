"""Tests for fleet upgrade helpers."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from tapps_mcp.distribution.nlt_mcp_config import needs_legacy_nlt_migration
from tapps_mcp.tools.fleet_upgrade import (
    FleetUpgradeProjectResult,
    _reinstall_global_clis,
    format_fleet_upgrade_markdown,
    resolve_cli_binary,
    resolve_fleet_roots,
    run_fleet_upgrade,
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
        assert result.upgrade_binary
        assert any("[dry-run]" in msg for msg in result.messages)
        assert any("upgrade_binary=" in msg for msg in result.messages)

    def test_resolve_cli_binary_prefers_exe_adjacent_over_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """TAP-4836: stale PATH shim must not win over the invoking release bin."""
        import sys

        release_bin = tmp_path / "release" / "bin"
        release_bin.mkdir(parents=True)
        good = release_bin / "tapps-mcp"
        good.write_text("#!/bin/sh\necho good\n", encoding="utf-8")
        good.chmod(0o755)

        stale_dir = tmp_path / "stale"
        stale_dir.mkdir()
        stale = stale_dir / "tapps-mcp"
        stale.write_text("#!/bin/sh\necho stale\n", encoding="utf-8")
        stale.chmod(0o755)

        monkeypatch.setattr(sys, "executable", str(release_bin / "python"))
        monkeypatch.setenv("PATH", f"{stale_dir}{os.pathsep}{os.environ.get('PATH', '')}")

        resolved = resolve_cli_binary("tapps-mcp")
        assert resolved == str(good)

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

    def test_reinstall_defaults_to_blue_green_without_live_mcp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "tapps_mcp.distribution.mcp_zombie_reap.find_live_mcp_serve_pids",
            lambda: [],
        )
        deploy_called: list[bool] = []
        skip_gate_flags: list[bool] = []

        def _fake_deploy(checkout: Path, *, skip_gate: bool = False) -> dict[str, object]:
            deploy_called.append(True)
            skip_gate_flags.append(skip_gate)
            return {"ok": True, "release": "3.12.42-deadbeef", "current": str(checkout)}

        monkeypatch.setattr(
            "tapps_mcp.distribution.blue_green.deploy_blue_green",
            _fake_deploy,
        )
        result = _reinstall_global_clis(tmp_path)
        assert deploy_called == [True]
        assert skip_gate_flags == [True]
        assert result["strategy"] == "blue_green"
        assert result["ok"] is True

    def test_reinstall_auto_promotes_when_live_mcp(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "tapps_mcp.distribution.mcp_zombie_reap.find_live_mcp_serve_pids",
            lambda: [4242],
        )
        deploy_called: list[bool] = []
        skip_gate_flags: list[bool] = []

        def _fake_deploy(checkout: Path, *, skip_gate: bool = False) -> dict[str, object]:
            deploy_called.append(True)
            skip_gate_flags.append(skip_gate)
            return {"ok": True, "release": "3.12.40-deadbeef", "current": str(checkout)}

        monkeypatch.setattr(
            "tapps_mcp.distribution.blue_green.deploy_blue_green",
            _fake_deploy,
        )
        result = _reinstall_global_clis(tmp_path, use_blue_green=False)
        assert deploy_called == [True]
        assert skip_gate_flags == [True]
        assert result["strategy"] == "blue_green_auto"
        assert result["auto_promoted"] is True
        assert result["live_mcp_pids"] == [4242]

    def test_fleet_reinstall_refreshes_cursor_wrappers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        consumer = tmp_path / "consumer"
        consumer.mkdir()
        (consumer / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")
        (consumer / ".cursor").mkdir()
        (consumer / ".cursor" / "mcp.json").write_text('{"mcpServers": {}}', encoding="utf-8")

        def _fake_deploy(checkout: Path, *, skip_gate: bool = False) -> dict[str, object]:
            return {"ok": True, "release": "3.12.42-deadbeef", "current": str(checkout)}

        refreshed: list[Path] = []

        def _fake_regenerate(project_root: Path) -> list[str]:
            refreshed.append(project_root.resolve())
            return [".cursor/bin/nlt-build-serve.sh"]

        monkeypatch.setattr(
            "tapps_mcp.distribution.mcp_zombie_reap.find_live_mcp_serve_pids",
            lambda: [],
        )
        monkeypatch.setattr(
            "tapps_mcp.distribution.blue_green.deploy_blue_green",
            _fake_deploy,
        )
        monkeypatch.setattr(
            "tapps_mcp.distribution.setup_generator.regenerate_cursor_nlt_wrappers",
            _fake_regenerate,
        )
        monkeypatch.setattr(
            "tapps_mcp.tools.fleet_upgrade.upgrade_project_root",
            lambda root, **kwargs: FleetUpgradeProjectResult(
                root=root.resolve(),
                success=True,
                upgrade_ok=True,
            ),
        )

        report = run_fleet_upgrade(
            roots=[consumer],
            reinstall_clis=True,
            tapps_checkout=tmp_path,
            refresh_mcp=False,
            run_doctor=False,
        )

        assert refreshed == [consumer.resolve()]
        wrapper_refresh = report["reinstall_clis"]["wrapper_refresh"]
        assert wrapper_refresh == [
            {
                "root": str(consumer.resolve()),
                "ok": True,
                "written": [".cursor/bin/nlt-build-serve.sh"],
            }
        ]

    def test_reinstall_inplace_when_forced_despite_live_mcp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "tapps_mcp.distribution.mcp_zombie_reap.find_live_mcp_serve_pids",
            lambda: [4242],
        )
        proc = type("P", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()
        with patch(
            "tapps_mcp.tools.fleet_upgrade.subprocess.run",
            return_value=proc,
        ) as run_mock:
            result = _reinstall_global_clis(
                tmp_path,
                use_blue_green=False,
                force_inplace=True,
            )
        assert run_mock.called
        assert result["strategy"] == "inplace_forced"
        assert result["ok"] is True
        # TAP-4537: installs must include the treesitter extra so the tool env
        # computes the same call-graph fingerprint as the dev venv.
        specs = [call.args[0][-1] for call in run_mock.call_args_list]
        assert specs == [
            f"{tmp_path / 'packages' / 'tapps-mcp'}[treesitter]",
            f"{tmp_path / 'packages' / 'docs-mcp'}[treesitter]",
        ]

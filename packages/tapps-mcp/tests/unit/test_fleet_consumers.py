"""Tests for HTTP fleet consumer audit/repair (ADR-0024)."""

from __future__ import annotations

import json
from pathlib import Path

from tapps_mcp.distribution.fleet_consumers import (
    audit_consumer,
    audit_consumers,
    discover_http_fleet_consumers,
    repair_consumer,
)


def _write_cursor_http(root: Path, *, project_root: Path | None = None) -> None:
    target = project_root or root
    servers = {}
    for name, port in (
        ("nlt-build", 8760),
        ("nlt-memory", 8761),
        ("nlt-setup", 8762),
        ("nlt-linear-issues", 8763),
        ("nlt-project-docs", 8764),
        ("nlt-release-ship", 8765),
    ):
        servers[name] = {
            "type": "streamableHttp",
            "url": f"http://127.0.0.1:{port}/mcp",
            "headers": {"X-Tapps-Project-Root": str(target)},
        }
    path = root / ".cursor" / "mcp.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mcpServers": servers}, indent=2) + "\n", encoding="utf-8")


class TestDiscoverConsumers:
    def test_discovers_http_transport_yaml(self, tmp_path: Path) -> None:
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / ".tapps-mcp.yaml").write_text("mcp_transport: http\n", encoding="utf-8")
        _write_cursor_http(proj)
        found = discover_http_fleet_consumers(scan_parent=tmp_path)
        assert found == [proj.resolve()]

    def test_skips_default_scratch_names(self, tmp_path: Path) -> None:
        scratch = tmp_path / "AgentForge-verify4595"
        scratch.mkdir()
        (scratch / ".tapps-mcp.yaml").write_text("mcp_transport: http\n", encoding="utf-8")
        _write_cursor_http(scratch)
        found = discover_http_fleet_consumers(scan_parent=tmp_path)
        assert found == []


class TestAuditRepair:
    def test_audit_flags_wrong_project_root(self, tmp_path: Path) -> None:
        proj = tmp_path / "ReportLab-wt-briefs"
        proj.mkdir()
        (proj / ".tapps-mcp.yaml").write_text("mcp_transport: http\n", encoding="utf-8")
        wrong = tmp_path / "ReportLab"
        wrong.mkdir()
        _write_cursor_http(proj, project_root=wrong)
        (proj / "AGENTS.md").write_text("<!-- tapps-agents-version: 3.12.52 -->\n", encoding="utf-8")
        row = audit_consumer(proj, package_version="3.12.52")
        assert row["ok"] is False
        assert any("X-Tapps-Project-Root" in i for i in row["issues"])

    def test_repair_fixes_root_and_vscode_key(self, tmp_path: Path) -> None:
        proj = tmp_path / "consumer"
        proj.mkdir()
        (proj / ".tapps-mcp.yaml").write_text("quality_preset: standard\n", encoding="utf-8")
        wrong = tmp_path / "other"
        wrong.mkdir()
        _write_cursor_http(proj, project_root=wrong)
        vscode = proj / ".vscode" / "mcp.json"
        vscode.parent.mkdir(parents=True, exist_ok=True)
        vscode.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "nlt-build": {
                            "type": "stdio",
                            "command": "tapps-mcp",
                            "args": ["serve", "--profile", "nlt-build"],
                        }
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (proj / "AGENTS.md").write_text("<!-- tapps-agents-version: 3.12.52 -->\n", encoding="utf-8")
        (proj / "CLAUDE.md").write_text("<!-- tapps-claude-version: 3.12.52 -->\n", encoding="utf-8")

        result = repair_consumer(proj)
        assert "yaml" in result["changes"]
        assert "cursor" in result["changes"]
        assert "vscode" in result["changes"]

        cursor = json.loads((proj / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        assert cursor["mcpServers"]["nlt-build"]["headers"]["X-Tapps-Project-Root"] == str(
            proj.resolve()
        )

        vscode_data = json.loads(vscode.read_text(encoding="utf-8"))
        assert "servers" in vscode_data
        assert "mcpServers" not in vscode_data
        assert vscode_data["servers"]["nlt-build"]["type"] == "http"
        assert vscode_data["servers"]["nlt-build"]["url"] == "http://127.0.0.1:8760/mcp"

        row = audit_consumer(proj, package_version="3.12.52")
        assert row["ok"] is True

    def test_developer_bundle_only_requires_three_servers(self, tmp_path: Path) -> None:
        proj = tmp_path / "orch"
        proj.mkdir()
        (proj / ".tapps-mcp.yaml").write_text(
            "mcp_transport: http\nmcp_bundle: developer\n",
            encoding="utf-8",
        )
        servers = {}
        for name, port in (
            ("nlt-build", 8760),
            ("nlt-memory", 8761),
            ("nlt-linear-issues", 8763),
        ):
            servers[name] = {
                "type": "streamableHttp",
                "url": f"http://127.0.0.1:{port}/mcp",
                "headers": {"X-Tapps-Project-Root": str(proj.resolve())},
            }
        path = proj / ".cursor" / "mcp.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"mcpServers": servers}, indent=2) + "\n", encoding="utf-8")
        (proj / "AGENTS.md").write_text("<!-- tapps-agents-version: 3.12.52 -->\n", encoding="utf-8")
        row = audit_consumer(proj, package_version="3.12.52")
        assert row["ok"] is True
        assert row["enabled_servers"] == ["nlt-build", "nlt-memory", "nlt-linear-issues"]

    def test_audit_consumers_aggregate(self, tmp_path: Path) -> None:
        good = tmp_path / "good"
        good.mkdir()
        (good / ".tapps-mcp.yaml").write_text("mcp_transport: http\n", encoding="utf-8")
        _write_cursor_http(good)
        (good / "AGENTS.md").write_text("<!-- tapps-agents-version: 3.12.52 -->\n", encoding="utf-8")
        (good / "CLAUDE.md").write_text("<!-- tapps-claude-version: 3.12.52 -->\n", encoding="utf-8")
        report = audit_consumers(scan_parent=tmp_path)
        assert report["total"] == 1
        assert report["ok"] == 1
        assert report["fail"] == 0

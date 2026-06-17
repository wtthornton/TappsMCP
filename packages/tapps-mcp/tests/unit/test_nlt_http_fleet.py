"""Tests for shared HTTP MCP fleet config (ADR-0024)."""

from __future__ import annotations

from pathlib import Path

from tapps_core.http.request_context import PROJECT_ROOT_HEADER
from tapps_mcp.distribution.nlt_http_fleet import (
    NLT_HTTP_FLEET_PORTS,
    build_http_fleet_url,
    build_nlt_http_mcp_entry,
    resolve_http_project_root_header,
    resolve_mcp_transport,
)


class TestNltHttpFleet:
    def test_ports_cover_all_servers(self) -> None:
        assert set(NLT_HTTP_FLEET_PORTS) == {
            "nlt-build",
            "nlt-memory",
            "nlt-setup",
            "nlt-linear-issues",
            "nlt-project-docs",
            "nlt-release-ship",
        }

    def test_build_url(self) -> None:
        assert build_http_fleet_url("nlt-build") == "http://127.0.0.1:8760/mcp"

    def test_http_mcp_entry(self, tmp_path: Path) -> None:
        entry = build_nlt_http_mcp_entry("nlt-memory", project_root=tmp_path)
        assert entry["type"] == "streamableHttp"
        assert entry["url"] == "http://127.0.0.1:8761/mcp"
        assert entry["headers"][PROJECT_ROOT_HEADER] == str(tmp_path.resolve())

    def test_validates_http_entry(self, tmp_path: Path) -> None:
        from tapps_mcp.distribution.nlt_http_fleet import is_valid_http_fleet_mcp_entry

        entry = build_nlt_http_mcp_entry("nlt-build", project_root=tmp_path)
        assert is_valid_http_fleet_mcp_entry(entry) is True
        assert is_valid_http_fleet_mcp_entry({"type": "stdio", "command": "x"}) is False

    def test_resolve_transport_explicit(self) -> None:
        assert resolve_mcp_transport(None, explicit="http") == "http"

    def test_project_root_header_is_absolute(self, tmp_path: Path) -> None:
        value = resolve_http_project_root_header(tmp_path)
        assert value == str(tmp_path.resolve())
        assert "${" not in value

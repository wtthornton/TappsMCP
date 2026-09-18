"""Tests for tapps_mcp.distribution.doctor_server_skew (lane R3).

collect_build_skew() (tools/session_health.py) only ever compares values read
inside the process running the probe, so it cannot see a live, long-running
MCP server that never got restarted after a CLI upgrade. These tests fix
that against fixtures rather than a real fleet: ``probe_fleet_tool_result``
(network I/O) and ``collect_build_skew`` (disk metadata) are both monkeypatched,
so every assertion here is driven entirely by the fixture values below --
never by whatever tapps-mcp happens to be installed on the machine running
the suite.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tapps_mcp.distribution import doctor_server_skew as dss
from tapps_mcp.distribution.nlt_mcp_config import NLT_SERVER_SPECS


def _write_mcp_json(root: Path, servers: dict[str, str]) -> None:
    """Write a Claude Code .mcp.json with one http entry per (server_id -> url)."""
    root.joinpath(".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    server_id: {"type": "http", "url": url} for server_id, url in servers.items()
                }
            }
        ),
        encoding="utf-8",
    )


def _fake_probe(version_by_server: dict[str, str | None]) -> Any:
    """Build a fake ``probe_fleet_tool_result`` returning data.server.version per server_id.

    A ``None`` value simulates a server that cannot be reached at all (the
    ``ok: False`` transport-failure shape); an empty dict simulates a server
    that answers but omits ``data.server.version``.
    """

    def _probe(
        server_id: str, tool_name: str, arguments: dict[str, Any] | None = None, **_kw: Any
    ) -> dict[str, Any]:
        assert tool_name == "tapps_session_start"
        version = version_by_server.get(server_id)
        if version is None:
            return {
                "ok": False,
                "server_id": server_id,
                "stage": "initialize",
                "error": "connection failed: refused",
            }
        return {
            "ok": True,
            "server_id": server_id,
            "tool": tool_name,
            "data": {
                "tool": "tapps_session_start",
                "success": True,
                "data": {"server": {"version": version}} if version else {},
            },
        }

    return _probe


def _fake_build_skew(installed_version: str | None) -> Any:
    return lambda: {
        "running_version": installed_version,
        "installed_version": installed_version,
        "skew": False,
    }


class TestTappsBackedFleetServers:
    def test_no_config_returns_empty(self, tmp_path: Path) -> None:
        assert dss._tapps_backed_fleet_servers(tmp_path) == []

    def test_filters_out_docs_mcp_backed_entry(self, tmp_path: Path) -> None:
        # Threshold check: nlt-project-docs must actually be env_kind "docs" in
        # the live registry, or this test would pass for the wrong reason.
        assert NLT_SERVER_SPECS["nlt-project-docs"]["env_kind"] == "docs"
        assert NLT_SERVER_SPECS["nlt-build"]["env_kind"] == "tapps"
        _write_mcp_json(
            tmp_path,
            {
                "nlt-build": "http://127.0.0.1:8760/mcp",
                "nlt-project-docs": "http://127.0.0.1:8764/mcp",
            },
        )
        candidates = dss._tapps_backed_fleet_servers(tmp_path)
        server_ids = [server_id for server_id, _url in candidates]
        assert server_ids == ["nlt-build"]

    def test_dedupes_by_server_id(self, tmp_path: Path) -> None:
        # Two host configs (.mcp.json + .cursor/mcp.json) declaring the same
        # server_id must be probed once, not twice.
        _write_mcp_json(tmp_path, {"nlt-build": "http://127.0.0.1:8760/mcp"})
        cursor_dir = tmp_path / ".cursor"
        cursor_dir.mkdir()
        cursor_dir.joinpath("mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "nlt-build": {"type": "streamableHttp", "url": "http://127.0.0.1:8760/mcp"}
                    }
                }
            ),
            encoding="utf-8",
        )
        candidates = dss._tapps_backed_fleet_servers(tmp_path)
        assert [server_id for server_id, _url in candidates] == ["nlt-build"]


class TestCheckFleetServerCliSkew:
    def test_no_declared_servers_passes(self, tmp_path: Path) -> None:
        result = dss.check_fleet_server_cli_skew(tmp_path)
        assert result.ok is True
        assert "No tapps-mcp HTTP fleet" in result.message

    def test_matched_versions_is_not_skew(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Coverage control (positive control): equal versions -> no skew.

        Expected to pass on both the fixed and unfixed shape of this check --
        it is NOT evidence the fix works, only that the happy path still
        reports clean. See test_skew_detected_names_both_versions for the
        negative control.
        """
        _write_mcp_json(tmp_path, {"nlt-build": "http://127.0.0.1:8760/mcp"})
        monkeypatch.setattr(
            "tapps_mcp.distribution.fleet_smoke.probe_fleet_tool_result",
            _fake_probe({"nlt-build": "3.12.90"}),
        )
        monkeypatch.setattr(
            "tapps_mcp.tools.session_health.collect_build_skew",
            _fake_build_skew("3.12.90"),
        )
        result = dss.check_fleet_server_cli_skew(tmp_path)
        assert result.ok is True
        assert "3.12.90" in result.message

    def test_skew_detected_names_both_versions(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Negative control: this MUST fail on unfixed code.

        Mechanism: check_fleet_server_cli_skew reads
        collect_build_skew()["installed_version"] (here forced to "3.12.90")
        and string-compares it against
        probe_fleet_tool_result(...)['data']['data']['server']['version']
        (here forced to "3.12.89") for every candidate server. "3.12.90" !=
        "3.12.89" is a plain string inequality -- there is no rounding or
        normalization between the fixture values and the comparison, so this
        pair is guaranteed to land in the ``skewed`` branch once the probe is
        actually consulted. The unfixed shape of this code (see the module
        docstring: build-skew is an in-process-only comparison) never calls
        probe_fleet_tool_result at all, so it cannot observe "nlt-build" and
        must report ok=True regardless of this fixture -- which is exactly
        the false "skew=False" the lane's motivating measurement showed.
        """
        _write_mcp_json(tmp_path, {"nlt-build": "http://127.0.0.1:8760/mcp"})
        monkeypatch.setattr(
            "tapps_mcp.distribution.fleet_smoke.probe_fleet_tool_result",
            _fake_probe({"nlt-build": "3.12.89"}),
        )
        monkeypatch.setattr(
            "tapps_mcp.tools.session_health.collect_build_skew",
            _fake_build_skew("3.12.90"),
        )
        result = dss.check_fleet_server_cli_skew(tmp_path)
        assert result.ok is False
        assert "3.12.90" in result.message
        assert "nlt-build=3.12.89" in result.message
        assert "restart" in result.detail.lower()

    def test_unreachable_server_refuses_not_no_skew(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Refusal control: an unreachable declared server must not read as no skew."""
        _write_mcp_json(tmp_path, {"nlt-build": "http://127.0.0.1:8760/mcp"})
        monkeypatch.setattr(
            "tapps_mcp.distribution.fleet_smoke.probe_fleet_tool_result",
            _fake_probe({"nlt-build": None}),
        )
        monkeypatch.setattr(
            "tapps_mcp.tools.session_health.collect_build_skew",
            _fake_build_skew("3.12.90"),
        )
        result = dss.check_fleet_server_cli_skew(tmp_path)
        assert result.ok is False
        assert "did not report a version" in result.message
        assert "nlt-build" in result.message

    def test_versionless_response_refuses_not_no_skew(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Refusal control: a server that answers without a version must not read as no skew."""
        _write_mcp_json(tmp_path, {"nlt-build": "http://127.0.0.1:8760/mcp"})
        monkeypatch.setattr(
            "tapps_mcp.distribution.fleet_smoke.probe_fleet_tool_result",
            _fake_probe({"nlt-build": ""}),
        )
        monkeypatch.setattr(
            "tapps_mcp.tools.session_health.collect_build_skew",
            _fake_build_skew("3.12.90"),
        )
        result = dss.check_fleet_server_cli_skew(tmp_path)
        assert result.ok is False
        assert "did not report a version" in result.message

    def test_unreadable_installed_version_refuses(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_mcp_json(tmp_path, {"nlt-build": "http://127.0.0.1:8760/mcp"})
        monkeypatch.setattr(
            "tapps_mcp.tools.session_health.collect_build_skew",
            _fake_build_skew(None),
        )
        result = dss.check_fleet_server_cli_skew(tmp_path)
        assert result.ok is False
        assert "could not be read" in result.message

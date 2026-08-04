"""Smoke tests for tapps_mcp.distribution.doctor_fleet (TAP-5606 split)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.distribution.doctor_fleet import (
    _cursor_config_transport,
    _iter_http_fleet_endpoints,
    _yaml_mcp_transport,
    check_fleet_crash_loop,
    check_http_fleet_liveness,
    check_mcp_transport_drift,
)


def test_iter_http_fleet_endpoints_no_configs_returns_empty(tmp_path: Path) -> None:
    assert _iter_http_fleet_endpoints(tmp_path) == []


def test_check_http_fleet_liveness_no_entries_passes(tmp_path: Path) -> None:
    result = check_http_fleet_liveness(tmp_path)
    assert result.ok is True
    assert "stdio" in result.message.lower()


def test_check_fleet_crash_loop_no_pid_files_passes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "tapps_mcp.distribution.nlt_http_fleet.FLEET_PID_DIR",
        tmp_path / "fleet-pids",
    )
    result = check_fleet_crash_loop()
    assert result.ok is True


def test_cursor_config_transport_missing_returns_none(tmp_path: Path) -> None:
    assert _cursor_config_transport(tmp_path) is None


def test_yaml_mcp_transport_missing_returns_none(tmp_path: Path) -> None:
    assert _yaml_mcp_transport(tmp_path) is None


def test_check_mcp_transport_drift_no_config_passes(tmp_path: Path) -> None:
    result = check_mcp_transport_drift(tmp_path)
    assert result.ok is True
    assert "No Cursor MCP config" in result.message

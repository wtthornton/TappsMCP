"""Smoke tests for tapps_mcp.distribution.doctor_fleet (TAP-5606 split)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.distribution import doctor_fleet
from tapps_mcp.distribution.doctor_fleet import (
    _cursor_config_transport,
    _iter_http_fleet_endpoints,
    _yaml_mcp_transport,
    check_fleet_crash_loop,
    check_fleet_watchdog_timer,
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


class TestCheckFleetWatchdogTimer:
    """TAP-7845: `is-active` reads green on a timer with no next elapse."""

    def test_no_systemctl_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(doctor_fleet, "_systemd_user_show", lambda *_a, **_kw: None)
        result = check_fleet_watchdog_timer()
        assert result.ok is True

    def test_unit_not_installed_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            doctor_fleet, "_systemd_user_show", lambda *_a, **_kw: {"LoadState": "not-found"}
        )
        result = check_fleet_watchdog_timer()
        assert result.ok is True
        assert "not installed" in result.message

    def test_inactive_and_disabled_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            doctor_fleet,
            "_systemd_user_show",
            lambda *_a, **_kw: {
                "LoadState": "loaded",
                "ActiveState": "inactive",
                "UnitFileState": "disabled",
                "NextElapseUSecMonotonic": "infinity",
                "NextElapseUSecRealtime": "",
            },
        )
        result = check_fleet_watchdog_timer()
        assert result.ok is True

    def test_active_with_infinite_monotonic_and_empty_realtime_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # This is the exact shape measured on the live host (TAP-7845): the
        # timer fired once, then never re-armed, while `is-active` stayed green.
        monkeypatch.setattr(
            doctor_fleet,
            "_systemd_user_show",
            lambda *_a, **_kw: {
                "LoadState": "loaded",
                "ActiveState": "active",
                "UnitFileState": "enabled",
                "NextElapseUSecMonotonic": "infinity",
                "NextElapseUSecRealtime": "",
            },
        )
        result = check_fleet_watchdog_timer()
        assert result.ok is False
        assert "infinity" in result.message

    def test_active_with_finite_monotonic_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Discrimination positive control: a healthy OnActiveSec/OnUnitActiveSec
        # timer with a real next elapse must not be blanket-flagged unhealthy.
        monkeypatch.setattr(
            doctor_fleet,
            "_systemd_user_show",
            lambda *_a, **_kw: {
                "LoadState": "loaded",
                "ActiveState": "active",
                "UnitFileState": "enabled",
                "NextElapseUSecMonotonic": "59.913440s",
                "NextElapseUSecRealtime": "",
            },
        )
        result = check_fleet_watchdog_timer()
        assert result.ok is True

    def test_active_with_only_calendar_backstop_passes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Discrimination positive control: an OnCalendar-only schedule reports
        # NextElapseUSecMonotonic=infinity by design (no monotonic trigger
        # exists) but must still be read as healthy via the realtime clock.
        monkeypatch.setattr(
            doctor_fleet,
            "_systemd_user_show",
            lambda *_a, **_kw: {
                "LoadState": "loaded",
                "ActiveState": "active",
                "UnitFileState": "enabled",
                "NextElapseUSecMonotonic": "infinity",
                "NextElapseUSecRealtime": "Fri 2026-09-18 11:36:00 PDT",
            },
        )
        result = check_fleet_watchdog_timer()
        assert result.ok is True

    def test_against_live_host_state(self) -> None:
        """Integration control: run the real check against this host's systemd.

        No mocking -- exercises `_systemd_user_show` for real. Asserts only
        that the check does not crash and returns a well-formed CheckResult;
        the pass/fail verdict depends on live host state (see LANE-COMPLETE
        evidence block for the actual red/green systemctl output).
        """
        result = check_fleet_watchdog_timer()
        assert result.name == "Fleet watchdog timer"
        assert isinstance(result.ok, bool)

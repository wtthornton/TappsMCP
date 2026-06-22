"""Tests for fleet supervision: systemd units + health-aware watchdog (ADR-0024)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tapps_mcp.distribution import fleet_control


class TestInstallSystemdUnits:
    @pytest.fixture
    def units(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(
            fleet_control, "_resolve_tapps_mcp_bin", lambda: "/opt/tapps/bin/tapps-mcp"
        )
        paths = fleet_control.install_systemd_user_unit()
        return {p.name: p.read_text(encoding="utf-8") for p in paths}

    def test_writes_all_three_units(self, units: dict[str, str]) -> None:
        assert set(units) == {
            "tapps-mcp-fleet.service",
            "tapps-mcp-fleet-watch.service",
            "tapps-mcp-fleet-watch.timer",
        }

    def test_canonical_service_keeps_cgroup_alive(self, units: dict[str, str]) -> None:
        service = units["tapps-mcp-fleet.service"]
        assert "RemainAfterExit=yes" in service
        assert "ExecStart=/opt/tapps/bin/tapps-mcp fleet start" in service

    def test_watchdog_uses_ensure_not_start(self, units: dict[str, str]) -> None:
        # The regression: a watchdog calling `fleet start` directly reaps the
        # fleet via cgroup teardown. It must call `fleet ensure` instead.
        watch = units["tapps-mcp-fleet-watch.service"]
        assert "ExecStart=/opt/tapps/bin/tapps-mcp fleet ensure" in watch
        assert "fleet start" not in watch
        assert "RemainAfterExit" not in watch

    def test_timer_polls_every_60s(self, units: dict[str, str]) -> None:
        timer = units["tapps-mcp-fleet-watch.timer"]
        assert "OnUnitActiveSec=60" in timer
        assert "WantedBy=timers.target" in timer


def _listening(down_ports: set[int]) -> Any:
    """Return a fake _port_listening that reports *down_ports* as not listening."""

    def _probe(_host: str, port: int, **_kw: Any) -> bool:
        return port not in down_ports

    return _probe


class TestEnsureFleetRunning:
    def test_healthy_is_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(fleet_control, "_port_listening", _listening(set()))
        result = fleet_control.ensure_fleet_running()
        assert result == {"action": "none", "healthy": True, "unhealthy": []}

    def test_unhealthy_restarts_canonical_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 8760 == nlt-build port; mark it down so the fleet is unhealthy.
        monkeypatch.setattr(fleet_control, "_port_listening", _listening({8760}))
        monkeypatch.setattr(fleet_control, "_systemd_unit_available", lambda _unit: True)
        calls: list[list[str]] = []

        class _Proc:
            returncode = 0

        def _run(cmd: list[str], **_kw: Any) -> _Proc:
            calls.append(cmd)
            return _Proc()

        monkeypatch.setattr(fleet_control.subprocess, "run", _run)

        def _no_direct(**_kw: Any) -> dict[str, Any]:  # pragma: no cover - must not run
            raise AssertionError("start_fleet should not be called under systemd")

        monkeypatch.setattr(fleet_control, "start_fleet", _no_direct)

        result = fleet_control.ensure_fleet_running()
        assert result["action"] == "systemd_restart"
        assert result["unhealthy"] == ["nlt-build"]
        assert calls == [["systemctl", "--user", "restart", "tapps-mcp-fleet.service"]]

    def test_unhealthy_without_systemd_falls_back_to_direct_start(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(fleet_control, "_port_listening", _listening({8760}))
        monkeypatch.setattr(fleet_control, "_systemd_unit_available", lambda _unit: False)
        started: list[bool] = []
        monkeypatch.setattr(
            fleet_control, "start_fleet", lambda *, force: started.append(force) or {}
        )
        result = fleet_control.ensure_fleet_running()
        assert result["action"] == "direct_start"
        assert started == [True]


class TestDoctorCrashLoopCheck:
    @pytest.fixture
    def pid_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        from tapps_mcp.distribution import nlt_http_fleet

        pid_dir = tmp_path / "pids"
        pid_dir.mkdir()
        monkeypatch.setattr(nlt_http_fleet, "FLEET_PID_DIR", pid_dir)
        return pid_dir

    def test_no_pid_files_passes(self, pid_dir: Path) -> None:
        from tapps_mcp.distribution.doctor import check_fleet_crash_loop

        result = check_fleet_crash_loop(Path.cwd())
        assert result.ok is True
        assert "not supervised" in result.message

    def test_pids_present_ports_down_flags_crash_loop(
        self, pid_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tapps_mcp.distribution import doctor

        (pid_dir / "nlt-build.pid").write_text("123", encoding="utf-8")
        (pid_dir / "nlt-memory.pid").write_text("124", encoding="utf-8")
        monkeypatch.setattr(doctor, "_probe_tcp", lambda _url, **_kw: False)

        result = doctor.check_fleet_crash_loop(Path.cwd())
        assert result.ok is False
        assert "started-then-died" in result.message
        assert "install-systemd" in result.detail

    def test_pids_present_ports_up_passes(
        self, pid_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tapps_mcp.distribution import doctor

        (pid_dir / "nlt-build.pid").write_text("123", encoding="utf-8")
        monkeypatch.setattr(doctor, "_probe_tcp", lambda _url, **_kw: True)

        result = doctor.check_fleet_crash_loop(Path.cwd())
        assert result.ok is True

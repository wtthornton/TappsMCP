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
    @pytest.fixture(autouse=True)
    def _no_sleep(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Keep the re-probe backoff from slowing the suite down.
        import time

        monkeypatch.setattr(time, "sleep", lambda _s: None)

    @pytest.fixture(autouse=True)
    def _isolate_state(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # The watchdog debounce persists the previous unhealthy set to disk;
        # keep that out of the real ~/.tapps-mcp during tests.
        monkeypatch.setattr(
            fleet_control, "FLEET_WATCH_STATE_FILE", tmp_path / ".watch-unhealthy.json"
        )

    @pytest.fixture(autouse=True)
    def _mcp_ok_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # TCP-focused tests must not hit a real /mcp; assume handshake OK unless
        # a test explicitly patches _mcp_initialize_ok / _mcp_persistently_*.
        monkeypatch.setattr(fleet_control, "_mcp_initialize_ok", lambda *_a, **_k: True)

    @staticmethod
    def _seed_prev_unhealthy(*server_ids: str) -> None:
        # Simulate a prior watchdog poll that already saw these servers down,
        # so the next call treats them as confirmed (debounce satisfied).
        fleet_control._write_prev_unhealthy(set(server_ids))

    def test_healthy_is_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(fleet_control, "_port_listening", _listening(set()))
        result = fleet_control.ensure_fleet_running()
        assert result == {"action": "none", "healthy": True, "unhealthy": []}

    def test_mcp_starved_but_tcp_up_defers_then_restarts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Regression: event-loop starvation left TCP listening while Cursor
        # timed out on initialize ("Loading tools"). Watchdog must see that.
        monkeypatch.setattr(fleet_control, "_port_listening", _listening(set()))
        monkeypatch.setattr(
            fleet_control,
            "_mcp_initialize_ok",
            lambda server_id, **_k: server_id != "nlt-build",
        )
        monkeypatch.setattr(fleet_control, "_systemd_unit_available", lambda _unit: True)

        def _no_restart(*_a: Any, **_kw: Any) -> Any:  # pragma: no cover - first poll
            raise AssertionError("first MCP-starve strike must defer")

        monkeypatch.setattr(fleet_control.subprocess, "run", _no_restart)
        monkeypatch.setattr(fleet_control, "start_fleet", _no_restart)

        first = fleet_control.ensure_fleet_running()
        assert first["action"] == "defer"
        assert first["unhealthy"] == ["nlt-build"]

        class _Proc:
            returncode = 0

        calls: list[list[str]] = []

        def _run(cmd: list[str], **_kw: Any) -> _Proc:
            calls.append(cmd)
            return _Proc()

        monkeypatch.setattr(fleet_control.subprocess, "run", _run)
        monkeypatch.setattr(
            fleet_control, "start_fleet", lambda **_k: (_ for _ in ()).throw(AssertionError())
        )

        second = fleet_control.ensure_fleet_running()
        assert second["action"] == "systemd_restart"
        assert second["unhealthy"] == ["nlt-build"]
        assert calls == [["systemctl", "--user", "restart", "tapps-mcp-fleet.service"]]

    def test_transient_single_miss_does_not_restart(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # One failed probe followed by success must NOT trip a fleet-wide restart
        # (that would sever every client's HTTP session). Regression for the
        # watchdog restarting a healthy fleet mid-commit (ADR-0024).
        seen: dict[int, int] = {}

        def _flaky(_host: str, port: int, **_kw: Any) -> bool:
            seen[port] = seen.get(port, 0) + 1
            return not (port == 8760 and seen[port] == 1)

        monkeypatch.setattr(fleet_control, "_port_listening", _flaky)

        def _no_restart(*_a: Any, **_kw: Any) -> Any:  # pragma: no cover - must not run
            raise AssertionError("watchdog must not restart on a transient miss")

        monkeypatch.setattr(fleet_control.subprocess, "run", _no_restart)
        monkeypatch.setattr(fleet_control, "start_fleet", _no_restart)

        result = fleet_control.ensure_fleet_running()
        assert result == {"action": "none", "healthy": True, "unhealthy": []}

    def test_first_strike_defers_without_restart(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A server down on a single poll (no prior strike) must defer, not
        # restart -- this is the host-overload debounce.
        monkeypatch.setattr(fleet_control, "_port_listening", _listening({8764}))

        def _no_restart(*_a: Any, **_kw: Any) -> Any:  # pragma: no cover - must not run
            raise AssertionError("first strike must not restart")

        monkeypatch.setattr(fleet_control.subprocess, "run", _no_restart)
        monkeypatch.setattr(fleet_control, "start_fleet", _no_restart)

        result = fleet_control.ensure_fleet_running()
        assert result["action"] == "defer"
        assert result["unhealthy"] == ["nlt-project-docs"]
        # The suspect set is persisted for the next poll's confirmation.
        assert fleet_control._read_prev_unhealthy() == {"nlt-project-docs"}

    def test_unhealthy_restarts_canonical_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 8760 == nlt-build port; mark it down so the fleet is unhealthy.
        monkeypatch.setattr(fleet_control, "_port_listening", _listening({8760}))
        monkeypatch.setattr(fleet_control, "_systemd_unit_available", lambda _unit: True)
        self._seed_prev_unhealthy("nlt-build")  # second consecutive strike
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
        self._seed_prev_unhealthy("nlt-build")  # second consecutive strike
        started: list[bool] = []
        monkeypatch.setattr(
            fleet_control, "start_fleet", lambda *, force: started.append(force) or {}
        )
        result = fleet_control.ensure_fleet_running()
        assert result["action"] == "direct_start"
        assert started == [True]


class TestFleetStatusReachability:
    def test_reachable_uses_tcp_not_http_root(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Platform servers return 404 on `/`; status must not treat that as down.
        seen: list[tuple[str, int]] = []

        def _probe(host: str, port: int, **_kw: Any) -> bool:
            seen.append((host, port))
            return True

        monkeypatch.setattr(fleet_control, "_port_listening", _probe)
        assert fleet_control._http_reachable("nlt-project-docs") is True
        assert seen == [(fleet_control.resolve_fleet_host(), 8764)]


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

        result = check_fleet_crash_loop()
        assert result.ok is True
        assert "not supervised" in result.message

    def test_pids_present_ports_down_flags_crash_loop(
        self, pid_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tapps_mcp.distribution import doctor

        (pid_dir / "nlt-build.pid").write_text("123", encoding="utf-8")
        (pid_dir / "nlt-memory.pid").write_text("124", encoding="utf-8")
        monkeypatch.setattr(doctor, "_probe_tcp", lambda _url, **_kw: False)

        result = doctor.check_fleet_crash_loop()
        assert result.ok is False
        assert "started-then-died" in result.message
        assert "install-systemd" in result.detail

    def test_pids_present_ports_up_passes(
        self, pid_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tapps_mcp.distribution import doctor

        (pid_dir / "nlt-build.pid").write_text("123", encoding="utf-8")
        monkeypatch.setattr(doctor, "_probe_tcp", lambda _url, **_kw: True)

        result = doctor.check_fleet_crash_loop()
        assert result.ok is True

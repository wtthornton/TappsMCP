"""Watchdog debounce + death-cause instrumentation regressions (TAP-6053).

Every test here drives ``ensure_fleet_running`` against a ``tmp_path`` state
directory. Nothing in this module touches the live fleet, its systemd units, or
``~/.tapps-mcp/fleet/``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from tapps_core import brain_bridge
from tapps_mcp.distribution import fleet_control

# 8760 == nlt-build, 8764 == nlt-project-docs (NLT_HTTP_FLEET_PORTS).
_BUILD_PORT = 8760


def _listening(down_ports: set[int]) -> Any:
    def _probe(_host: str, port: int, **_kw: Any) -> bool:
        return port not in down_ports

    return _probe


class _Proc:
    returncode = 0


class TestManualEnsureCannotStarveConfirmation:
    """Acceptance 3 + regression test (b) from TAP-6053."""

    @pytest.fixture(autouse=True)
    def _no_sleep(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import time

        monkeypatch.setattr(time, "sleep", lambda _s: None)

    @pytest.fixture(autouse=True)
    def _isolate_state(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            fleet_control, "FLEET_WATCH_STATE_FILE", tmp_path / ".watch-unhealthy.json"
        )
        monkeypatch.setattr(fleet_control, "FLEET_LOG_DIR", tmp_path / "logs")
        monkeypatch.setattr(fleet_control, "FLEET_PID_DIR", tmp_path / "pids")

    @pytest.fixture(autouse=True)
    def _mcp_ok_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(fleet_control, "_mcp_initialize_ok", lambda *_a, **_k: True)

    def test_two_consecutive_unhealthy_polls_trigger_restart(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Regression test (a): the debounce must still fire on the SECOND
        # consecutive watchdog poll, namespacing notwithstanding.
        monkeypatch.setattr(fleet_control, "_port_listening", _listening({_BUILD_PORT}))
        monkeypatch.setattr(fleet_control, "_systemd_unit_available", lambda _unit: True)

        def _forbid(*_a: Any, **_kw: Any) -> Any:  # pragma: no cover - first strike
            raise AssertionError("first strike must defer")

        monkeypatch.setattr(fleet_control.subprocess, "run", _forbid)
        monkeypatch.setattr(fleet_control, "start_fleet", _forbid)

        first = fleet_control.ensure_fleet_running(source="watchdog")
        assert first["action"] == "defer"

        calls: list[list[str]] = []
        monkeypatch.setattr(
            fleet_control.subprocess,
            "run",
            lambda cmd, **_kw: (calls.append(cmd), _Proc())[1],
        )
        second = fleet_control.ensure_fleet_running(source="watchdog")

        assert second["action"] == "systemd_restart"
        assert second["unhealthy"] == ["nlt-build"]
        assert calls == [["systemctl", "--user", "restart", "tapps-mcp-fleet.service"]]

    def test_manual_ensure_between_polls_does_not_clear_pending(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Regression test (b): the pre-TAP-6053 failure. A manual `fleet
        # ensure` that happens to find the fleet reachable used to write an
        # empty set into the SAME state file the timer reads, so the next
        # automated poll started its two-strike count over and the restart was
        # starved indefinitely. The manual run now writes its own namespace.
        monkeypatch.setattr(fleet_control, "_port_listening", _listening({_BUILD_PORT}))
        monkeypatch.setattr(fleet_control, "_systemd_unit_available", lambda _unit: True)

        def _forbid(*_a: Any, **_kw: Any) -> Any:  # pragma: no cover - first strike
            raise AssertionError("first strike must defer")

        monkeypatch.setattr(fleet_control.subprocess, "run", _forbid)
        monkeypatch.setattr(fleet_control, "start_fleet", _forbid)

        assert fleet_control.ensure_fleet_running(source="watchdog")["action"] == "defer"
        assert fleet_control._read_prev_unhealthy("watchdog") == {"nlt-build"}

        # Out-of-band operator run, and this time every port answers.
        monkeypatch.setattr(fleet_control, "_port_listening", _listening(set()))
        manual = fleet_control.ensure_fleet_running(source="manual")
        assert manual["action"] == "none"
        assert manual["source"] == "manual"

        # The watchdog's pending confirmation survived it untouched.
        assert fleet_control._read_prev_unhealthy("watchdog") == {"nlt-build"}

        monkeypatch.setattr(fleet_control, "_port_listening", _listening({_BUILD_PORT}))
        calls: list[list[str]] = []
        monkeypatch.setattr(
            fleet_control.subprocess,
            "run",
            lambda cmd, **_kw: (calls.append(cmd), _Proc())[1],
        )
        second = fleet_control.ensure_fleet_running(source="watchdog")

        assert second["action"] == "systemd_restart"
        assert calls == [["systemctl", "--user", "restart", "tapps-mcp-fleet.service"]]

    def test_manual_and_watchdog_use_separate_state_files(self) -> None:
        watchdog = fleet_control._watch_state_file("watchdog")
        manual = fleet_control._watch_state_file("manual")
        assert watchdog == fleet_control.FLEET_WATCH_STATE_FILE
        assert manual != watchdog
        assert manual.name == ".watch-unhealthy-manual.json"

    def test_legacy_list_state_still_confirms(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A pending set written by a pre-TAP-6053 build is a bare JSON list.
        # It must migrate, not be silently dropped (which would cost the fleet
        # one more poll interval of downtime on the upgrade).
        fleet_control.FLEET_WATCH_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        fleet_control.FLEET_WATCH_STATE_FILE.write_text('["nlt-build"]', encoding="utf-8")

        monkeypatch.setattr(fleet_control, "_port_listening", _listening({_BUILD_PORT}))
        monkeypatch.setattr(fleet_control, "_systemd_unit_available", lambda _unit: True)
        calls: list[list[str]] = []
        monkeypatch.setattr(
            fleet_control.subprocess,
            "run",
            lambda cmd, **_kw: (calls.append(cmd), _Proc())[1],
        )

        result = fleet_control.ensure_fleet_running(source="watchdog")
        assert result["action"] == "systemd_restart"
        assert calls == [["systemctl", "--user", "restart", "tapps-mcp-fleet.service"]]


class TestUnhealthyReasonRecording:
    """Acceptance 2: the journal line carries a diagnosis, not just names."""

    @pytest.fixture(autouse=True)
    def _no_sleep(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import time

        monkeypatch.setattr(time, "sleep", lambda _s: None)

    def test_tcp_down_and_initialize_timeout_are_distinguished(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(fleet_control, "_port_listening", _listening({_BUILD_PORT}))
        monkeypatch.setattr(
            fleet_control,
            "_mcp_initialize_ok",
            lambda server_id, **_k: server_id != "nlt-memory",
        )

        reasons = fleet_control._collect_unhealthy_servers("127.0.0.1")

        assert reasons == {
            "nlt-build": "tcp_down",
            "nlt-memory": "initialize_timeout",
        }

    def test_confirmed_payload_carries_reasons_and_downtime(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            fleet_control, "FLEET_WATCH_STATE_FILE", tmp_path / ".watch-unhealthy.json"
        )
        monkeypatch.setattr(fleet_control, "FLEET_LOG_DIR", tmp_path / "logs")
        monkeypatch.setattr(fleet_control, "FLEET_PID_DIR", tmp_path / "pids")
        monkeypatch.setattr(fleet_control, "_mcp_initialize_ok", lambda *_a, **_k: True)
        monkeypatch.setattr(fleet_control, "_port_listening", _listening({_BUILD_PORT}))
        monkeypatch.setattr(fleet_control, "_systemd_unit_available", lambda _unit: True)
        monkeypatch.setattr(fleet_control.subprocess, "run", lambda *_a, **_kw: _Proc())

        fleet_control.ensure_fleet_running(source="watchdog")
        confirmed = fleet_control.ensure_fleet_running(source="watchdog")

        assert confirmed["reasons"] == {"nlt-build": "tcp_down"}
        assert confirmed["down_for_s"]["nlt-build"] >= 0.0
        assert confirmed["source"] == "watchdog"


class TestDeathEvidenceCapture:
    """Acceptance 1: detection captures what the dead process last emitted."""

    def test_log_tail_and_pid_liveness_are_captured(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(fleet_control, "FLEET_LOG_DIR", tmp_path / "logs")
        monkeypatch.setattr(fleet_control, "FLEET_PID_DIR", tmp_path / "pids")
        (tmp_path / "logs").mkdir()
        (tmp_path / "logs" / "nlt-build.log").write_text(
            "noise\n\ntapps.signal_exit signal=SIGTERM signum=15 pid=42 ppid=1 "
            "exit_status=0 uptime_s=931.4\n",
            encoding="utf-8",
        )

        evidence = fleet_control._death_evidence("nlt-build")

        assert evidence["pid"] is None
        assert evidence["pid_alive"] is False
        assert evidence["log_tail"][-1].startswith("tapps.signal_exit signal=SIGTERM")

    def test_missing_log_degrades_to_empty_tail(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(fleet_control, "FLEET_LOG_DIR", tmp_path / "logs")
        monkeypatch.setattr(fleet_control, "FLEET_PID_DIR", tmp_path / "pids")

        assert fleet_control._death_evidence("nlt-build")["log_tail"] == []


class TestSignalExitLine:
    """The line the SIGTERM handler writes to fd 2 before unwinding."""

    def test_line_names_the_signal_and_the_process(self) -> None:
        line = brain_bridge.format_signal_exit_line(15)

        assert line.startswith("tapps.signal_exit ")
        assert line.endswith("\n")
        assert "signal=SIGTERM signum=15" in line
        assert re.search(r"\bpid=\d+ ppid=\d+ exit_status=0 uptime_s=\d+\.\d\b", line)

    def test_unknown_signal_number_does_not_raise(self) -> None:
        assert "signal=UNKNOWN signum=999" in brain_bridge.format_signal_exit_line(999)


class TestWatchdogUnitPassesItsOwnSource:
    def test_installed_watch_unit_uses_source_watchdog(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Without this the timer would share the manual namespace and the
        # starvation fix would be inert.
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        fleet_control.install_systemd_user_unit()

        unit = (
            tmp_path / ".config" / "systemd" / "user" / "tapps-mcp-fleet-watch.service"
        ).read_text(encoding="utf-8")

        assert "fleet ensure --source watchdog" in unit

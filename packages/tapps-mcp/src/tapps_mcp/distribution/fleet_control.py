"""Start/stop/status for the shared HTTP MCP fleet (ADR-0024)."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

from tapps_mcp.distribution.nlt_http_fleet import (
    FLEET_ENV_FILE,
    FLEET_LOG_DIR,
    FLEET_PID_DIR,
    NLT_HTTP_FLEET_PORTS,
    fleet_server_launch_specs,
    resolve_fleet_code_root,
    resolve_fleet_host,
    sample_fleet_env_content,
)

_OPERATOR_ENV = Path.home() / ".tapps-operator.env"

# Cross-invocation watchdog state: server ids that were unreachable on the
# previous ``fleet ensure`` run. A whole-fleet restart severs every client's
# HTTP session, so we only act on servers that stay down across two
# consecutive polls -- this debounces transient host overload (a heavy
# ``uv run pytest`` / build saturating CPU makes short TCP probes time out for
# every port at once, which must not trigger a fleet-wide restart).
FLEET_WATCH_STATE_FILE = FLEET_PID_DIR.parent / ".watch-unhealthy.json"


def _read_prev_unhealthy() -> set[str]:
    try:
        data = json.loads(FLEET_WATCH_STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    if isinstance(data, list):
        return {str(item) for item in data}
    return set()


def _write_prev_unhealthy(unhealthy: set[str]) -> None:
    try:
        FLEET_WATCH_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        FLEET_WATCH_STATE_FILE.write_text(json.dumps(sorted(unhealthy)), encoding="utf-8")
    except OSError:
        pass


def ensure_fleet_env_file() -> Path:
    """Create ``~/.tapps-mcp/fleet.env`` with defaults when missing."""
    FLEET_ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not FLEET_ENV_FILE.is_file():
        FLEET_ENV_FILE.write_text(sample_fleet_env_content(), encoding="utf-8")
    return FLEET_ENV_FILE


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = os.path.expandvars(value)
    return values


def _build_fleet_process_env() -> dict[str, str]:
    ensure_fleet_env_file()
    env = os.environ.copy()
    env.update(_load_env_file(_OPERATOR_ENV))
    env.update(_load_env_file(FLEET_ENV_FILE))

    code_root = resolve_fleet_code_root()
    env["TAPPS_MCP_PROJECT_ROOT"] = str(code_root)
    env["TAPPS_MCP_HOST_PROJECT_ROOT"] = str(code_root)
    env["DOCS_MCP_PROJECT_ROOT"] = str(code_root)

    mem_token = env.get("TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN", "")
    brain_token = env.get("TAPPS_BRAIN_AUTH_TOKEN", "")
    if brain_token and (not mem_token or mem_token == "${TAPPS_BRAIN_AUTH_TOKEN}"):  # noqa: S105
        env["TAPPS_MCP_MEMORY_BRAIN_AUTH_TOKEN"] = brain_token

    if not env.get("TAPPS_MCP_CONTEXT7_API_KEY") and env.get("CONTEXT7_API_KEY"):
        env["TAPPS_MCP_CONTEXT7_API_KEY"] = env["CONTEXT7_API_KEY"]

    env.setdefault("TAPPS_MCP_MEMORY_BRAIN_HTTP_URL", "http://localhost:8080")
    env.setdefault("TAPPS_BRAIN_PROFILE", "full")
    env.setdefault("TAPPS_METRICS_STORAGE", "dual")
    return env


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _read_pid(server_id: str) -> int | None:
    pid_file = FLEET_PID_DIR / f"{server_id}.pid"
    if not pid_file.is_file():
        return None
    try:
        return int(pid_file.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def _http_reachable(server_id: str, fleet_host: str | None = None) -> bool:
    """Return ``True`` when the fleet server's TCP port accepts connections.

    Platform servers (``tapps-platform``, ``docsmcp``) return 404 on ``/`` with
    MCP at ``/mcp``; an HTTP GET probe would misread that as down (``urlopen``
    raises on 404). Match status display: TCP listen check only.

    Watchdog liveness uses :func:`_mcp_initialize_ok` in addition to TCP so a
    starved event loop (TCP up, ``/mcp`` hung) is not reported healthy.
    """
    host = fleet_host or resolve_fleet_host()
    port = NLT_HTTP_FLEET_PORTS[server_id]
    return _port_listening(host, port, timeout=1.5)


def _mcp_initialize_ok(
    server_id: str,
    fleet_host: str | None = None,
    *,
    timeout: float = 3.0,
) -> bool:
    """Return ``True`` when ``initialize`` against ``/mcp`` completes in time."""
    from tapps_mcp.distribution.fleet_smoke import probe_fleet_mcp_initialize

    result = probe_fleet_mcp_initialize(
        server_id,
        fleet_host=fleet_host,
        timeout=timeout,
    )
    return bool(result.get("ok"))


def _mcp_persistently_unresponsive(
    server_id: str,
    host: str,
    *,
    attempts: int = 3,
    backoff: float = 0.5,
    timeout: float = 3.0,
) -> bool:
    """Return ``True`` only when every MCP initialize probe fails.

    Mirrors :func:`_port_persistently_down`: a single slow probe during host
    overload must not mark the server unhealthy.
    """
    for attempt in range(attempts):
        if _mcp_initialize_ok(server_id, fleet_host=host, timeout=timeout):
            return False
        if attempt < attempts - 1:
            time.sleep(backoff)
    return True


def _collect_unhealthy_servers(host: str) -> set[str]:
    """TCP-down servers plus TCP-up servers whose ``/mcp`` handshake is hung."""
    down = {
        server_id
        for server_id, port in NLT_HTTP_FLEET_PORTS.items()
        if _port_persistently_down(host, port)
    }
    for server_id in NLT_HTTP_FLEET_PORTS:
        if server_id in down:
            continue
        if _mcp_persistently_unresponsive(server_id, host):
            down.add(server_id)
    return down


def start_fleet(*, force: bool = False) -> dict[str, Any]:
    """Start all six HTTP fleet processes."""
    FLEET_PID_DIR.mkdir(parents=True, exist_ok=True)
    FLEET_LOG_DIR.mkdir(parents=True, exist_ok=True)
    env = _build_fleet_process_env()
    host = resolve_fleet_host()
    started: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    for server_id, command, serve_args, port in fleet_server_launch_specs():
        pid = _read_pid(server_id)
        if pid is not None and _pid_alive(pid) and not force:
            skipped.append(server_id)
            continue
        if pid is not None and _pid_alive(pid) and force:
            stop_fleet(server_ids=[server_id])

        log_path = FLEET_LOG_DIR / f"{server_id}.log"
        cmd = [
            command,
            *serve_args,
            "--transport",
            "http",
            "--host",
            host,
            "--port",
            str(port),
        ]
        try:
            with log_path.open("a", encoding="utf-8") as log_handle:
                log_handle.write(f"\n--- fleet start {time.strftime('%Y-%m-%dT%H:%M:%S')} ---\n")
                log_handle.flush()
                proc = subprocess.Popen(
                    cmd,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    env=env,
                    start_new_session=True,
                )
        except OSError as exc:
            errors.append(f"{server_id}: {exc}")
            continue

        (FLEET_PID_DIR / f"{server_id}.pid").write_text(str(proc.pid), encoding="utf-8")
        started.append(server_id)

    return {
        "started": started,
        "skipped": skipped,
        "errors": errors,
        "code_root": str(resolve_fleet_code_root()),
        "host": host,
    }


def stop_fleet(*, server_ids: list[str] | None = None) -> dict[str, Any]:
    """Stop fleet processes (SIGTERM, then SIGKILL after brief wait)."""
    targets = server_ids or list(NLT_HTTP_FLEET_PORTS.keys())
    stopped: list[str] = []
    missing: list[str] = []
    for server_id in targets:
        pid_file = FLEET_PID_DIR / f"{server_id}.pid"
        pid = _read_pid(server_id)
        if pid is None or not _pid_alive(pid):
            missing.append(server_id)
            if pid_file.is_file():
                pid_file.unlink(missing_ok=True)
            continue
        os.kill(pid, signal.SIGTERM)
        for _ in range(20):
            if not _pid_alive(pid):
                break
            time.sleep(0.1)
        if _pid_alive(pid):
            os.kill(pid, signal.SIGKILL)
        pid_file.unlink(missing_ok=True)
        stopped.append(server_id)
    return {"stopped": stopped, "missing": missing}


_CANONICAL_UNIT = "tapps-mcp-fleet.service"


def _port_listening(host: str, port: int, *, timeout: float = 2.0) -> bool:
    """Return ``True`` when a TCP connection to ``host:port`` succeeds.

    A listening port means uvicorn is up and serving the MCP endpoint. This is
    deliberately *not* an HTTP GET on ``/``: the platform servers return 404
    there (MCP lives at ``/mcp``), which an HTTP probe would misread as down.
    """
    import socket

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _port_persistently_down(
    host: str, port: int, *, attempts: int = 3, backoff: float = 0.5
) -> bool:
    """Return ``True`` only when ``host:port`` fails *every* probe attempt.

    The watchdog restart severs every client's HTTP session, so a single
    transient miss (e.g. the box is briefly CPU-bound during a commit or test
    run) must not trip a full fleet restart. Re-probe with a short backoff and
    declare a port down only when it is unreachable across all attempts.
    """
    import time

    for attempt in range(attempts):
        if _port_listening(host, port):
            return False
        if attempt < attempts - 1:
            time.sleep(backoff)
    return True


def _systemd_unit_available(unit: str) -> bool:
    """Return ``True`` when the named systemd --user unit is known to systemd."""
    import shutil

    if shutil.which("systemctl") is None:
        return False
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "cat", unit],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def ensure_fleet_running() -> dict[str, Any]:
    """Restart the fleet only when it is not fully reachable (watchdog entry).

    Designed to be the ``ExecStart`` of a ``Type=oneshot`` watchdog unit. It must
    never spawn the long-lived servers into its *own* cgroup: a oneshot without
    ``RemainAfterExit`` would then reap them on exit (the ADR-0024 regression).
    When the canonical ``tapps-mcp-fleet.service`` is available we delegate to
    ``systemctl --user restart`` so the servers land in *that* unit's surviving
    cgroup; only outside systemd do we fall back to a direct start.

    Unhealthy means TCP not listening **or** TCP up but ``/mcp`` ``initialize``
    fails persistently (event-loop starvation — Cursor "Loading tools").
    """
    host = resolve_fleet_host()
    down_now = _collect_unhealthy_servers(host)

    if not down_now:
        _write_prev_unhealthy(set())
        return {"action": "none", "healthy": True, "unhealthy": []}

    # Debounce: only act on servers that were ALSO down on the previous poll.
    # A single bad poll (transient host overload) records the suspect set but
    # defers the restart, so the fleet is not torn down for every CPU blip.
    prev_down = _read_prev_unhealthy()
    _write_prev_unhealthy(down_now)
    confirmed = sorted(down_now & prev_down)
    if not confirmed:
        return {
            "action": "defer",
            "healthy": False,
            "unhealthy": sorted(down_now),
            "deferred": sorted(down_now),
        }

    unhealthy = confirmed

    if _systemd_unit_available(_CANONICAL_UNIT):
        try:
            proc = subprocess.run(
                ["systemctl", "--user", "restart", _CANONICAL_UNIT],
                capture_output=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            proc = None
        if proc is not None and proc.returncode == 0:
            return {"action": "systemd_restart", "healthy": False, "unhealthy": unhealthy}

    start_fleet(force=True)
    return {"action": "direct_start", "healthy": False, "unhealthy": unhealthy}


def fleet_any_running() -> bool:
    """Return True when at least one supervised fleet server has a live PID."""
    return fleet_status()["running"] > 0


def _wait_fleet_ports_listening(*, timeout: float = 30.0, poll: float = 0.5) -> list[str]:
    """Block until every fleet port accepts TCP, up to *timeout* seconds.

    Freshly spawned ``serve`` processes need a moment to import and bind;
    smoking them immediately after ``start_fleet`` reads as connection
    refused. Returns the server ids still not listening at the deadline.
    """
    host = resolve_fleet_host()
    deadline = time.monotonic() + timeout
    pending = dict(NLT_HTTP_FLEET_PORTS)
    while pending and time.monotonic() < deadline:
        for server_id, port in list(pending.items()):
            if _port_listening(host, port, timeout=1.0):
                del pending[server_id]
        if pending:
            time.sleep(poll)
    return sorted(pending)


def restart_fleet_with_smoke(*, project_root: Path | None = None) -> dict[str, Any]:
    """Stop, start, wait for readiness, then MCP-smoke every fleet server."""
    from tapps_mcp.distribution.fleet_smoke import smoke_test_fleet

    stop_fleet()
    started = start_fleet(force=True)
    not_ready = _wait_fleet_ports_listening()
    smoke = smoke_test_fleet(project_root=project_root)
    return {
        "ok": bool(smoke.get("ok")) and not not_ready,
        "started": started.get("started", []),
        "errors": started.get("errors", []),
        "not_ready": not_ready,
        "smoke": smoke,
    }


def fleet_status() -> dict[str, Any]:
    """Return running/reachable status for each fleet server."""
    host = resolve_fleet_host()
    servers: dict[str, dict[str, Any]] = {}
    for server_id, _, _, port in fleet_server_launch_specs():
        pid = _read_pid(server_id)
        alive = pid is not None and _pid_alive(pid)
        reachable = _http_reachable(server_id, fleet_host=host)
        servers[server_id] = {
            "pid": pid,
            "alive": alive,
            "reachable": reachable,
            "url": f"http://{host}:{port}/mcp",
        }
    running = sum(1 for row in servers.values() if row["alive"])
    return {
        "host": host,
        "code_root": str(resolve_fleet_code_root()),
        "running": running,
        "total": len(servers),
        "servers": servers,
        "env_file": str(FLEET_ENV_FILE),
        "pid_dir": str(FLEET_PID_DIR),
    }


def install_systemd_user_unit(*, script_path: Path | None = None) -> list[Path]:
    """Write the systemd user units that supervise the shared HTTP fleet.

    Single source of truth for all fleet units (ADR-0024). Three files are
    written:

    * ``tapps-mcp-fleet.service`` — ``Type=oneshot`` + ``RemainAfterExit=yes``.
      ``RemainAfterExit`` keeps the unit's cgroup alive so the six servers
      spawned by ``fleet start`` are *not* reaped when the start command exits.
    * ``tapps-mcp-fleet-watch.service`` — health-aware watchdog. It runs
      ``fleet ensure`` which restarts the canonical service when unhealthy, so
      it never owns the long-lived servers in its own cgroup. A hand-rolled
      watchdog that called ``fleet start`` directly (oneshot, no
      ``RemainAfterExit``) reaped the fleet every 60s — this generator replaces
      that footgun.
    * ``tapps-mcp-fleet-watch.timer`` — polls every 60s.
    """
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    tapps_bin = _resolve_tapps_mcp_bin()

    service_path = unit_dir / "tapps-mcp-fleet.service"
    service_path.write_text(
        "\n".join(
            [
                "[Unit]",
                "Description=TappsMCP shared HTTP MCP fleet (six NLT servers)",
                "After=network-online.target",
                "Wants=network-online.target",
                "",
                "[Service]",
                "Type=oneshot",
                "RemainAfterExit=yes",
                f"ExecStart={tapps_bin} fleet start",
                f"ExecStop={tapps_bin} fleet stop",
                "Environment=PYTHONUNBUFFERED=1",
                "",
                "[Install]",
                "WantedBy=default.target",
                "",
            ]
        ),
        encoding="utf-8",
    )

    watch_service_path = unit_dir / "tapps-mcp-fleet-watch.service"
    watch_service_path.write_text(
        "\n".join(
            [
                "[Unit]",
                "Description=Ensure TappsMCP HTTP fleet is running (watchdog)",
                "After=network-online.target",
                "",
                "[Service]",
                "Type=oneshot",
                # No RemainAfterExit by design: `fleet ensure` does not spawn the
                # servers into this unit's cgroup, so oneshot teardown is safe.
                f"ExecStart={tapps_bin} fleet ensure",
                "Environment=PYTHONUNBUFFERED=1",
                "",
            ]
        ),
        encoding="utf-8",
    )

    watch_timer_path = unit_dir / "tapps-mcp-fleet-watch.timer"
    watch_timer_path.write_text(
        "\n".join(
            [
                "[Unit]",
                "Description=Poll TappsMCP HTTP fleet every 60s and start if down",
                "",
                "[Timer]",
                "OnBootSec=45",
                "OnUnitActiveSec=60",
                "Persistent=true",
                "",
                "[Install]",
                "WantedBy=timers.target",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return [service_path, watch_service_path, watch_timer_path]


def _resolve_tapps_mcp_bin() -> str:
    from tapps_mcp.distribution.blue_green import CURRENT_LINK

    current = CURRENT_LINK / "bin" / "tapps-mcp"
    if current.is_file():
        return str(current)
    import shutil

    found = shutil.which("tapps-mcp")
    if found:
        return found
    return "tapps-mcp"

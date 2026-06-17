"""Start/stop/status for the shared HTTP MCP fleet (ADR-0024)."""

from __future__ import annotations

import os
import signal
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from tapps_mcp.distribution.nlt_http_fleet import (
    DEFAULT_FLEET_CODE_ROOT_ENV,
    DEFAULT_FLEET_HOST_ENV,
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
    if brain_token and (not mem_token or mem_token == "${TAPPS_BRAIN_AUTH_TOKEN}"):
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
    host = fleet_host or resolve_fleet_host()
    port = NLT_HTTP_FLEET_PORTS[server_id]
    url = f"http://{host}:{port}/"
    try:
        with urllib.request.urlopen(url, timeout=1.5) as resp:  # noqa: S310
            return 200 <= resp.status < 500
    except (urllib.error.URLError, TimeoutError, ValueError):
        return False


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
                log_handle.write(
                    f"\n--- fleet start {time.strftime('%Y-%m-%dT%H:%M:%S')} ---\n"
                )
                log_handle.flush()
                proc = subprocess.Popen(  # noqa: S603
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


def install_systemd_user_unit(*, script_path: Path | None = None) -> Path:
    """Write a systemd user unit that wraps ``tapps-mcp fleet start/stop``."""
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    tapps_bin = _resolve_tapps_mcp_bin()
    unit_path = unit_dir / "tapps-mcp-fleet.service"
    unit_path.write_text(
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
    return unit_path


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

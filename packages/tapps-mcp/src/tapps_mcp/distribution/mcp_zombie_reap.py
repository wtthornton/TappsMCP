"""Reap orphaned MCP serve processes (deploy-local only).

Orphan = ``serve --profile nlt-*`` or global-install ``serve`` whose parent PID
is dead. Safe with multiple Cursor windows — never kills live children.

See docs/adr/0005-mcp-server-zombie-cleanup-hook-on-session-start.md.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
from typing import Any

_SERVE_CMD = re.compile(
    r"serve --profile nlt-|/(tapps-mcp|docsmcp|tapps-platform)( |$).*serve"
)


def _parent_alive(ppid: int) -> bool:
    if ppid <= 1:
        return False
    try:
        os.kill(ppid, 0)
    except OSError:
        return False
    else:
        return True


def _iter_mcp_serve_processes() -> list[tuple[int, int, str]]:
    """Return ``(pid, ppid, cmd)`` for every MCP ``serve`` process."""
    try:
        proc = subprocess.run(
            ["ps", "-eo", "pid=", "ppid=", "cmd="],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    if proc.returncode != 0:
        return []

    rows: list[tuple[int, int, str]] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[0])
            ppid = int(parts[1])
        except ValueError:
            continue
        cmd = parts[2]
        if not _SERVE_CMD.search(cmd):
            continue
        rows.append((pid, ppid, cmd))
    return rows


def find_orphan_mcp_serve_pids() -> list[int]:
    """Return PIDs of MCP serve processes whose parent is dead."""
    fleet_pids = _load_fleet_supervised_pids()
    orphans: list[int] = []
    for pid, ppid, cmd in _iter_mcp_serve_processes():
        if pid in fleet_pids or _is_fleet_http_serve(cmd):
            continue
        if ppid == 1 or not _parent_alive(ppid):
            orphans.append(pid)
    return sorted(orphans)


def _load_fleet_supervised_pids() -> set[int]:
    from tapps_mcp.distribution.nlt_http_fleet import read_fleet_supervised_pids

    return read_fleet_supervised_pids()


def _is_fleet_http_serve(cmd: str) -> bool:
    from tapps_mcp.distribution.nlt_http_fleet import is_fleet_http_serve_command

    return is_fleet_http_serve_command(cmd)


def find_live_mcp_serve_pids() -> list[int]:
    """Return PIDs of MCP serve processes still attached to a live parent (e.g. Cursor).

    In-place ``uv tool install --reinstall`` replaces the global tool venv and
    breaks these processes — fleet/CLI reinstall must use blue/green instead.
    """
    live: list[int] = []
    for pid, ppid, _cmd in _iter_mcp_serve_processes():
        if ppid > 1 and _parent_alive(ppid):
            live.append(pid)
    return sorted(live)


def reap_orphan_mcp_serves(*, dry_run: bool = False) -> dict[str, Any]:
    """Kill orphan MCP serve PIDs. Returns summary dict for deploy reports."""
    pids = find_orphan_mcp_serve_pids()
    reaped: list[int] = []
    errors: list[str] = []
    for pid in pids:
        if dry_run:
            reaped.append(pid)
            continue
        try:
            os.kill(pid, signal.SIGTERM)
            reaped.append(pid)
        except OSError as exc:
            errors.append(f"{pid}: {exc}")
    return {
        "ok": not errors,
        "dry_run": dry_run,
        "found": pids,
        "reaped": reaped,
        "errors": errors,
    }


def main() -> None:
    result = reap_orphan_mcp_serves()
    if result["reaped"]:
        print(f"[TappsMCP] Reaped orphaned MCP serve PIDs: {result['reaped']}", flush=True)
    if result["errors"]:
        for err in result["errors"]:
            print(f"[TappsMCP] reap error: {err}", flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()

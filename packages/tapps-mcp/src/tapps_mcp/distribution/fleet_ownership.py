"""Who actually owns a fleet port, and which release they are running.

`fleet start` records a pid per server, but that record is only a claim. When
a server from a previous release survives a deploy, it keeps the port; the
replacement cannot bind, dies, and leaves its pidfile behind. Every check
that asks "is the port answering?" then reports healthy while the old release
serves every request (TAP-5630).

These helpers answer the questions the pidfile cannot: which process is bound
to the port right now, and what release is it running.
"""

from __future__ import annotations

import re
from pathlib import Path

from tapps_mcp.distribution.nlt_http_fleet import is_fleet_http_serve_command

_PROC = Path("/proc")
_RELEASE_RE = re.compile(r"releases/([^/\s]+)")


def read_process_cmdline(pid: int, *, proc_root: Path = _PROC) -> str:
    """Return *pid*'s command line as a space-joined string, or "" if gone."""
    try:
        raw = (proc_root / str(pid) / "cmdline").read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\0", b" ").decode("utf-8", errors="replace").strip()


def process_release(pid: int, *, proc_root: Path = _PROC) -> str | None:
    """Return the release directory name *pid* is running from, if any.

    ``~/.tapps-mcp/releases/3.12.65-6696aaf3/bin/python`` yields
    ``3.12.65-6696aaf3``. Returns ``None`` for a process outside a release
    tree (an editable checkout, say) or one that has exited.
    """
    match = _RELEASE_RE.search(read_process_cmdline(pid, proc_root=proc_root))
    return match.group(1) if match else None


def _serves_port(cmdline: str, port: int) -> bool:
    """True when *cmdline* is a fleet HTTP serve bound to *port*."""
    if not is_fleet_http_serve_command(cmdline):
        return False
    return f"--port {port}" in cmdline or f"--port={port}" in cmdline


def _pidfile_claimed_pids(pid_dir: Path) -> set[int]:
    """Pids the fleet pidfiles currently claim as the live set."""
    claimed: set[int] = set()
    if not pid_dir.is_dir():
        return claimed
    for pidfile in pid_dir.glob("*.pid"):
        try:
            claimed.add(int(pidfile.read_text(encoding="utf-8").strip()))
        except (OSError, ValueError):
            continue
    return claimed


def find_superseded_fleet_pids(
    current_release: str | None,
    *,
    pid_dir: Path,
    proc_root: Path = _PROC,
) -> list[int]:
    """Fleet HTTP servers stranded on a release that is no longer ``current``.

    ADR-0024 forbids reaping the shared HTTP fleet by transport alone, because
    the servers are spawned ``start_new_session=True`` under a ``Type=oneshot``
    parent that exits — they are permanently ppid=1 and would look like orphans
    to any parent-based reaper. This is the narrower question that *is* safe to
    act on: which fleet processes belong to a superseded release **and** are not
    claimed by any pidfile.

    Both conditions are required. Release alone would kill a server mid-deploy
    that still owns its port; pidfile-absence alone would kill a healthy server
    whose bookkeeping was lost. Requiring both leaves exactly the strays.

    Returns an empty list when *current_release* is unknown — never guess and
    kill on incomplete information.
    """
    if not current_release or not proc_root.is_dir():
        return []
    claimed = _pidfile_claimed_pids(pid_dir)
    stranded: list[int] = []
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid in claimed:
            continue
        cmdline = read_process_cmdline(pid, proc_root=proc_root)
        if not is_fleet_http_serve_command(cmdline):
            continue
        match = _RELEASE_RE.search(cmdline)
        if match is None or match.group(1) == current_release:
            continue
        stranded.append(pid)
    return sorted(stranded)


def find_port_owner(port: int, *, proc_root: Path = _PROC) -> int | None:
    """Return the pid of the fleet serve process bound to *port*.

    Scans ``/proc`` rather than the pidfiles, so it finds a server the current
    bookkeeping has lost track of. Only matches processes whose command line is
    a fleet HTTP ``serve`` for this exact port — never an unrelated listener,
    which must not be killed on the fleet's behalf.
    """
    if not proc_root.is_dir():
        return None
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if _serves_port(read_process_cmdline(pid, proc_root=proc_root), port):
            return pid
    return None

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

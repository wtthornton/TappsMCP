"""Process inspection helpers for blue/green deploy quiescence and GC."""

from __future__ import annotations

from pathlib import Path


def proc_cmdline(entry: Path) -> str:
    try:
        raw = (entry / "cmdline").read_bytes()
    except OSError:
        return ""
    if not raw:
        return ""
    return raw.replace(b"\x00", b" ").decode("utf-8", errors="replace")


def pytest_blockers(checkout: Path) -> list[str]:
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return []
    checkout_s = str(checkout)
    packages_s = f"{checkout_s}/packages"
    blockers: list[str] = []
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        cmd = proc_cmdline(entry)
        if "pytest" in cmd and (checkout_s in cmd or packages_s in cmd):
            blockers.append(f"pytest pid={entry.name}")
    return blockers


def proc_references_path(link: Path, target: Path) -> bool:
    try:
        return link.is_symlink() and target in link.resolve().parents
    except OSError:
        return False


def _cmdline_references_path(cmd: str, target: Path) -> bool:
    """True when *cmd* (a process's argv, space-joined) references *target*.

    A literal substring match catches argv carrying the release path
    directly (e.g. argv[0] = ``<release>/bin/python``). It is blind to a
    reference reached only through the ``current`` symlink (e.g. argv[1] =
    ``~/.tapps-mcp/current/bin/tapps-mcp``): the text never contains the
    release path, only the symlink's. So each absolute-path-looking token
    is also resolved and checked against *target* directly -- this is what
    catches the symlink-only case (TAP-6893).
    """
    target_s = str(target)
    if target_s in cmd:
        return True
    for token in cmd.split():
        if not token.startswith("/"):
            continue
        try:
            resolved = Path(token).resolve()
        except OSError:
            continue
        if resolved == target or target in resolved.parents:
            return True
    return False


def pids_referencing(path: Path) -> set[int]:
    """Return PIDs whose exe, cwd, or cmdline reference *path* (best-effort Linux).

    A blue/green release can be held without ever showing up in ``exe`` or
    ``cwd``: the shared uv-managed CPython is ``exe``, the operator's home
    dir is ``cwd``, and the release directory is only visible in argv (the
    server execs ``<release>/bin/python`` with that path as argv[0]) --
    verified live via ``readlink /proc/<pid>/exe`` / ``cwd`` against running
    MCP servers, TAP-6893. A reference reached only through the ``current``
    symlink (argv carrying ``~/.tapps-mcp/current/...`` rather than the
    release path itself) is resolved before comparing, so it is not missed
    -- this bites hardest right after a flip, when a process still executing
    out of the just-superseded release's only surviving reference is
    ``current``, now pointing at the new one.

    Cost is bounded per pid, not by an unbounded scan of every fd or the
    full ``maps`` of every process on the host: at most 3 ``/proc`` reads
    per pid (``exe``, ``cwd``, ``cmdline`` -- the last already paid for by
    :func:`pytest_blockers`), plus one ``resolve()`` per whitespace-split
    argv token, bounded by that process's own argv length (these CLIs pass
    well under 20 tokens).
    """
    refs: set[int] = set()
    target = path.resolve()
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return refs
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if any(proc_references_path(entry / attr, target) for attr in ("exe", "cwd")):
            refs.add(pid)
            continue
        if _cmdline_references_path(proc_cmdline(entry), target):
            refs.add(pid)
    return refs

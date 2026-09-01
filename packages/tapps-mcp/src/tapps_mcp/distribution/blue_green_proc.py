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


def pids_referencing(path: Path) -> set[int]:
    """Return PIDs whose exe, cwd, or cmdline reference *path* (best-effort Linux).

    A blue/green release can be held without ever showing up in ``exe`` or
    ``cwd``: the shared uv-managed CPython is ``exe``, the operator's home
    dir is ``cwd``, and the release directory is only visible in argv (the
    server execs ``<release>/bin/python`` with that path as argv[0]) --
    verified live via ``readlink /proc/<pid>/exe`` / ``cwd`` against running
    MCP servers, TAP-6893. Checking ``cmdline`` is a single bounded read per
    process, already paid for by :func:`pytest_blockers`; scanning every fd
    or the full ``maps`` of every process on the host would be unbounded and
    is deliberately avoided here.
    """
    refs: set[int] = set()
    target = path.resolve()
    target_s = str(target)
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
        if target_s in proc_cmdline(entry):
            refs.add(pid)
    return refs

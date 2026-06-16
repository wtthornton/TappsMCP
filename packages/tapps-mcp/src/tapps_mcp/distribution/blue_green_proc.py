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
    """Return PIDs whose exe or cwd lives under *path* (best-effort Linux)."""
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
    return refs

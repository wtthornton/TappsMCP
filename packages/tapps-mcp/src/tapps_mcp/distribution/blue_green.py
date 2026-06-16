"""Blue/green deploy for the dev-monorepo shared MCP CLI install.

Builds immutable versioned release venvs under ``~/.tapps-mcp/releases/`` and
atomically flips ``~/.tapps-mcp/current``. Running MCP servers stay pinned to
their release dir (inode-held); only new launches pick up the flipped ``current``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import filelock
import structlog

from tapps_mcp.distribution.blue_green_proc import pids_referencing, pytest_blockers

logger = structlog.get_logger(__name__)

TAPPS_MCP_HOME = Path.home() / ".tapps-mcp"
RELEASES_DIR = TAPPS_MCP_HOME / "releases"
CURRENT_LINK = TAPPS_MCP_HOME / "current"
DEPLOY_LOCK = TAPPS_MCP_HOME / ".deploy.lock"
DEFAULT_KEEP_RELEASES = 3
_REQUIRED_BINARIES = ("tapps-mcp", "tapps-platform", "docsmcp")


@dataclass(frozen=True)
class ReleaseRef:
    """Pointer to one immutable release directory."""

    version: str
    short_sha: str
    path: Path

    @property
    def name(self) -> str:
        return f"{self.version}-{self.short_sha}"


def tapps_mcp_home() -> Path:
    return TAPPS_MCP_HOME


def current_release_path() -> Path | None:
    """Return the resolved release dir when ``current`` symlink exists."""
    if not CURRENT_LINK.is_symlink() and not CURRENT_LINK.is_dir():
        return None
    try:
        resolved = CURRENT_LINK.resolve()
    except OSError:
        return None
    return resolved if resolved.is_dir() else None


def blue_green_enabled() -> bool:
    """Return True when blue/green ``current`` launches are explicitly opted in.

    Default is **off** (global ``uv tool install`` shims). Set
    ``TAPPS_MCP_USE_BLUE_GREEN=1`` for ``deploy-local`` / zero-downtime dev deploys.
    """
    raw = os.environ.get("TAPPS_MCP_USE_BLUE_GREEN", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def resolve_blue_green_binary(command: str) -> str | None:
    """Return ``~/.tapps-mcp/current/bin/<command>`` when enabled and present."""
    if not blue_green_enabled():
        return None
    candidate = CURRENT_LINK / "bin" / command
    if candidate.is_file():
        return str(candidate.resolve())
    return None


def _read_package_version(checkout: Path) -> str:
    import tomllib

    pyproject = checkout / "packages" / "tapps-mcp" / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    version = data.get("project", {}).get("version")
    if not isinstance(version, str) or not version:
        msg = f"missing project.version in {pyproject}"
        raise ValueError(msg)
    return version


def _read_short_sha(checkout: Path) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=checkout,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        msg = f"git rev-parse failed in {checkout}: {(proc.stderr or proc.stdout).strip()}"
        raise RuntimeError(msg)
    return proc.stdout.strip()


def _release_ref(checkout: Path) -> ReleaseRef:
    version = _read_package_version(checkout)
    short_sha = _read_short_sha(checkout)
    return ReleaseRef(version=version, short_sha=short_sha, path=RELEASES_DIR / f"{version}-{short_sha}")


def _run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    logger.info("blue_green.run", cmd=cmd, cwd=str(cwd) if cwd else None)
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def build_release(checkout: Path, release: ReleaseRef, *, force: bool = False) -> dict[str, Any]:
    """Create an isolated venv release from a monorepo checkout."""
    checkout = checkout.resolve()
    manifest_path = release.path / "release.json"
    if release.path.is_dir() and manifest_path.is_file() and not force:
        return {"ok": True, "skipped": True, "release": release.name, "path": str(release.path)}

    if release.path.exists():
        shutil.rmtree(release.path)

    RELEASES_DIR.mkdir(parents=True, exist_ok=True)
    proc = _run(["uv", "venv", str(release.path), "--python", sys.executable], cwd=checkout)
    if proc.returncode != 0:
        return {
            "ok": False,
            "release": release.name,
            "step": "uv venv",
            "output": (proc.stdout or proc.stderr or "").strip()[-1000:],
        }

    python = release.path / "bin" / "python"
    pkg_specs = [
        str(checkout / "packages" / "tapps-core"),
        str(checkout / "packages" / "docs-mcp"),
        str(checkout / "packages" / "tapps-mcp"),
    ]
    proc = _run(
        ["uv", "pip", "install", "--python", str(python), *pkg_specs],
        cwd=checkout,
        timeout=900,
    )
    if proc.returncode != 0:
        shutil.rmtree(release.path, ignore_errors=True)
        return {
            "ok": False,
            "release": release.name,
            "step": "uv pip install",
            "output": (proc.stdout or proc.stderr or "").strip()[-1000:],
        }

    manifest = {
        "version": release.version,
        "short_sha": release.short_sha,
        "built_at": datetime.now(tz=UTC).isoformat(),
        "checkout": str(checkout),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "skipped": False, "release": release.name, "path": str(release.path)}


def smoke_test_release(release: ReleaseRef, *, project_root: Path | None = None) -> dict[str, Any]:
    """Verify required binaries exist and report their versions."""
    base = _smoke_required_binaries(release)
    if not base.get("ok"):
        return base
    versions = base["versions"]
    if project_root is None:
        return {"ok": True, "versions": versions}

    tapps_mcp = release.path / "bin" / "tapps-mcp"
    proc = _run([str(tapps_mcp), "doctor", "--quick"], cwd=project_root, timeout=120)
    if proc.returncode != 0:
        return {
            "ok": False,
            "failures": ["doctor --quick failed"],
            "versions": versions,
            "output": (proc.stdout or proc.stderr or "").strip()[-1000:],
        }
    return {"ok": True, "versions": versions}


def flip_current(release: ReleaseRef) -> dict[str, Any]:
    """Atomically point ``~/.tapps-mcp/current`` at *release*."""
    TAPPS_MCP_HOME.mkdir(parents=True, exist_ok=True)
    temp_link = TAPPS_MCP_HOME / f".current-flip-{int(time.time() * 1000)}.tmp"
    if temp_link.exists() or temp_link.is_symlink():
        temp_link.unlink(missing_ok=True)
    temp_link.symlink_to(release.path, target_is_directory=True)
    temp_link.replace(CURRENT_LINK)
    resolved = current_release_path()
    if resolved != release.path.resolve():
        return {"ok": False, "error": "current symlink did not resolve to release"}
    return {"ok": True, "current": str(CURRENT_LINK), "release": release.name}


def _release_dirs() -> list[Path]:
    if not RELEASES_DIR.is_dir():
        return []
    return sorted(
        (p for p in RELEASES_DIR.iterdir() if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def _binary_version(exe: Path) -> str | None:
    proc = _run([str(exe), "--version"], timeout=30)
    if proc.returncode != 0 or not (proc.stdout or proc.stderr).strip():
        return None
    return (proc.stdout or proc.stderr).strip().split()[-1]


def _smoke_required_binaries(release: ReleaseRef) -> dict[str, Any]:
    bin_dir = release.path / "bin"
    failures: list[str] = []
    versions: dict[str, str] = {}
    for binary in _REQUIRED_BINARIES:
        exe = bin_dir / binary
        if not exe.is_file():
            failures.append(f"missing {binary}")
            continue
        version = _binary_version(exe)
        if version is None:
            failures.append(f"{binary} --version failed")
            continue
        versions[binary] = version
    if failures:
        return {"ok": False, "failures": failures, "versions": versions}
    return {"ok": True, "versions": versions}


def _deploy_under_lock(
    checkout: Path,
    release: ReleaseRef,
    report: dict[str, Any],
    *,
    force_build: bool,
    keep_releases: int,
    run_doctor_smoke: bool,
) -> dict[str, Any]:
    build = build_release(checkout, release, force=force_build)
    report["build"] = build
    if not build.get("ok"):
        report["ok"] = False
        return report

    smoke = smoke_test_release(release, project_root=None)
    report["smoke_test"] = smoke
    if not smoke.get("ok"):
        report["ok"] = False
        return report

    from tapps_mcp.distribution.mcp_zombie_reap import reap_orphan_mcp_serves

    zombie_reap = reap_orphan_mcp_serves()
    report["mcp_zombie_reap"] = zombie_reap
    if not zombie_reap.get("ok"):
        report["ok"] = False
        return report

    flip = flip_current(release)
    report["flip"] = flip
    if not flip.get("ok"):
        report["ok"] = False
        return report

    if run_doctor_smoke:
        post_flip = smoke_test_release(release, project_root=checkout)
        report["post_flip_smoke"] = post_flip
        if not post_flip.get("ok"):
            report["ok"] = False
            return report

    report["gc"] = gc_releases(keep=keep_releases, protect=release.path)
    report["ok"] = True
    report["current"] = str(CURRENT_LINK)
    try:
        from tapps_mcp.distribution.setup_generator import (
            is_tapps_mcp_dev_monorepo,
            regenerate_cursor_nlt_wrappers,
        )

        if is_tapps_mcp_dev_monorepo(checkout):
            wrappers = regenerate_cursor_nlt_wrappers(checkout)
            report["cursor_wrappers"] = {"ok": True, "written": wrappers}
    except Exception as exc:
        report["cursor_wrappers"] = {"ok": False, "error": str(exc)}
    return report


def gc_releases(*, keep: int = DEFAULT_KEEP_RELEASES, protect: Path | None = None) -> dict[str, Any]:
    """Delete old release dirs not referenced by live processes."""
    current = current_release_path()
    protected = {current.resolve()} if current is not None else set()
    if protect is not None:
        protected.add(protect.resolve())

    dirs = _release_dirs()
    kept: list[str] = []
    deleted: list[str] = []
    skipped: list[str] = []

    for idx, release_dir in enumerate(dirs):
        resolved = release_dir.resolve()
        if resolved in protected or idx < keep:
            kept.append(release_dir.name)
            continue
        if pids_referencing(resolved):
            skipped.append(release_dir.name)
            continue
        shutil.rmtree(release_dir, ignore_errors=True)
        deleted.append(release_dir.name)

    return {"ok": True, "kept": kept, "deleted": deleted, "skipped_in_use": skipped}


@contextmanager
def deploy_lock() -> Iterator[None]:
    """Serialize deploys via ``~/.tapps-mcp/.deploy.lock``."""
    TAPPS_MCP_HOME.mkdir(parents=True, exist_ok=True)
    with filelock.FileLock(str(DEPLOY_LOCK)):
        yield


def is_deploy_lock_held() -> bool:
    """Return True when another process holds the deploy lock."""
    if not DEPLOY_LOCK.exists():
        return False
    probe = filelock.FileLock(str(DEPLOY_LOCK), timeout=0)
    try:
        probe.acquire(timeout=0)
        probe.release()
        return False
    except filelock.Timeout:
        return True


def quiescence_gate(checkout: Path) -> dict[str, Any]:
    """Refuse deploy while workspace test churn is active."""
    blockers = pytest_blockers(checkout.resolve())
    if blockers:
        return {"ok": False, "blockers": blockers}
    return {"ok": True}


def deploy_blue_green(
    checkout: Path,
    *,
    skip_gate: bool = False,
    dry_run: bool = False,
    force_build: bool = False,
    keep_releases: int = DEFAULT_KEEP_RELEASES,
    run_doctor_smoke: bool = True,
) -> dict[str, Any]:
    """Build, smoke-test, flip ``current``, and GC old releases."""
    checkout = checkout.resolve()
    release = _release_ref(checkout)
    report: dict[str, Any] = {
        "release": release.name,
        "checkout": str(checkout),
        "dry_run": dry_run,
    }

    if not skip_gate:
        gate = quiescence_gate(checkout)
        report["quiescence_gate"] = gate
        if not gate.get("ok"):
            report["ok"] = False
            return report

    if dry_run:
        report["ok"] = True
        report["planned"] = {
            "build": str(release.path),
            "flip": str(CURRENT_LINK),
            "keep_releases": keep_releases,
        }
        return report

    with deploy_lock():
        return _deploy_under_lock(
            checkout,
            release,
            report,
            force_build=force_build,
            keep_releases=keep_releases,
            run_doctor_smoke=run_doctor_smoke,
        )


def blue_green_status() -> dict[str, Any]:
    """Summarize the blue/green layout for doctor/diagnostics."""
    current = current_release_path()
    releases = [p.name for p in _release_dirs()]
    manifest: dict[str, Any] | None = None
    if current is not None:
        manifest_path = current / "release.json"
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                manifest = None
    return {
        "home": str(TAPPS_MCP_HOME),
        "current": str(current) if current else None,
        "releases": releases,
        "manifest": manifest,
        "deploy_lock_held": is_deploy_lock_held(),
    }

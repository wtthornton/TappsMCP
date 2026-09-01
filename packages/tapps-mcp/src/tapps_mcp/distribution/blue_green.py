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
from collections.abc import Iterator, Mapping
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
    """Return True when blue/green ``current`` should be preferred for CLI probes.

    ADR-0023: shell wrappers always probe ``~/.tapps-mcp/current`` at runtime.
    Python drift/resolve match that when the layout exists, unless the operator
    explicitly disables with ``TAPPS_MCP_USE_BLUE_GREEN=0`` (or false/off/no).
    Explicit ``=1``/true/on forces on even before the first deploy creates
    ``current``.
    """
    raw = os.environ.get("TAPPS_MCP_USE_BLUE_GREEN", "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    return (CURRENT_LINK / "bin").is_dir()


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
    return ReleaseRef(
        version=version, short_sha=short_sha, path=RELEASES_DIR / f"{version}-{short_sha}"
    )


def _run(
    cmd: list[str], *, cwd: Path | None = None, timeout: int = 600
) -> subprocess.CompletedProcess[str]:
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
    # Include the treesitter extra so the release env parses TS/Go/Rust with
    # tree-sitter like the dev venv. Without it the call-graph fingerprint
    # (which folds in the tree-sitter-typescript version, TAP-4537) never
    # matches across envs and doctor reports the index as permanently stale.
    pkg_specs = [
        str(checkout / "packages" / "tapps-core"),
        f"{checkout / 'packages' / 'docs-mcp'}[treesitter]",
        f"{checkout / 'packages' / 'tapps-mcp'}[treesitter]",
    ]
    # Force the CPU torch wheels. tapps-brain depends on sentence-transformers
    # unconditionally, which drags in torch and ~4.5 GB of CUDA wheels that no
    # release env can use on a CPU host. --torch-backend=cpu resolves the whole
    # PyTorch ecosystem (torch, triton, nvidia-*) against the CPU index instead.
    # See docs/handoff/BRAIN-sentence-transformers-optional.md for the upstream
    # fix that would remove the dependency entirely.
    proc = _run(
        ["uv", "pip", "install", "--python", str(python), "--torch-backend=cpu", *pkg_specs],
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


def _reap_superseded_then_gc(
    release: ReleaseRef, previous_release: Path | None, keep_releases: int
) -> dict[str, Any]:
    """Reap fleet servers stranded on the superseded release, then GC.

    Servers stranded on the release we just superseded hold memory and brain
    connections for nothing, and would keep a GC'd release dir alive. Must
    run before GC so nothing is executing out of a directory about to be
    deleted.

    The reap touches pidfiles, /proc, and signal delivery -- any of which
    can fail in ways this call site cannot enumerate in advance (a pidfile
    written by a different tapps-mcp version, a race on process exit, a
    permissions quirk). Broad ``except Exception`` is kept deliberately: the
    point of this comment is that narrowing it to "the exceptions we
    thought of" would silently let an unanticipated one fall through and
    reach gc_releases anyway, which is precisely the defect being fixed
    (TAP-6894). What changed is that failure now *gates* GC instead of being
    swallowed and ignored.
    """
    from tapps_mcp.distribution.fleet_control import reap_superseded_fleet

    try:
        superseded_reap = reap_superseded_fleet()
    except Exception as exc:  # gate GC below instead of narrowing, see docstring above
        return {
            "superseded_reap": {"ok": False, "error": str(exc)},
            "gc": {
                "ok": False,
                "skipped": True,
                "reason": "superseded_reap raised; GC blocked until reap succeeds",
            },
        }

    protect_extra: dict[Path, str] | None = None
    if previous_release is not None and previous_release.resolve() != release.path.resolve():
        protect_extra = {previous_release: "previous"}
    gc = gc_releases(keep=keep_releases, protect=release.path, protect_extra=protect_extra)
    return {"superseded_reap": superseded_reap, "gc": gc}


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

    # Captured before the flip: this is the rollback target an operator would
    # reach for. Once flip_current runs, current_release_path() resolves to
    # the *new* release, so this is the only chance to know what "outgoing"
    # means (TAP-6895).
    previous_release = current_release_path()

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

    from tapps_mcp.distribution.fleet_control import fleet_any_running, restart_fleet_with_smoke

    if fleet_any_running():
        fleet_smoke = restart_fleet_with_smoke(project_root=checkout)
        report["fleet_restart_smoke"] = fleet_smoke
        if not fleet_smoke.get("ok"):
            report["ok"] = False
            return report

    report.update(_reap_superseded_then_gc(release, previous_release, keep_releases))
    report["ok"] = True
    report["current"] = str(CURRENT_LINK)
    try:
        from tapps_mcp.distribution.setup_generator import (
            is_tapps_mcp_dev_monorepo,
            regenerate_nlt_stdio_wrappers,
        )

        if is_tapps_mcp_dev_monorepo(checkout):
            wrappers = regenerate_nlt_stdio_wrappers(checkout)
            report["stdio_wrappers"] = {"ok": True, "written": wrappers}
            # Backward-compatible key for older consumers of the deploy report.
            report["cursor_wrappers"] = report["stdio_wrappers"]
    except Exception as exc:
        report["stdio_wrappers"] = {"ok": False, "error": str(exc)}
        report["cursor_wrappers"] = report["stdio_wrappers"]
    return report


def _resolve_protected_reasons(
    *,
    protect: Path | None,
    protect_extra: Mapping[Path, str] | None,
) -> dict[Path, str]:
    """Build the {resolved_path: reason} map GC (real or previewed) protects."""
    current = current_release_path()
    protected_reasons: dict[Path, str] = {}
    if current is not None:
        protected_reasons[current.resolve()] = "current"
    if protect is not None:
        protected_reasons.setdefault(protect.resolve(), "incoming")
    if protect_extra:
        for path, extra_reason in protect_extra.items():
            protected_reasons.setdefault(path.resolve(), extra_reason)
    return protected_reasons


def _plan_gc(
    dirs: list[Path],
    *,
    keep: int,
    protected_reasons: Mapping[Path, str],
) -> dict[str, Any]:
    """Decide what GC would keep/delete/skip. Takes no filesystem action.

    Pure decision logic shared by :func:`gc_releases` (which acts on
    ``to_delete``) and the ``--dry-run`` preview in :func:`deploy_blue_green`
    (which does not) -- a second, separately maintained copy of this
    keep/protect/skip logic in the CLI preview is exactly the kind of drift
    TAP-6896 exists to prevent.
    """
    kept: list[str] = []
    to_delete: list[str] = []
    skipped: list[str] = []
    protected_report: dict[str, str] = {}

    for idx, release_dir in enumerate(dirs):
        resolved = release_dir.resolve()
        reason = protected_reasons.get(resolved)
        if reason is not None:
            kept.append(release_dir.name)
            protected_report[release_dir.name] = reason
            continue
        if idx < keep:
            kept.append(release_dir.name)
            continue
        if pids_referencing(resolved):
            skipped.append(release_dir.name)
            continue
        to_delete.append(release_dir.name)

    return {
        "kept": kept,
        "to_delete": to_delete,
        "skipped_in_use": skipped,
        "protected": protected_report,
    }


def gc_releases(
    *,
    keep: int = DEFAULT_KEEP_RELEASES,
    protect: Path | None = None,
    protect_extra: Mapping[Path, str] | None = None,
) -> dict[str, Any]:
    """Delete old release dirs not referenced by live processes.

    ``protect`` names the incoming release (kept for call-site compatibility);
    ``protect_extra`` names additional paths with a reason each -- used to
    protect the pre-flip rollback target alongside the incoming release
    (TAP-6895), so it survives index-based eviction the way ``current`` does.
    """
    protected_reasons = _resolve_protected_reasons(protect=protect, protect_extra=protect_extra)
    plan = _plan_gc(_release_dirs(), keep=keep, protected_reasons=protected_reasons)
    for name in plan["to_delete"]:
        shutil.rmtree(RELEASES_DIR / name, ignore_errors=True)

    return {
        "ok": True,
        "kept": plan["kept"],
        "deleted": plan["to_delete"],
        "skipped_in_use": plan["skipped_in_use"],
        "protected": plan["protected"],
    }


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
    except filelock.Timeout:
        return True
    return False


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
        # The incoming release directory does not exist yet (build hasn't
        # run), so it never appears among _release_dirs() -- there is
        # nothing to preview-delete for it. The pre-flip `current` is the
        # release an operator would roll back to if this deploy proceeded;
        # _resolve_protected_reasons protecting it as "current" here previews
        # the same outcome gc_releases reaches post-flip (TAP-6896), via the
        # identical helper the real GC uses -- not a second copy of the rules.
        protected_reasons = _resolve_protected_reasons(protect=release.path, protect_extra=None)
        gc_preview = _plan_gc(
            _release_dirs(), keep=keep_releases, protected_reasons=protected_reasons
        )
        report["ok"] = True
        report["planned"] = {
            "build": str(release.path),
            "flip": str(CURRENT_LINK),
            "keep_releases": keep_releases,
        }
        report["gc_preview"] = gc_preview
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

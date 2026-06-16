"""Call-graph fingerprint settings and git-aware invalidation (TAP-4077, TAP-4078)."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from tapps_mcp.project.import_graph import _DEFAULT_EXCLUDES, _should_skip


@dataclass(frozen=True)
class CallGraphFingerprintSettings:
    """Shared inputs for index fingerprint computation (TAP-4077)."""

    project_root: Path
    exclude_patterns: tuple[str, ...] = ()
    top_level_package: str = ""


def fingerprint_settings(
    project_root: Path,
    *,
    exclude_patterns: list[str] | None = None,
    top_level_package: str = "",
) -> CallGraphFingerprintSettings:
    """Build fingerprint settings used by build, summarize, and doctor."""
    patterns = tuple(exclude_patterns or ())
    return CallGraphFingerprintSettings(
        project_root=project_root.resolve(),
        exclude_patterns=patterns,
        top_level_package=top_level_package,
    )


def _git_fingerprint_component(project_root: Path) -> str | None:
    """Return ``HEAD|dirty_py_paths`` when *project_root* is a git checkout."""
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if head.returncode != 0:
            return None
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", "*.py"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        dirty_paths: list[str] = []
        if dirty.returncode == 0:
            for line in dirty.stdout.splitlines():
                if len(line) < 4:
                    continue
                path = line[3:].strip()
                if path.endswith(".py"):
                    dirty_paths.append(path.replace("\\", "/"))
        dirty_paths.sort()
        return f"{head.stdout.strip()}|{'|'.join(dirty_paths)}"
    except (OSError, subprocess.TimeoutExpired):
        return None


def _mtime_fingerprint_component(settings: CallGraphFingerprintSettings, index_version: int) -> str:
    excludes = set(_DEFAULT_EXCLUDES)
    if settings.exclude_patterns:
        excludes.update(settings.exclude_patterns)
    parts = [f"v{index_version}", settings.top_level_package]
    for py_file in sorted(settings.project_root.rglob("*.py")):
        if _should_skip(py_file, excludes) or py_file.name.endswith("_pb2.py"):
            continue
        try:
            stat = py_file.stat()
        except OSError:
            continue
        rel = py_file.relative_to(settings.project_root)
        parts.append(f"{rel}:{stat.st_mtime_ns}:{stat.st_size}")
    return "|".join(parts)


def compute_index_fingerprint(
    settings: CallGraphFingerprintSettings,
    *,
    index_version: int,
) -> str:
    """Compute a stable fingerprint for call-graph cache invalidation."""
    git_part = _git_fingerprint_component(settings.project_root)
    if git_part is not None:
        payload = f"git:{git_part}|pkg:{settings.top_level_package}|v{index_version}"
    else:
        payload = _mtime_fingerprint_component(settings, index_version)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]

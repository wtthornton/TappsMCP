"""Call-graph fingerprint settings and git-aware invalidation (TAP-4077, TAP-4078)."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from tapps_mcp.project.import_graph import (
    _DEFAULT_EXCLUDES,
    _configured_graph_excludes,
    _should_skip,
)

# Source-file suffixes folded into the fingerprint (TAP-4537). Python plus the
# TypeScript pair so a new/edited .ts/.tsx invalidates the call-graph cache.
_FINGERPRINT_SUFFIXES = (".py", ".ts", ".tsx")

# Sentinel used when tree-sitter-typescript is not installed, so the fingerprint
# stays stable across environments that lack the optional grammar (TAP-4537).
_TS_GRAMMAR_ABSENT = "absent"


def _ts_grammar_version() -> str:
    """Return the installed ``tree_sitter_typescript`` version, or a sentinel.

    Folded into the fingerprint so a grammar upgrade invalidates the cache.
    Imported defensively: the grammar is an optional (``treesitter`` extra)
    dependency and may be absent.
    """
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("tree-sitter-typescript")
        except PackageNotFoundError:
            return _TS_GRAMMAR_ABSENT
    except ImportError:  # pragma: no cover - importlib.metadata always present on 3.12
        return _TS_GRAMMAR_ABSENT


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
    """Build fingerprint settings used by build, summarize, and doctor.

    Merges caller-passed patterns with the project's configured
    ``graph_exclude_patterns`` (``.tapps-mcp.yaml`` / env) and sorts for a
    deterministic fingerprint. Resolving config here keeps the build walk and
    the staleness fingerprint on the exact same file set.
    """
    resolved_root = project_root.resolve()
    merged = set(exclude_patterns or ())
    merged.update(_configured_graph_excludes(resolved_root))
    return CallGraphFingerprintSettings(
        project_root=resolved_root,
        exclude_patterns=tuple(sorted(merged)),
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
            ["git", "status", "--porcelain", "--", *[f"*{s}" for s in _FINGERPRINT_SUFFIXES]],
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
                if path.endswith(_FINGERPRINT_SUFFIXES):
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
    source_files = sorted(
        f for suffix in _FINGERPRINT_SUFFIXES for f in settings.project_root.rglob(f"*{suffix}")
    )
    nested_repo_cache: dict[Path, bool] = {}
    for source_file in source_files:
        if (
            _should_skip(source_file, excludes, settings.project_root, nested_repo_cache)
            or source_file.name.endswith("_pb2.py")
        ):
            continue
        try:
            stat = source_file.stat()
        except OSError:
            continue
        rel = source_file.relative_to(settings.project_root)
        parts.append(f"{rel}:{stat.st_mtime_ns}:{stat.st_size}")
    return "|".join(parts)


def compute_per_file_fingerprints(
    settings: CallGraphFingerprintSettings,
) -> dict[str, str]:
    """Return a ``{relative_posix_path: content_hash}`` map for the source tree.

    Per-file fingerprints (TAP-4533) let the incremental re-index compute the
    *changed subset* without re-hashing every file semantically: compare this
    map to the one persisted in the cached index and the differing keys are the
    files to re-parse. The hash is content-based (sha256 of the file bytes) so
    it is stable across checkouts and machines — unlike an mtime, which changes
    on a no-op ``touch`` and would force a needless re-parse.
    """
    excludes = set(_DEFAULT_EXCLUDES)
    if settings.exclude_patterns:
        excludes.update(settings.exclude_patterns)
    fingerprints: dict[str, str] = {}
    source_files = sorted(
        f for suffix in _FINGERPRINT_SUFFIXES for f in settings.project_root.rglob(f"*{suffix}")
    )
    nested_repo_cache: dict[Path, bool] = {}
    for source_file in source_files:
        if (
            _should_skip(source_file, excludes, settings.project_root, nested_repo_cache)
            or source_file.name.endswith("_pb2.py")
        ):
            continue
        try:
            data = source_file.read_bytes()
        except OSError:
            continue
        rel = source_file.relative_to(settings.project_root).as_posix()
        fingerprints[rel] = hashlib.sha256(data).hexdigest()[:16]
    return fingerprints


def compute_index_fingerprint(
    settings: CallGraphFingerprintSettings,
    *,
    index_version: int,
) -> str:
    """Compute a stable fingerprint for call-graph cache invalidation."""
    ts_grammar = _ts_grammar_version()
    # Exclude patterns change which files are indexed, so they must be part of
    # the fingerprint — the git component tracks HEAD/dirty paths only and
    # would otherwise miss a graph_exclude_patterns config change.
    excludes_part = ",".join(settings.exclude_patterns)
    git_part = _git_fingerprint_component(settings.project_root)
    if git_part is not None:
        payload = (
            f"git:{git_part}|pkg:{settings.top_level_package}|v{index_version}"
            f"|ts:{ts_grammar}|ex:{excludes_part}"
        )
    else:
        payload = (
            f"{_mtime_fingerprint_component(settings, index_version)}"
            f"|ts:{ts_grammar}|ex:{excludes_part}"
        )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]

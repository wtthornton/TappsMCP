"""File-discovery and result-collection helpers for validate_changed.

Extracted from ``validate_changed.py`` (TAP-2468) to keep that module
focused on the MCP tool handler. This module is responsible for:

* Resolving the list of scorable files (explicit list or ``git diff``).
* Looking up the content-hash quick-check cache and partitioning the
  input paths into ``(cached_results, uncached_paths)``.
* Normalising ``asyncio.gather`` results into plain dicts.
* Writing the post-validation marker files used by stop hooks.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from collections.abc import Callable

from tapps_mcp.security.verdict import read_security_verdict

_logger = structlog.get_logger(__name__)

# Marker file for stop hook: if present and recent, hook skips
# "run validate" reminder.
_VALIDATE_OK_MARKER = ".tapps-mcp/sessions/last_validate_ok"

# Scorable suffixes used for large-repo file_paths guard (TAP-5271).
_SCORABLE_SUFFIXES = (
    ".py",
    ".pyi",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".go",
    ".rs",
)


def count_tracked_scorable_files(project_root: Path, *, cap: int = 500) -> int:
    """Count tracked scorable files under *project_root* (best-effort, capped).

    Uses ``git ls-files`` when available; falls back to a shallow ``rglob`` of
    scorable suffixes. Stops counting at *cap* so the large-repo check stays
    cheap (TAP-5271).
    """
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "-C", str(project_root), "ls-files"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        proc = None
    count = 0
    if proc is not None and proc.returncode == 0:
        for line in proc.stdout.splitlines():
            lower = line.lower()
            if lower.endswith(_SCORABLE_SUFFIXES):
                count += 1
                if count >= cap:
                    return count
        return count
    try:
        for path in project_root.rglob("*"):
            if not path.is_file():
                continue
            name = path.name.lower()
            if any(name.endswith(sfx) for sfx in _SCORABLE_SUFFIXES):
                count += 1
                if count >= cap:
                    return count
    except OSError:
        return count
    return count


def _write_validate_ok_marker(project_root: Path) -> None:
    """Write markers so hooks can detect that validation was run.

    Writes two markers:
    - ``_VALIDATE_OK_MARKER`` (legacy, for Cursor stop hook)
    - ``.tapps-mcp/.validation-marker`` (for Claude Code blocking hooks)
    """
    # TAP-6606: a real batch just ran, so any recorded "nothing to gate"
    # verdict is now false. Drop it here rather than letting it age out —
    # a stale verdict must never outlive the session that earned it.
    from tapps_mcp.tools.nothing_to_gate import clear as _clear_nothing_to_gate

    _clear_nothing_to_gate(project_root)

    ts = str(time.time())
    with contextlib.suppress(OSError):
        marker = project_root / _VALIDATE_OK_MARKER
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(ts, encoding="utf-8")
    with contextlib.suppress(OSError):
        validation_marker = project_root / ".tapps-mcp" / ".validation-marker"
        validation_marker.parent.mkdir(parents=True, exist_ok=True)
        validation_marker.write_text(ts, encoding="utf-8")


def _discover_changed_files(
    file_paths: str,
    base_ref: str,
    project_root: Path,
    *,
    cross_repo_root: Path | None = None,
) -> list[Path]:
    """Resolve the list of scorable files to validate.

    When *file_paths* is non-empty, parse the comma-separated list and
    validate each path. Otherwise, auto-detect changed scorable files
    via ``git diff``.

    When *cross_repo_root* is set (explicit ``project_root`` override on
    the MCP tool), paths resolve under that root instead of the host
    ``settings.project_root`` / ``TAPPS_MCP_HOST_PROJECT_ROOT`` mapping.

    Supports: Python (.py, .pyi), TypeScript/JavaScript (.ts, .tsx,
    .js, .jsx, .mjs, .cjs), Go (.go), and Rust (.rs) files.
    """
    from tapps_mcp.server import _validate_file_path
    from tapps_mcp.server_helpers import _is_scorable_file
    from tapps_mcp.tools.batch_validator import detect_changed_scorable_files
    from tapps_mcp.tools.project_paths import validate_read_path_under_root

    paths: list[Path] = []
    if file_paths.strip():
        for raw_fp in file_paths.split(","):
            cleaned_fp = raw_fp.strip()
            if not cleaned_fp:
                continue
            if not _is_scorable_file(cleaned_fp):
                continue
            if cross_repo_root is not None:
                with contextlib.suppress(ValueError, FileNotFoundError):
                    paths.append(validate_read_path_under_root(cleaned_fp, cross_repo_root))
            else:
                with contextlib.suppress(ValueError, FileNotFoundError):
                    paths.append(_validate_file_path(cleaned_fp))
    else:
        paths = detect_changed_scorable_files(project_root, base_ref)
    return paths


def _cache_hit_as_file_result(path: Path, preset: str = "standard") -> dict[str, Any] | None:
    """Return a validate_changed-shaped file_result from the content cache.

    STORY-101.3 — reuses the ``KIND_QUICK_CHECK`` entry populated by
    :func:`tapps_quick_check` so identical-content re-validations don't
    consume the auto-detect wall-clock budget.

    ``preset`` must match the batch's gate preset: the cache key includes it
    (see :func:`content_hash_cache.result_key`), so a ``standard`` entry can
    never satisfy a ``strict`` run.
    """
    from tapps_mcp.tools import content_hash_cache as _chc

    try:
        key = _chc.result_key(path, preset=preset)
    except (OSError, FileNotFoundError):
        return None
    cached = _chc.get(_chc.KIND_QUICK_CHECK, key)
    if cached is None:
        return None
    return {
        "file_path": str(path),
        "overall_score": cached.get("overall_score", 0.0),
        "gate_passed": cached.get("gate_passed", False),
        # TAP-6387: replayed quick_check payload — read the recorded verdict,
        # never re-derive one from the issue count below it.
        "security_passed": read_security_verdict(cached),
        "security_issues": cached.get("security_issue_count", 0),
        "cache_hit": True,
        # Entries come from quick_check, which always scores the full
        # category set — label them so a quick-mode batch does not report
        # a 7-category score as if it were the 1-category lint score.
        "mode": "full",
        "categories_scored": cached.get("categories_scored", []),
    }


def _partition_by_cache(
    paths: list[Path],
    preset: str = "standard",
) -> tuple[list[dict[str, Any]], list[Path]]:
    """Split ``paths`` into (cached_results, uncached_paths)."""
    cached_results: list[dict[str, Any]] = []
    uncached_paths: list[Path] = []
    for p in paths:
        hit = _cache_hit_as_file_result(p, preset)
        if hit is not None:
            cached_results.append(hit)
        else:
            uncached_paths.append(p)
    return cached_results, uncached_paths


def _collect_results(
    raw_results: list[dict[str, Any] | BaseException],
    paths: list[Path],
) -> list[dict[str, Any]]:
    """Normalize gather results, converting exceptions to error dicts."""
    results: list[dict[str, Any]] = []
    for i, raw in enumerate(raw_results):
        if isinstance(raw, BaseException):
            results.append({"file_path": str(paths[i]), "errors": [str(raw)]})
        else:
            results.append(raw)
    return results


# TAP-6068: refs tried (in order) when checking whether a failing file's
# content already existed on trunk before this session touched anything.
# Mirrors the branch-range fallback in batch_validator.detect_changed_scorable_files.
_ZERO_DELTA_TRUNK_REFS = ("main", "master", "origin/main", "origin/master")
_ZERO_DELTA_GIT_TIMEOUT = 5


def _git_show_text(project_root: Path, ref: str, relpath: str) -> str | None:
    """Return *relpath*'s content at *ref*, or ``None`` if unresolvable."""
    from tapps_mcp.tools.subprocess_runner import run_command

    result = run_command(
        ["git", "show", f"{ref}:{relpath}"],
        cwd=str(project_root),
        timeout=_ZERO_DELTA_GIT_TIMEOUT,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _is_zero_delta_against_trunk(project_root: Path, file_path: str) -> bool:
    """True when *file_path*'s current content matches its content on trunk.

    Distinguishes pre-existing debt (a sub-70 file the session never
    touched) from a fresh regression the gate should genuinely block on.
    Fail-closed: a brand-new file, an unresolved trunk ref, or a read error
    all resolve to ``False`` — a genuine regression can never hide behind
    this check.
    """
    try:
        rel = Path(file_path).resolve().relative_to(project_root.resolve())
    except (OSError, ValueError):
        return False
    try:
        current = (project_root / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    posix_rel = rel.as_posix()
    for ref in _ZERO_DELTA_TRUNK_REFS:
        trunk_content = _git_show_text(project_root, ref, posix_rel)
        if trunk_content is not None:
            return trunk_content == current
    return False


def _annotate_zero_delta_failures(
    results: list[dict[str, Any]],
    project_root: Path,
) -> bool:
    """Tag each failing result with ``zero_delta``; report if ALL of them are.

    Mutates *results* in place, adding ``zero_delta: True`` to any failing
    entry whose content is unchanged from trunk. Returns ``True`` only when
    there is at least one failure and every failure is zero-delta —
    pre-existing debt this session did not introduce, distinguishable from a
    fresh regression (TAP-6068 acceptance item 3).
    """
    saw_failure = False
    saw_new_failure = False
    for r in results:
        if r.get("gate_passed"):
            continue
        saw_failure = True
        file_path = r.get("file_path")
        zero_delta = (
            _is_zero_delta_against_trunk(project_root, file_path)
            if isinstance(file_path, str)
            else False
        )
        r["zero_delta"] = zero_delta
        if not zero_delta:
            saw_new_failure = True
    return saw_failure and not saw_new_failure


async def maybe_write_debt_ok_marker(
    write_marker: Callable[[Path], None],
    *,
    incomplete: bool,
    all_passed: bool,
    results: list[dict[str, Any]],
    project_root: Path,
) -> bool:
    """Write the ok-marker on a pass or a debt-only failure; report which.

    Returns ``only_pre_existing_debt_failed`` — ``True`` when the batch
    failed solely on pre-existing debt (TAP-6068). *write_marker* is passed
    in (rather than imported) so callers keep writing through their own
    test-patchable indirection.
    """
    if all_passed:
        write_marker(project_root)
        return False
    if incomplete or not results:
        return False
    only_debt = await asyncio.to_thread(_annotate_zero_delta_failures, results, project_root)
    if only_debt:
        write_marker(project_root)
    return only_debt


__all__ = [
    "_VALIDATE_OK_MARKER",
    "_annotate_zero_delta_failures",
    "_cache_hit_as_file_result",
    "_collect_results",
    "_discover_changed_files",
    "_is_zero_delta_against_trunk",
    "_partition_by_cache",
    "_write_validate_ok_marker",
    "maybe_write_debt_ok_marker",
]

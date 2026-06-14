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

import contextlib
import time
from pathlib import Path
from typing import Any

import structlog

_logger = structlog.get_logger(__name__)

# Marker file for stop hook: if present and recent, hook skips
# "run validate" reminder.
_VALIDATE_OK_MARKER = ".tapps-mcp/sessions/last_validate_ok"


def _write_validate_ok_marker(project_root: Path) -> None:
    """Write markers so hooks can detect that validation was run.

    Writes two markers:
    - ``_VALIDATE_OK_MARKER`` (legacy, for Cursor stop hook)
    - ``.tapps-mcp/.validation-marker`` (for Claude Code blocking hooks)
    """
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


def _cache_hit_as_file_result(path: Path) -> dict[str, Any] | None:
    """Return a validate_changed-shaped file_result from content-hash cache.

    STORY-101.3 — reuses the ``KIND_QUICK_CHECK`` entry populated by
    :func:`tapps_quick_check` so identical-content re-validations don't
    consume the auto-detect wall-clock budget.
    """
    from tapps_mcp.tools import content_hash_cache as _chc

    try:
        sha = _chc.content_hash(path)
    except (OSError, FileNotFoundError):
        return None
    cached = _chc.get(_chc.KIND_QUICK_CHECK, sha)
    if cached is None:
        return None
    return {
        "file_path": str(path),
        "overall_score": cached.get("overall_score", 0.0),
        "gate_passed": cached.get("gate_passed", False),
        "security_passed": cached.get("security_passed", True),
        "security_issues": cached.get("security_issue_count", 0),
        "cache_hit": True,
    }


def _partition_by_cache(
    paths: list[Path],
) -> tuple[list[dict[str, Any]], list[Path]]:
    """Split ``paths`` into (cached_results, uncached_paths)."""
    cached_results: list[dict[str, Any]] = []
    uncached_paths: list[Path] = []
    for p in paths:
        hit = _cache_hit_as_file_result(p)
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


__all__ = [
    "_VALIDATE_OK_MARKER",
    "_cache_hit_as_file_result",
    "_collect_results",
    "_discover_changed_files",
    "_partition_by_cache",
    "_write_validate_ok_marker",
]

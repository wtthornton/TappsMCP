"""Batch validation - detect changed Python files and validate them."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from tapps_mcp.tools.subprocess_runner import run_command

if TYPE_CHECKING:
    from pathlib import Path

logger = structlog.get_logger(__name__)

# Maximum files to validate in a single batch call.
# Raised from 10 to 50 to handle larger changesets without silent truncation.
MAX_BATCH_FILES = 50

# Git diff timeout (seconds). Kept low so the "no changed files" path returns quickly.
_GIT_DIFF_TIMEOUT = 5


def _git_diff_names(project_root: Path, *args: str) -> set[str]:
    """Run git diff --name-only with given args; return set of filenames or empty."""
    result = run_command(
        ["git", "diff", "--name-only", *args],
        cwd=str(project_root),
        timeout=_GIT_DIFF_TIMEOUT,
    )
    if result.returncode == 0 and result.stdout:
        return set(result.stdout.strip().splitlines())
    if result.timed_out:
        logger.debug("git_diff_timed_out", args=args, project_root=str(project_root))
    elif result.returncode != 0:
        logger.debug(
            "git_diff_failed",
            args=args,
            returncode=result.returncode,
            stderr=result.stderr,
        )
    return set()


def _git_untracked_names(project_root: Path) -> set[str]:
    """Return untracked (but not ignored) files via ``git ls-files --others``."""
    result = run_command(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=str(project_root),
        timeout=_GIT_DIFF_TIMEOUT,
    )
    if result.returncode == 0 and result.stdout:
        return set(result.stdout.strip().splitlines())
    if result.timed_out:
        logger.debug("git_ls_files_timed_out", project_root=str(project_root))
    elif result.returncode != 0:
        logger.debug(
            "git_ls_files_failed",
            returncode=result.returncode,
            project_root=str(project_root),
        )
    return set()


@dataclass
class FileValidationResult:
    """Result of validating a single file."""

    file_path: str
    score: float | None = None
    gate_passed: bool | None = None
    security_passed: bool | None = None
    security_issues: int = 0
    errors: list[str] = field(default_factory=list)


def detect_changed_python_files(
    project_root: Path,
    base_ref: str = "HEAD",
) -> list[Path]:
    """Detect changed Python files using git diff.

    Runs unstaged and staged git diffs in parallel for minimal latency.
    Deduplicates and returns sorted .py paths that exist.

    Args:
        project_root: The git repository root.
        base_ref: Git ref to diff against (default: HEAD).

    Returns:
        Sorted, deduplicated list of changed .py file paths.
    """
    return detect_changed_scorable_files(project_root, base_ref, extensions={".py", ".pyi"})


def detect_changed_scorable_files(
    project_root: Path,
    base_ref: str = "HEAD",
    extensions: set[str] | None = None,
) -> list[Path]:
    """Detect changed files that can be scored using git diff.

    Runs unstaged and staged git diffs in parallel for minimal latency.
    Deduplicates and returns sorted paths that exist and have scorable extensions.

    Args:
        project_root: The git repository root.
        base_ref: Git ref to diff against (default: HEAD).
        extensions: Set of file extensions to include. If None, uses all
            supported extensions (.py, .pyi, .ts, .tsx, .js, .jsx, .mjs, .cjs, .go, .rs).

    Returns:
        Sorted, deduplicated list of changed scorable file paths.
    """
    if extensions is None:
        from tapps_mcp.scoring.language_detector import get_supported_extensions

        extensions = set(get_supported_extensions())

    files: set[str] = set()
    with ThreadPoolExecutor(max_workers=3) as executor:
        fut_unstaged = executor.submit(_git_diff_names, project_root, base_ref)
        fut_staged = executor.submit(_git_diff_names, project_root, "--cached")
        fut_untracked = executor.submit(_git_untracked_names, project_root)
        try:
            files.update(fut_unstaged.result(timeout=_GIT_DIFF_TIMEOUT + 1))
        except (FuturesTimeoutError, OSError):
            logger.warning("git_diff_unstaged_failed")
        try:
            files.update(fut_staged.result(timeout=_GIT_DIFF_TIMEOUT + 1))
        except (FuturesTimeoutError, OSError):
            logger.warning("git_diff_staged_failed")
        try:
            files.update(fut_untracked.result(timeout=_GIT_DIFF_TIMEOUT + 1))
        except (FuturesTimeoutError, OSError):
            logger.warning("git_ls_files_untracked_failed")

    scorable_files: list[Path] = []
    for raw_name in sorted(files):
        cleaned = raw_name.strip()
        if not cleaned:
            continue
        # Check if the file extension is in the allowed set
        from pathlib import Path as _Path

        p = _Path(cleaned)
        if p.suffix.lower() not in extensions:
            continue
        path = project_root / cleaned
        if path.exists():
            scorable_files.append(path)

    return scorable_files


def format_batch_summary(results: list[dict[str, Any]]) -> str:
    """Format a human-readable summary of batch validation results."""
    total = len(results)
    passed = sum(1 for r in results if r.get("gate_passed") is True)
    failed = sum(1 for r in results if r.get("gate_passed") is not True)
    security_issues = sum(r.get("security_issues", 0) for r in results)

    parts = [f"{total} files validated"]
    if passed:
        parts.append(f"{passed} passed gate")
    if failed:
        parts.append(f"{failed} failed gate")
    if security_issues:
        parts.append(f"{security_issues} security issues")
    return ", ".join(parts)

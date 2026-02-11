"""Batch validation - detect changed Python files and validate them."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from pathlib import Path

logger = structlog.get_logger(__name__)

# Maximum files to validate in a single batch call
MAX_BATCH_FILES = 10


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

    Checks both unstaged and staged changes, deduplicates results.

    Args:
        project_root: The git repository root.
        base_ref: Git ref to diff against (default: HEAD).

    Returns:
        Sorted, deduplicated list of changed .py file paths.
    """
    files: set[str] = set()

    # Unstaged changes
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", base_ref],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            files.update(result.stdout.strip().splitlines())
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        logger.warning("git_diff_unstaged_failed")

    # Staged changes
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            files.update(result.stdout.strip().splitlines())
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        logger.warning("git_diff_staged_failed")

    # Filter to .py files that exist
    py_files: list[Path] = []
    for raw_name in sorted(files):
        cleaned = raw_name.strip()
        if not cleaned or not cleaned.endswith(".py"):
            continue
        path = project_root / cleaned
        if path.exists():
            py_files.append(path)

    return py_files


def format_batch_summary(results: list[dict[str, Any]]) -> str:
    """Format a human-readable summary of batch validation results."""
    total = len(results)
    passed = sum(1 for r in results if r.get("gate_passed"))
    failed = sum(1 for r in results if r.get("gate_passed") is False)
    security_issues = sum(r.get("security_issues", 0) for r in results)

    parts = [f"{total} files validated"]
    if passed:
        parts.append(f"{passed} passed gate")
    if failed:
        parts.append(f"{failed} failed gate")
    if security_issues:
        parts.append(f"{security_issues} security issues")
    return ", ".join(parts)

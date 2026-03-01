"""mypy type-checker wrapper — scoped single-file execution."""

from __future__ import annotations

import structlog

from tapps_mcp.scoring.models import TypeIssue
from tapps_mcp.tools.subprocess_runner import run_command, run_command_async

logger = structlog.get_logger(__name__)


def parse_mypy_output(raw: str, target_file: str | None = None) -> list[TypeIssue]:
    """Parse mypy plain-text output into ``TypeIssue`` models.

    Each line looks like::

        path/to/file.py:10: error: Incompatible types [assignment]
    """
    issues: list[TypeIssue] = []
    for line in raw.strip().splitlines():
        if (
            "error:" not in line.lower()
            and "warning:" not in line.lower()
            and "note:" not in line.lower()
        ):
            continue
        parts = line.split(":", 3)
        min_parts = 4
        if len(parts) < min_parts:
            continue
        filename = parts[0].strip()
        # Filter to target file if specified
        if target_file and target_file not in filename:
            continue
        try:
            line_num = int(parts[1].strip())
        except ValueError:
            continue
        severity_raw = parts[2].strip().lower()
        message = parts[3].strip()

        # Extract error code from brackets
        error_code: str | None = None
        if "[" in message and "]" in message:
            start = message.rfind("[")
            end = message.rfind("]")
            if start < end:
                error_code = message[start + 1 : end]
                message = message[:start].strip()

        if "error" in severity_raw:
            severity = "error"
        elif "warning" in severity_raw:
            severity = "warning"
        else:
            severity = "note"

        issues.append(
            TypeIssue(
                file=filename,
                line=line_num,
                message=message,
                error_code=error_code,
                severity=severity,
            )
        )
    return issues


def calculate_type_score(issues: list[TypeIssue]) -> float:
    """Convert type issues into a 0-10 score."""
    from tapps_mcp.scoring.constants import MYPY_ERROR_PENALTY, clamp_individual

    error_count = sum(1 for i in issues if i.severity == "error")
    score = 10.0 - (error_count * MYPY_ERROR_PENALTY)
    return clamp_individual(score)


_MYPY_ARGS: list[str] = [
    "mypy",
    "--show-error-codes",
    "--no-error-summary",
    "--no-color-output",
    "--no-incremental",
    "--follow-imports=skip",
]


def run_mypy_check(file_path: str, *, cwd: str | None = None, timeout: int = 30) -> list[TypeIssue]:
    """Run scoped mypy on a single file synchronously."""
    result = run_command(
        [*_MYPY_ARGS, file_path],
        cwd=cwd,
        timeout=timeout,
    )
    if result.timed_out:
        logger.warning("mypy_timeout", file=file_path, timeout=timeout)
        return []
    return parse_mypy_output(result.stdout, target_file=file_path)


async def run_mypy_check_async(
    file_path: str, *, cwd: str | None = None, timeout: int = 30
) -> list[TypeIssue]:
    """Run scoped mypy on a single file asynchronously."""
    result = await run_command_async(
        [*_MYPY_ARGS, file_path],
        cwd=cwd,
        timeout=timeout,
    )
    if result.timed_out:
        logger.warning("mypy_timeout_async", file=file_path, timeout=timeout)
        return []
    return parse_mypy_output(result.stdout, target_file=file_path)

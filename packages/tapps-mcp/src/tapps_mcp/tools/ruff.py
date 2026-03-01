"""Ruff linter wrapper — check, fix, and JSON output parsing."""

from __future__ import annotations

import json

import structlog

from tapps_mcp.scoring.models import LintIssue
from tapps_mcp.tools.subprocess_runner import run_command, run_command_async

logger = structlog.get_logger(__name__)


def parse_ruff_json(raw: str) -> list[LintIssue]:
    """Parse ruff ``--output-format=json`` output into ``LintIssue`` models."""
    if not raw.strip():
        return []
    try:
        diagnostics = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(diagnostics, list):
        return []
    issues: list[LintIssue] = []
    for d in diagnostics:
        if not isinstance(d, dict):
            continue
        code_obj = d.get("code")
        if isinstance(code_obj, str):
            code_str = code_obj
        elif isinstance(code_obj, dict):
            code_str = str(code_obj.get("name", code_obj.get("code", "unknown")))
        else:
            code_str = "unknown"
        loc = d.get("location", {})
        severity = "error" if code_str.startswith(("E", "F")) else "warning"
        issues.append(
            LintIssue(
                code=code_str,
                message=d.get("message", ""),
                file=d.get("filename", ""),
                line=loc.get("row", 0),
                column=loc.get("column", 0),
                severity=severity,
            )
        )
    return issues


def calculate_lint_score(issues: list[LintIssue]) -> float:
    """Convert a list of lint issues into a 0-10 score."""
    from tapps_mcp.scoring.constants import (
        RUFF_ERROR_PENALTY,
        RUFF_FATAL_PENALTY,
        RUFF_WARNING_PENALTY,
        clamp_individual,
    )

    score = 10.0
    for issue in issues:
        if issue.code.startswith("F"):
            score -= RUFF_FATAL_PENALTY
        elif issue.code.startswith("E"):
            score -= RUFF_ERROR_PENALTY
        else:
            score -= RUFF_WARNING_PENALTY
    return clamp_individual(score)


def run_ruff_check(file_path: str, *, cwd: str | None = None, timeout: int = 30) -> list[LintIssue]:
    """Run ``ruff check --output-format=json`` synchronously."""
    result = run_command(
        ["ruff", "check", "--output-format=json", file_path],
        cwd=cwd,
        timeout=timeout,
    )
    if not result.success and not result.stdout.strip():
        logger.debug("ruff_check_no_output", stderr=result.stderr)
        return []
    return parse_ruff_json(result.stdout)


async def run_ruff_check_async(
    file_path: str, *, cwd: str | None = None, timeout: int = 30
) -> list[LintIssue]:
    """Run ``ruff check --output-format=json`` asynchronously."""
    result = await run_command_async(
        ["ruff", "check", "--output-format=json", file_path],
        cwd=cwd,
        timeout=timeout,
    )
    if not result.success and not result.stdout.strip():
        return []
    return parse_ruff_json(result.stdout)


def run_ruff_fix(file_path: str, *, cwd: str | None = None, timeout: int = 30) -> int:
    """Run ``ruff check --fix`` and return the number of fixes applied.

    Returns 0 if ruff is not available or the run fails.
    """
    result = run_command(
        ["ruff", "check", "--fix", "--output-format=json", file_path],
        cwd=cwd,
        timeout=timeout,
    )
    if not result.stdout.strip():
        return 0
    try:
        before = json.loads(result.stdout)
    except json.JSONDecodeError:
        return 0
    # ruff --fix returns remaining issues; compute fixes applied by comparing
    after_result = run_command(
        ["ruff", "check", "--output-format=json", file_path],
        cwd=cwd,
        timeout=timeout,
    )
    try:
        after = json.loads(after_result.stdout) if after_result.stdout.strip() else []
    except json.JSONDecodeError:
        after = []
    return max(0, len(before) - len(after))


async def run_ruff_fix_async(file_path: str, *, cwd: str | None = None, timeout: int = 30) -> int:
    """Async variant of ``run_ruff_fix``."""
    before_result = await run_command_async(
        ["ruff", "check", "--output-format=json", file_path],
        cwd=cwd,
        timeout=timeout,
    )
    try:
        before = json.loads(before_result.stdout) if before_result.stdout.strip() else []
    except json.JSONDecodeError:
        before = []

    await run_command_async(
        ["ruff", "check", "--fix", file_path],
        cwd=cwd,
        timeout=timeout,
    )

    after_result = await run_command_async(
        ["ruff", "check", "--output-format=json", file_path],
        cwd=cwd,
        timeout=timeout,
    )
    try:
        after = json.loads(after_result.stdout) if after_result.stdout.strip() else []
    except json.JSONDecodeError:
        after = []
    return max(0, len(before) - len(after))

"""Parallel external-tool execution.

Runs ruff, mypy, bandit, and radon concurrently via asyncio for the
full scoring mode.
"""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tapps_mcp.scoring.models import LintIssue, SecurityIssue, TypeIssue

import structlog

from tapps_mcp.tools.bandit import run_bandit_check_async
from tapps_mcp.tools.mypy import run_mypy_check_async
from tapps_mcp.tools.radon import run_radon_cc_async, run_radon_mi_async
from tapps_mcp.tools.ruff import run_ruff_check_async

logger = structlog.get_logger(__name__)


@dataclass
class ParallelResults:
    """Aggregated results from running all external tools."""

    lint_issues: list[LintIssue] = field(default_factory=list)
    type_issues: list[TypeIssue] = field(default_factory=list)
    security_issues: list[SecurityIssue] = field(default_factory=list)
    radon_cc: list[dict[str, Any]] = field(default_factory=list)
    radon_mi: float = 50.0
    missing_tools: list[str] = field(default_factory=list)
    degraded: bool = False


async def run_all_tools(
    file_path: str,
    *,
    cwd: str | None = None,
    timeout: int = 30,
    run_ruff: bool = True,
    run_mypy: bool = True,
    run_bandit: bool = True,
    run_radon: bool = True,
) -> ParallelResults:
    """Run ruff, mypy, bandit, and radon concurrently.

    Args:
        file_path: Path to the Python file to analyse.
        cwd: Working directory for subprocess calls.
        timeout: Per-tool timeout in seconds.
        run_ruff: Whether to run ruff.
        run_mypy: Whether to run mypy.
        run_bandit: Whether to run bandit.
        run_radon: Whether to run radon.

    Returns:
        Aggregated ``ParallelResults``.
    """
    results = ParallelResults()
    tasks: dict[str, asyncio.Task[Any]] = {}

    # Only schedule tools that are installed
    if run_ruff and shutil.which("ruff"):
        tasks["ruff"] = asyncio.create_task(
            run_ruff_check_async(file_path, cwd=cwd, timeout=timeout)
        )
    elif run_ruff:
        results.missing_tools.append("ruff")

    if run_mypy and shutil.which("mypy"):
        tasks["mypy"] = asyncio.create_task(
            run_mypy_check_async(file_path, cwd=cwd, timeout=timeout)
        )
    elif run_mypy:
        results.missing_tools.append("mypy")

    if run_bandit and shutil.which("bandit"):
        tasks["bandit"] = asyncio.create_task(
            run_bandit_check_async(file_path, cwd=cwd, timeout=timeout)
        )
    elif run_bandit:
        results.missing_tools.append("bandit")

    if run_radon and shutil.which("radon"):
        tasks["radon_cc"] = asyncio.create_task(
            run_radon_cc_async(file_path, cwd=cwd, timeout=timeout)
        )
        tasks["radon_mi"] = asyncio.create_task(
            run_radon_mi_async(file_path, cwd=cwd, timeout=timeout)
        )
    elif run_radon:
        results.missing_tools.append("radon")

    # Gather all tasks with an overall safety timeout
    if tasks:
        overall_timeout = timeout + 15  # individual tools have `timeout`; this is a safety cap
        try:
            done = await asyncio.wait_for(
                asyncio.gather(*tasks.values(), return_exceptions=True),
                timeout=overall_timeout,
            )
        except TimeoutError:
            logger.warning("parallel_gather_timeout", timeout=overall_timeout)
            results.degraded = True
            # Cancel any still-running tasks
            for t in tasks.values():
                t.cancel()
            return results
        task_names = list(tasks.keys())
        for name, result in zip(task_names, done, strict=True):
            if isinstance(result, Exception):
                logger.warning("tool_failed", tool=name, error=str(result))
                results.degraded = True
                continue
            if name == "ruff":
                results.lint_issues = result  # type: ignore[assignment]
            elif name == "mypy":
                results.type_issues = result  # type: ignore[assignment]
            elif name == "bandit":
                results.security_issues = result  # type: ignore[assignment]
            elif name == "radon_cc":
                results.radon_cc = result  # type: ignore[assignment]
            elif name == "radon_mi":
                results.radon_mi = result  # type: ignore[assignment]

    if results.missing_tools:
        results.degraded = True

    return results

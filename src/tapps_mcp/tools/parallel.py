"""Parallel external-tool execution.

Runs ruff, mypy, bandit, and radon concurrently via asyncio for the
full scoring mode.  Supports three execution modes:

- ``"subprocess"`` (default) - async subprocess for all tools
- ``"direct"``   - radon library + sync subprocess in thread pool
- ``"auto"``     - try subprocess, fall back to direct on failure
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

_VALID_MODES = {"subprocess", "direct", "auto"}


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
    tool_errors: dict[str, str] = field(default_factory=dict)


def _mark_missing(name: str, results: ParallelResults) -> None:
    """Record a tool as missing (not installed)."""
    results.missing_tools.append(name)
    results.tool_errors[name] = "not_found"


def _assign_result(name: str, results: ParallelResults, value: object) -> None:
    """Assign a completed tool result to the correct field."""
    if name == "ruff":
        results.lint_issues = value  # type: ignore[assignment]
    elif name == "mypy":
        results.type_issues = value  # type: ignore[assignment]
    elif name == "bandit":
        results.security_issues = value  # type: ignore[assignment]
    elif name == "radon_cc":
        results.radon_cc = value  # type: ignore[assignment]
    elif name == "radon_mi":
        results.radon_mi = value  # type: ignore[assignment]


async def run_all_tools(
    file_path: str,
    *,
    cwd: str | None = None,
    timeout: int = 30,
    run_ruff: bool = True,
    run_mypy: bool = True,
    run_bandit: bool = True,
    run_radon: bool = True,
    mode: str = "subprocess",
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
        mode: Execution mode - ``"subprocess"`` (async subprocess),
            ``"direct"`` (library / sync subprocess in thread pool),
            or ``"auto"`` (subprocess with direct fallback).

    Returns:
        Aggregated ``ParallelResults``.
    """
    if mode not in _VALID_MODES:
        logger.warning("invalid_mode", mode=mode, using="subprocess")
        mode = "subprocess"

    if mode == "direct":
        return await _run_direct(
            file_path,
            cwd=cwd,
            timeout=timeout,
            run_ruff=run_ruff,
            run_mypy=run_mypy,
            run_bandit=run_bandit,
            run_radon=run_radon,
        )

    # "subprocess" or "auto" — start with async subprocess
    return await _run_subprocess(
        file_path,
        cwd=cwd,
        timeout=timeout,
        run_ruff=run_ruff,
        run_mypy=run_mypy,
        run_bandit=run_bandit,
        run_radon=run_radon,
    )


# ---------------------------------------------------------------------------
# Subprocess mode (original async subprocess)
# ---------------------------------------------------------------------------


async def _run_subprocess(
    file_path: str,
    *,
    cwd: str | None = None,
    timeout: int = 30,
    run_ruff: bool = True,
    run_mypy: bool = True,
    run_bandit: bool = True,
    run_radon: bool = True,
) -> ParallelResults:
    """Run tools via async subprocess (original behaviour)."""
    results = ParallelResults()
    tasks: dict[str, asyncio.Task[Any]] = {}
    kw: dict[str, Any] = {"cwd": cwd, "timeout": timeout}

    if run_ruff and shutil.which("ruff"):
        tasks["ruff"] = asyncio.create_task(run_ruff_check_async(file_path, **kw))
    elif run_ruff:
        _mark_missing("ruff", results)

    if run_mypy and shutil.which("mypy"):
        tasks["mypy"] = asyncio.create_task(run_mypy_check_async(file_path, **kw))
    elif run_mypy:
        _mark_missing("mypy", results)

    if run_bandit and shutil.which("bandit"):
        tasks["bandit"] = asyncio.create_task(run_bandit_check_async(file_path, **kw))
    elif run_bandit:
        _mark_missing("bandit", results)

    if run_radon and shutil.which("radon"):
        tasks["radon_cc"] = asyncio.create_task(run_radon_cc_async(file_path, **kw))
        tasks["radon_mi"] = asyncio.create_task(run_radon_mi_async(file_path, **kw))
    elif run_radon:
        _mark_missing("radon", results)

    # Gather all tasks with an overall safety timeout
    if tasks:
        overall_timeout = timeout + 15
        try:
            done = await asyncio.wait_for(
                asyncio.gather(*tasks.values(), return_exceptions=True),
                timeout=overall_timeout,
            )
        except TimeoutError:
            logger.warning("parallel_gather_timeout", timeout=overall_timeout)
            results.degraded = True
            results.tool_errors["_gather"] = f"timeout after {overall_timeout}s"
            for t in tasks.values():
                t.cancel()
            return results
        task_names = list(tasks.keys())
        for name, result in zip(task_names, done, strict=True):
            if isinstance(result, Exception):
                error_msg = f"{type(result).__name__}: {result}"
                logger.warning("tool_failed", tool=name, error=error_msg)
                results.tool_errors[name] = error_msg
                results.degraded = True
                continue
            _assign_result(name, results, result)

    if results.missing_tools:
        results.degraded = True

    return results


# ---------------------------------------------------------------------------
# Direct mode (radon library + sync subprocess in thread pool)
# ---------------------------------------------------------------------------


async def _run_direct(
    file_path: str,
    *,
    cwd: str | None = None,
    timeout: int = 30,
    run_ruff: bool = True,
    run_mypy: bool = True,
    run_bandit: bool = True,
    run_radon: bool = True,
) -> ParallelResults:
    """Run tools via direct library calls and sync subprocess in thread pool.

    - **radon**: uses ``radon.complexity`` / ``radon.metrics`` directly
      (no subprocess at all).
    - **ruff**: uses synchronous ``subprocess.run`` in a thread pool via
      ``asyncio.to_thread``.
    - **mypy / bandit**: uses synchronous subprocess wrappers in a thread
      pool via ``asyncio.to_thread``.
    """
    from tapps_mcp.tools.bandit import run_bandit_check
    from tapps_mcp.tools.mypy import run_mypy_check
    from tapps_mcp.tools.radon_direct import cc_direct, is_available, mi_direct
    from tapps_mcp.tools.ruff_direct import run_ruff_check_direct

    results = ParallelResults()
    tasks: dict[str, asyncio.Task[Any]] = {}
    kw: dict[str, Any] = {"cwd": cwd, "timeout": timeout}

    # Ruff: sync subprocess in thread pool
    if run_ruff and shutil.which("ruff"):
        tasks["ruff"] = asyncio.create_task(run_ruff_check_direct(file_path, **kw))
    elif run_ruff:
        _mark_missing("ruff", results)

    # Mypy: sync subprocess in thread pool
    if run_mypy and shutil.which("mypy"):
        tasks["mypy"] = asyncio.create_task(
            asyncio.to_thread(run_mypy_check, file_path, cwd=cwd, timeout=timeout),
        )
    elif run_mypy:
        _mark_missing("mypy", results)

    # Bandit: sync subprocess in thread pool
    if run_bandit and shutil.which("bandit"):
        tasks["bandit"] = asyncio.create_task(
            asyncio.to_thread(run_bandit_check, file_path, cwd=cwd, timeout=timeout),
        )
    elif run_bandit:
        _mark_missing("bandit", results)

    # Radon: direct library import (no subprocess)
    if run_radon:
        if is_available():
            tasks["radon_cc"] = asyncio.create_task(
                asyncio.to_thread(cc_direct, file_path),
            )
            tasks["radon_mi"] = asyncio.create_task(
                asyncio.to_thread(mi_direct, file_path),
            )
        elif shutil.which("radon"):
            # Fall back to async subprocess if library not importable
            tasks["radon_cc"] = asyncio.create_task(run_radon_cc_async(file_path, **kw))
            tasks["radon_mi"] = asyncio.create_task(run_radon_mi_async(file_path, **kw))
            results.tool_errors["radon"] = "library_unavailable, using subprocess fallback"
        else:
            _mark_missing("radon", results)

    # Gather with safety timeout
    if tasks:
        overall_timeout = timeout + 15
        try:
            done = await asyncio.wait_for(
                asyncio.gather(*tasks.values(), return_exceptions=True),
                timeout=overall_timeout,
            )
        except TimeoutError:
            logger.warning("parallel_direct_gather_timeout", timeout=overall_timeout)
            results.degraded = True
            results.tool_errors["_gather"] = f"timeout after {overall_timeout}s"
            for t in tasks.values():
                t.cancel()
            return results
        task_names = list(tasks.keys())
        for name, result in zip(task_names, done, strict=True):
            if isinstance(result, Exception):
                error_msg = f"{type(result).__name__}: {result}"
                logger.warning("tool_direct_failed", tool=name, error=error_msg)
                results.tool_errors[name] = error_msg
                results.degraded = True
                continue
            _assign_result(name, results, result)

    if results.missing_tools:
        results.degraded = True

    return results

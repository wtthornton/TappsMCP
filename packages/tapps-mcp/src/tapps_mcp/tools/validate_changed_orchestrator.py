"""Per-file validation orchestration for validate_changed.

Extracted from ``validate_changed.py`` (TAP-2468) so the MCP tool handler
stays thin. This module owns:

* Running the scorer + gate + security scan against a single file under
  a concurrency semaphore.
* Reporting progress (initial notification + heartbeat task).
* Honouring the auto-detect wall-clock budget when running the batch.
* Background dependency-cache warming.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from mcp.server.fastmcp import Context

from tapps_mcp.server_helpers import emit_ctx_info
from tapps_mcp.tools.validate_changed_collection import _collect_results
from tapps_mcp.tools.validation_progress import (
    _ProgressTracker,
    _validate_progress_heartbeat,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from tapps_core.config.settings import TappsMCPSettings

_logger = structlog.get_logger(__name__)


# Maximum files to validate concurrently (balances speed vs subprocess pressure).
_VALIDATE_CONCURRENCY = 10


async def _run_security_scan(
    path: Path,
    score: Any,
    is_python: bool,
    do_security_full: bool,
    quick: bool,
) -> dict[str, Any]:
    """Run bandit + secret scan for Python files; no-op for other languages."""
    if do_security_full and is_python:
        from tapps_mcp.security.secret_scanner import SecretScanner

        secret_result = SecretScanner().scan_file(str(path))
        bandit_count = len(score.security_issues)
        secret_count = secret_result.total_findings
        bandit_crit_high = sum(
            1 for i in score.security_issues if i.severity in ("critical", "high")
        )
        return {
            "security_passed": (bandit_crit_high + secret_result.high_severity) == 0,
            "security_issues": bandit_count + secret_count,
        }
    if is_python and quick:
        return {"security_passed": True, "security_issues": 0}
    # Non-Python files: no security scanning yet
    return {"security_passed": True, "security_issues": 0}


async def _validate_single_file(
    path: Path,
    preset: str,
    quick: bool,
    do_security_full: bool,
    sem: asyncio.Semaphore,
    tracker: _ProgressTracker | None = None,
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    """Score and optionally security-scan a single file under concurrency limit.

    Supports multi-language files by using the appropriate scorer based
    on file extension:
    - Python (.py, .pyi) -> CodeScorer
    - TypeScript/JavaScript (.ts, .tsx, .js, .jsx, .mjs, .cjs) -> TypeScriptScorer
    - Go (.go) -> GoScorer
    - Rust (.rs) -> RustScorer
    """
    from tapps_mcp.gates.evaluator import evaluate_gate
    from tapps_mcp.server_helpers import _get_scorer_for_file

    async with sem:
        file_result: dict[str, Any] = {"file_path": str(path)}
        try:
            scorer = _get_scorer_for_file(path)
            if scorer is None:
                file_result["errors"] = [f"Unsupported file type: {path.suffix}"]
                from tapps_mcp.tools.validate_changed_diagnostics import finalize_file_diagnostics

                finalize_file_diagnostics(file_result)
                return file_result

            file_result["language"] = scorer.language

            if quick:
                score = await asyncio.to_thread(scorer.score_file_quick, path)
            else:
                score = await scorer.score_file(path)
            file_result["overall_score"] = round(score.overall_score, 2)

            gate = evaluate_gate(score, preset=preset)
            file_result["gate_passed"] = gate.passed
            if gate.failures:
                file_result["gate_failures"] = [f.model_dump() for f in gate.failures]

            from tapps_mcp.tools.validate_changed_diagnostics import (
                attach_improvement_hints,
                attach_score_diagnostics,
                finalize_file_diagnostics,
            )

            attach_score_diagnostics(file_result, score)
            attach_improvement_hints(file_result, score)

            sec = await _run_security_scan(
                path, score, scorer.language == "python", do_security_full, quick
            )
            file_result.update(sec)
            finalize_file_diagnostics(file_result)
        except Exception as exc:
            file_result["errors"] = [str(exc)]
            from tapps_mcp.tools.validate_changed_diagnostics import finalize_file_diagnostics

            finalize_file_diagnostics(file_result)
        if tracker is not None:
            tracker.completed += 1
            tracker.last_file = path.name
            tracker.record_file_result(str(path), file_result)
        await _emit_file_info(ctx, path, file_result)
        return file_result


async def _emit_file_info(
    ctx: Context[Any, Any, Any] | None,
    path: Path,
    result: dict[str, Any],
) -> None:
    """Send a ctx.info() log notification for the completed file (best-effort)."""
    score = result.get("overall_score", "?")
    passed = result.get("gate_passed", False)
    status = "PASSED" if passed else "FAILED"
    await emit_ctx_info(ctx, f"Validated {path.name}: {score}/100, gate {status}")


def _start_progress_reporting(
    ctx: Context[Any, Any, Any] | None,
    total_files: int,
    start: int,
    stop_event: asyncio.Event,
    tracker: _ProgressTracker | None = None,
) -> asyncio.Task[None] | None:
    """Start the progress heartbeat task if context supports it."""
    from tapps_mcp import server_pipeline_tools as _host

    if ctx is None or total_files <= 0:
        return None
    report = getattr(ctx, "report_progress", None)
    if callable(report):
        with contextlib.suppress(Exception):
            init_task = asyncio.create_task(_report_initial_progress(report, total_files))
            _host._background_tasks.add(init_task)
            init_task.add_done_callback(_host._background_tasks.discard)
    return asyncio.create_task(
        _validate_progress_heartbeat(ctx, total_files, start, stop_event, tracker),
    )


async def _report_initial_progress(
    report: Callable[..., Awaitable[Any]],
    total_files: int,
) -> None:
    """Send the initial progress=0 notification."""
    with contextlib.suppress(Exception):
        await report(
            progress=0,
            total=total_files,
            message=f"Validating {total_files} files...",
        )


def _maybe_warm_dependency_cache(
    settings: TappsMCPSettings,
    quick: bool,
) -> None:
    """Warm dependency cache in background when empty (does not block)."""
    from tapps_mcp import server_pipeline_tools as _host

    if not settings.dependency_scan_enabled or quick:
        return
    from tapps_mcp.tools.dependency_scan_cache import get_dependency_findings

    if not get_dependency_findings(str(settings.project_root)):
        task = asyncio.create_task(_warm_dependency_cache(settings))
        _host._background_tasks.add(task)
        task.add_done_callback(_host._background_tasks.discard)


async def _warm_dependency_cache(
    settings: TappsMCPSettings,
) -> None:
    """Best-effort background task to warm the dependency scan cache."""
    try:
        from tapps_mcp.tools.dependency_scan_cache import set_dependency_findings
        from tapps_mcp.tools.pip_audit import run_pip_audit_async

        result = await run_pip_audit_async(
            project_root=str(settings.project_root),
            source=settings.dependency_scan_source,
            severity_threshold=settings.dependency_scan_severity_threshold,
            ignore_ids=settings.dependency_scan_ignore_ids or None,
            timeout=30,
        )
        if not result.error:
            set_dependency_findings(str(settings.project_root), result.findings)
            _logger.debug(
                "dependency_cache_warmed",
                findings=len(result.findings),
            )
    except Exception:
        _logger.debug("dependency_cache_warming_failed", exc_info=True)


@dataclasses.dataclass
class _TimedOutInfo:
    """Aggregate state for wall-clock-limited auto-detect runs."""

    timed_out: bool = False
    files_remaining: list[Path] = dataclasses.field(default_factory=list)


async def _run_tasks_with_budget(
    tasks: list[asyncio.Task[dict[str, Any]]],
    uncached_paths: list[Path],
    start: int,
    auto_detect: bool,
) -> tuple[list[dict[str, Any]], _TimedOutInfo]:
    """Run validation tasks, honouring the auto-detect wall-clock budget.

    Looks up ``_AUTO_DETECT_BUDGET_S`` on ``server_pipeline_tools`` at
    call time so tests patching the module-level constant are honoured.
    """
    from tapps_mcp import server_pipeline_tools as _host

    info = _TimedOutInfo()
    if not tasks:
        return [], info

    if auto_detect:
        return await _run_tasks_with_timeout(tasks, uncached_paths, start, info, _host)

    raw = list(await asyncio.gather(*tasks, return_exceptions=True))
    return _collect_results(raw, uncached_paths), info


async def _run_tasks_with_timeout(
    tasks: list[asyncio.Task[dict[str, Any]]],
    uncached_paths: list[Path],
    start: int,
    info: _TimedOutInfo,
    host: Any,
) -> tuple[list[dict[str, Any]], _TimedOutInfo]:
    """Wait on tasks with the auto-detect wall-clock budget applied."""
    elapsed_s = (time.perf_counter_ns() - start) / 1e9
    remaining_budget = max(0.0, host._AUTO_DETECT_BUDGET_S - elapsed_s)
    done, pending = await asyncio.wait(tasks, timeout=remaining_budget)
    raw_results: list[dict[str, Any] | BaseException] = []
    completed_paths: list[Path] = []
    for p, t in zip(uncached_paths, tasks, strict=True):
        if t in done:
            try:
                raw_results.append(t.result())
            except Exception as exc:
                raw_results.append(exc)
            completed_paths.append(p)
        else:
            info.files_remaining.append(p)
            t.cancel()
    if pending:
        info.timed_out = True
        with contextlib.suppress(Exception):
            await asyncio.gather(*pending, return_exceptions=True)
    return _collect_results(raw_results, completed_paths), info


__all__ = [
    "_VALIDATE_CONCURRENCY",
    "_TimedOutInfo",
    "_emit_file_info",
    "_maybe_warm_dependency_cache",
    "_report_initial_progress",
    "_run_security_scan",
    "_run_tasks_with_budget",
    "_start_progress_reporting",
    "_validate_single_file",
    "_warm_dependency_cache",
]

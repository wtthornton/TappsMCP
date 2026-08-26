"""Per-file validation orchestration for validate_changed.

Extracted from ``validate_changed.py`` (TAP-2468) so the MCP tool handler
stays thin. This module owns:

* Running the scorer + gate + security scan against a single file under
  a concurrency semaphore.
* Reporting progress (initial notification + heartbeat task).
* Honouring the wall-clock budget when running the batch (tight for
  auto-detect, a much larger wedge-breaking ceiling for explicit paths).
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

from tapps_mcp.security.verdict import count_blocking, security_verdict
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
# Kept at 2 so shared HTTP fleet (nlt-build) cannot spawn a GIL stampede that
# starves Cursor initialize/tools/list — see tools.event_loop_guard.
_VALIDATE_CONCURRENCY = 2

# TAP-5965 — wall-clock ceiling for explicit-file_paths runs. Deliberately far
# above any healthy batch (full mode on a large explicit set is minutes, not
# tens of minutes): this is a wedge breaker, not a latency budget. Without it
# the explicit path gathered its tasks unbounded, so a single stuck file hung
# the MCP caller forever instead of returning a verdict.
_EXPLICIT_PATHS_BUDGET_S: float = 600.0


async def _run_security_scan(
    path: Path,
    score: Any,
    is_python: bool,
    do_security_full: bool,
    quick: bool,
    quick_sec: Any = None,
) -> dict[str, Any]:
    """Run bandit + secret scan for Python files; no-op for other languages.

    ``quick_sec`` is the :class:`SecurityScanResult` already produced by
    ``score_and_scan_quick`` in quick mode. Reusing it keeps the reported
    security verdict identical to ``tapps_quick_check``'s (TAP-5402) and
    avoids scanning the same file twice.

    TAP-6387: every branch derives ``security_passed`` from
    :func:`security_verdict` — the same definition backing
    ``SecurityScanResult.passed`` — so this tool cannot answer the question
    differently from ``tapps_quick_check``. The full-scan branch previously
    hand-counted ``bandit_crit_high + secret_result.high_severity``, which
    silently dropped the TAP-1794 secret-scan read error and reported an
    unreadable file as clean.
    """
    if do_security_full and is_python:
        from tapps_mcp.security.secret_scanner import SecretScanner

        secret_result = SecretScanner().scan_file(str(path))
        return {
            "security_passed": security_verdict(
                blocking_findings=(
                    count_blocking(score.security_issues) + secret_result.high_severity
                ),
                scan_error=secret_result.error,
            ),
            "security_issues": len(score.security_issues) + secret_result.total_findings,
        }
    if is_python and quick and quick_sec is not None:
        return {
            "security_passed": quick_sec.passed,
            "security_issues": quick_sec.total_issues,
        }
    if is_python and quick:
        # No precomputed scan (e.g. a test stub) — fall back to whatever the
        # scorer attached rather than claiming security_passed=True outright.
        issues = getattr(score, "security_issues", None) or []
        return {
            "security_passed": security_verdict(blocking_findings=count_blocking(issues)),
            "security_issues": len(issues),
            "security_scan_skipped": True,
        }
    # Non-Python files: no security scanning yet
    return {"security_passed": True, "security_issues": 0, "security_scan_skipped": True}


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
    from tapps_mcp.tools.event_loop_guard import heavy_cpu

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

            quick_sec = None
            async with heavy_cpu():
                if quick:
                    # TAP-5402: share tapps_quick_check's scoring path exactly.
                    # This used to call the bare `score_file_quick`, which
                    # scores only `linting` and publishes it on the 0-100
                    # scale — so `evaluate_gate` silently skipped every
                    # category-minimum check (they no-op on a missing
                    # category) and the gate reduced to `lint*10 >= 70`. The
                    # documented pre-completion gate therefore PASSED files
                    # that quick_check FAILED on the very same bytes.
                    from tapps_core.config.settings import load_settings
                    from tapps_mcp.server_scoring_tools import score_and_scan_quick

                    score, quick_sec = await score_and_scan_quick(path, scorer, load_settings())
                else:
                    score = await scorer.score_file(path)
            file_result["overall_score"] = round(score.overall_score, 2)
            file_result["mode"] = "quick" if quick else "full"
            file_result["categories_scored"] = list(score.categories.keys())
            # TAP-5402: a ruff timeout/crash yields an empty issue list and a
            # perfect lint score. Surfacing `degraded` keeps a tool outage
            # from reading as a clean pass.
            if score.degraded:
                file_result["degraded"] = True
                file_result["missing_tools"] = list(score.missing_tools)

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
                path, score, scorer.language == "python", do_security_full, quick, quick_sec
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

    if get_dependency_findings(str(settings.project_root)) is None:
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
    """Run validation tasks under a wall-clock budget.

    Auto-detect runs use the tight ``_AUTO_DETECT_BUDGET_S`` cap. Explicit
    ``file_paths`` runs get the far larger ``_EXPLICIT_PATHS_BUDGET_S``
    ceiling (TAP-5965) — long full-mode batches are legitimate, but an
    unbounded ``gather`` turned any wedged file into an indefinite hang for
    the MCP caller.

    ``_AUTO_DETECT_BUDGET_S`` is looked up on ``server_pipeline_tools`` at call
    time so tests patching it on the host module are honoured.
    """
    from tapps_mcp import server_pipeline_tools as _host

    info = _TimedOutInfo()
    if not tasks:
        return [], info

    budget_s = _host._AUTO_DETECT_BUDGET_S if auto_detect else _EXPLICIT_PATHS_BUDGET_S
    return await _run_tasks_with_timeout(tasks, uncached_paths, start, info, budget_s)


async def _run_tasks_with_timeout(
    tasks: list[asyncio.Task[dict[str, Any]]],
    uncached_paths: list[Path],
    start: int,
    info: _TimedOutInfo,
    budget_s: float,
) -> tuple[list[dict[str, Any]], _TimedOutInfo]:
    """Wait on tasks until ``budget_s`` wall-clock seconds have elapsed."""
    elapsed_s = (time.perf_counter_ns() - start) / 1e9
    remaining_budget = max(0.0, budget_s - elapsed_s)
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
    "_EXPLICIT_PATHS_BUDGET_S",
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

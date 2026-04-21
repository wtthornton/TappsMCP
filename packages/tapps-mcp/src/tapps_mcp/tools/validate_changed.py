"""``tapps_validate_changed`` orchestration and supporting helpers.

Extracted from ``server_pipeline_tools.py`` for maintainability.
Re-exported from ``server_pipeline_tools`` for backward compatibility.

The ``tapps_validate_changed`` handler looks up several symbols on
``server_pipeline_tools`` at call time (``_discover_changed_files``,
``_validate_single_file``, ``_compute_impact_analysis``,
``_write_validate_ok_marker``, ``load_settings``,
``_AUTO_DETECT_BUDGET_S``) so that tests patching those names on the
host module are honoured even though the function definitions live here.
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

from tapps_mcp.server_helpers import emit_ctx_info, success_response
from tapps_mcp.tools.validate_changed_output import (
    _SEVERITY_RANK,
    _build_per_file_results,
    _build_structured_validation_output,
    _build_validation_summary,
    _handle_no_changed_files,
    _resolve_security_depth,
)
from tapps_mcp.tools.validation_progress import (
    _PROGRESS_HEARTBEAT_INTERVAL,
    _VALIDATION_PROGRESS_FILE,
    _ProgressTracker,
    _validate_progress_heartbeat,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from tapps_core.config.settings import TappsMCPSettings
    from tapps_mcp.common.elicitation import WizardResult

_logger = structlog.get_logger(__name__)


# Maximum files to validate concurrently (balances speed vs subprocess pressure).
_VALIDATE_CONCURRENCY = 10

# STORY-101.3 — wall-clock cap on auto-detect tapps_validate_changed runs.
# Large repos can yield hundreds of changed files; without a cap, agents
# can block for minutes. Explicit file_paths mode ignores this budget.
# Kept module-level so STORY-101.6 (perf budget regression test) can tune it.
_AUTO_DETECT_BUDGET_S: float = 30.0

# Marker file for stop hook: if present and recent, hook skips "run validate" reminder.
_VALIDATE_OK_MARKER = ".tapps-mcp/sessions/last_validate_ok"


# Re-export for test patchability via ``server_pipeline_tools.X``.
__all__ = [
    "_AUTO_DETECT_BUDGET_S",
    "_PROGRESS_HEARTBEAT_INTERVAL",
    "_SEVERITY_RANK",
    "_VALIDATE_CONCURRENCY",
    "_VALIDATE_OK_MARKER",
    "_VALIDATION_PROGRESS_FILE",
    "_ProgressTracker",
    "_validate_progress_heartbeat",
]


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


async def _maybe_run_wizard(
    ctx: Context[Any, Any, Any],
    *,
    llm_engagement_level: str | None,
    platform: str,
    agent_teams: bool,
) -> WizardResult | None:
    """Run the interactive wizard if this is a true first-run.

    Returns a :class:`WizardResult` when the wizard ran and completed,
    or ``None`` when skipped.
    """
    # Skip if explicit params were provided (not all defaults)
    if llm_engagement_level is not None or platform or agent_teams:
        return None

    # Skip if existing config already present; look up load_settings via the host
    # module so tests can patch tapps_mcp.server_pipeline_tools.load_settings.
    from tapps_mcp import server_pipeline_tools as _host

    settings = _host.load_settings()
    proj = settings.project_root
    has_settings = (proj / ".claude" / "settings.json").exists()
    has_yaml = (proj / ".tapps-mcp.yaml").exists()
    if has_settings or has_yaml:
        return None

    from tapps_mcp.common.elicitation import run_init_wizard

    wizard = await run_init_wizard(ctx)
    if not wizard.completed:
        return None

    # Persist wizard answers in .tapps-mcp.yaml
    yaml_content = (
        f"llm_engagement_level: {wizard.engagement_level}\n"
        f"quality_preset: {wizard.quality_preset}\n"
    )
    yaml_path = proj / ".tapps-mcp.yaml"
    with contextlib.suppress(OSError):
        await asyncio.to_thread(yaml_path.write_text, yaml_content, encoding="utf-8")

    return wizard


def _discover_changed_files(
    file_paths: str,
    base_ref: str,
    project_root: Path,
) -> list[Path]:
    """Resolve the list of scorable files to validate.

    When *file_paths* is non-empty, parse the comma-separated list and
    validate each path. Otherwise, auto-detect changed scorable files
    via ``git diff``.

    Supports: Python (.py, .pyi), TypeScript/JavaScript (.ts, .tsx, .js, .jsx, .mjs, .cjs),
    Go (.go), and Rust (.rs) files.
    """
    from tapps_mcp.server import _validate_file_path
    from tapps_mcp.server_helpers import _is_scorable_file
    from tapps_mcp.tools.batch_validator import detect_changed_scorable_files

    paths: list[Path] = []
    if file_paths.strip():
        for raw_fp in file_paths.split(","):
            cleaned_fp = raw_fp.strip()
            if not cleaned_fp:
                continue
            if not _is_scorable_file(cleaned_fp):
                continue
            with contextlib.suppress(ValueError, FileNotFoundError):
                paths.append(_validate_file_path(cleaned_fp))
    else:
        paths = detect_changed_scorable_files(project_root, base_ref)
    return paths


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

    Supports multi-language files by using the appropriate scorer based on file extension:
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

            sec = await _run_security_scan(
                path, score, scorer.language == "python", do_security_full, quick
            )
            file_result.update(sec)
        except Exception as exc:
            file_result["errors"] = [str(exc)]
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

    Looks up ``_AUTO_DETECT_BUDGET_S`` on ``server_pipeline_tools`` at call time
    so tests patching the module-level constant are honoured.
    """
    from tapps_mcp import server_pipeline_tools as _host

    info = _TimedOutInfo()
    if not tasks:
        return [], info

    if auto_detect:
        elapsed_s = (time.perf_counter_ns() - start) / 1e9
        remaining_budget = max(0.0, _host._AUTO_DETECT_BUDGET_S - elapsed_s)
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

    raw = list(await asyncio.gather(*tasks, return_exceptions=True))
    return _collect_results(raw, uncached_paths), info


def _build_response_data(
    results: list[dict[str, Any]],
    all_passed: bool,
    total_sec: int,
    per_file_results: list[dict[str, Any]],
    summary_rows: list[str],
    summary: str,
    impact_data: dict[str, Any] | None,
) -> dict[str, Any]:
    """Assemble the base response data dict for tapps_validate_changed."""
    resp_data: dict[str, Any] = {
        "files_validated": len(results),
        "all_gates_passed": all_passed,
        "total_security_issues": total_sec,
        "per_file_results": per_file_results,
        "summary_rows": summary_rows,
        "results": results,
        "summary": summary,
    }
    if impact_data is not None:
        resp_data["impact_summary"] = impact_data
    return resp_data


async def _run_judges(
    judges: list[dict[str, Any]],
    project_root: Path,
) -> dict[str, Any]:
    """Invoke judges and return the judge-result payload (advisory by default)."""
    try:
        from tapps_core.metrics.judge import run_judges

        return await run_judges(judges, cwd=project_root)
    except Exception:
        _logger.debug("judge_run_failed", exc_info=True)
        return {"judge_results": [], "judges_passed": False}


def _append_timeout_hint(
    resp: dict[str, Any],
    files_remaining: list[Path],
) -> None:
    """Inject an auto-detect-budget hint into the response's next_steps."""
    from tapps_mcp import server_pipeline_tools as _host

    data = resp.get("data", {})
    sample = ",".join(str(p) for p in files_remaining[:10])
    hint = (
        f"Auto-detect exceeded {_host._AUTO_DETECT_BUDGET_S:.0f}s budget with "
        f"{len(files_remaining)} files unvalidated. Finish with explicit "
        f'paths: tapps_validate_changed(file_paths="{sample}")'
    )
    existing = list(data.get("next_steps") or [])
    data["next_steps"] = [hint, *existing][:5]


async def tapps_validate_changed(
    file_paths: str = "",
    base_ref: str = "HEAD",
    preset: str = "standard",
    include_security: bool = True,
    quick: bool = True,
    security_depth: str = "basic",
    include_impact: bool = True,
    correlation_id: str = "",
    judges: list[dict[str, Any]] | None = None,
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    """REQUIRED before declaring multi-file work complete.
    Detects changed scorable files (via git diff) or accepts an explicit
    comma-separated list. Runs score + quality gate on each file; security
    scan only for Python files when quick=False or security_depth='full'
    (default quick=True does not run security). Skipping means quality
    issues in changed files go undetected.

    Supports multi-language scoring:
    - Python (.py, .pyi)
    - TypeScript/JavaScript (.ts, .tsx, .js, .jsx, .mjs, .cjs)
    - Go (.go)
    - Rust (.rs)

    If this tool is unavailable or rejected, use tapps_quick_check on
    individual changed files as a fallback.

    Default is quick=True (ruff-only, typically under 10s). Pass quick=False
    for full validation (ruff, mypy, bandit, radon, vulture per file, 1-5+ min).
    To include security scan in default quick mode, pass security_depth='full'.

    Args:
        file_paths: Comma-separated file paths (empty = auto-detect via git diff).
        base_ref: Git ref to diff against (default: HEAD for unstaged changes).
        preset: Quality gate preset - "standard", "strict", or "framework".
        include_security: Whether to run security scan on each file (ignored if quick=True).
        quick: If True (default), ruff-only scoring for speed. If False, full validation.
        security_depth: Security scan depth - "basic" (default) or "full". When "full",
            security scan runs even in quick mode.
        include_impact: Whether to run impact analysis on changed files (default: True).
        correlation_id: Optional caller-provided ID echoed in the response for traceability.
            Empty string (default) means no correlation ID is included in the response.
        judges: Optional list of judge dicts. Each judge has: type (pytest|grep|exists),
            target (str), expect (str, regex for grep), description (str), blocking (bool).
            Judges run after the quality gate and results appear under judge_results.
            blocking=False (default) means failures are advisory only.
        ctx: Optional MCP context (injected by host); used for progress notifications.
    """
    # Late imports through the host module so tests can patch these names.
    from tapps_mcp import server_pipeline_tools as _host
    from tapps_mcp.server import _record_call, _record_execution, _with_nudges
    from tapps_mcp.server_helpers import ensure_session_initialized
    from tapps_mcp.tools.batch_validator import MAX_BATCH_FILES

    start = time.perf_counter_ns()
    _record_call("tapps_validate_changed")

    settings = _host.load_settings()
    paths = _host._discover_changed_files(file_paths, base_ref, settings.project_root)

    if not paths:
        return _handle_no_changed_files(
            start,
            settings,
            _record_execution,
            _with_nudges,
            explicit_paths=bool(file_paths.strip()),
            base_ref=base_ref,
            correlation_id=correlation_id,
        )

    capped = len(paths) > MAX_BATCH_FILES
    extra_count = len(paths) - MAX_BATCH_FILES if capped else 0
    paths = paths[:MAX_BATCH_FILES]
    total_files = len(paths)

    tracker = _ProgressTracker(total=total_files)
    tracker.init_sidecar(settings.project_root)
    stop_progress = asyncio.Event()
    progress_task = _start_progress_reporting(ctx, total_files, start, stop_progress, tracker)

    auto_detect = not file_paths.strip()
    cached_results, uncached_paths = _partition_by_cache(paths)

    try:
        await ensure_session_initialized()
        _maybe_warm_dependency_cache(settings, quick)

        sem = asyncio.Semaphore(_VALIDATE_CONCURRENCY)
        do_security_full = _resolve_security_depth(security_depth, include_security, quick)

        tasks = [
            asyncio.create_task(
                _host._validate_single_file(p, preset, quick, do_security_full, sem, tracker, ctx)
            )
            for p in uncached_paths
        ]

        task_results, timeout_info = await _run_tasks_with_budget(
            tasks, uncached_paths, start, auto_detect
        )
    except Exception as exc:
        _record_call("tapps_validate_changed", success=False)
        tracker.finalize_error(str(exc))
        raise
    finally:
        if progress_task is not None:
            stop_progress.set()
            progress_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await progress_task

    results = [*task_results, *cached_results]
    all_passed = all(r.get("gate_passed", False) for r in results)
    total_sec = sum(r.get("security_issues", 0) for r in results)

    impact_data = (
        _host._compute_impact_analysis(paths, settings.project_root)
        if include_impact and paths
        else None
    )

    summary = _build_validation_summary(results, quick, capped, extra_count)
    per_file_results, summary_rows = _build_per_file_results(results)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    if not all_passed:
        _record_call("tapps_validate_changed", success=False)
    _record_execution("tapps_validate_changed", start, gate_passed=all_passed)
    tracker.finalize(all_passed, summary, elapsed_ms)
    if all_passed:
        _host._write_validate_ok_marker(settings.project_root)

    resp_data = _build_response_data(
        results, all_passed, total_sec, per_file_results, summary_rows, summary, impact_data
    )

    # EPIC-102: auto-recall of relevant insights (opt-in)
    if settings.memory.recall_on_validate:
        from tapps_mcp.tools.insight_recall import recall_insights_for_validate

        recall_data = recall_insights_for_validate(paths, settings.project_root)
        resp_data.update(recall_data)
    if correlation_id.strip():
        resp_data["correlation_id"] = correlation_id.strip()
    if timeout_info.timed_out:
        resp_data["timed_out"] = True
        resp_data["files_remaining"] = len(timeout_info.files_remaining)
        resp_data["files_remaining_paths"] = [str(p) for p in timeout_info.files_remaining]
        resp_data["auto_detect_budget_s"] = _host._AUTO_DETECT_BUDGET_S

    # Judge pattern (TAP-478) — run after quality gate, advisory by default
    if judges:
        resp_data.update(await _run_judges(judges, settings.project_root))

    resp = success_response("tapps_validate_changed", elapsed_ms, resp_data)
    _build_structured_validation_output(results, all_passed, security_depth, impact_data, resp)
    resp = _with_nudges("tapps_validate_changed", resp)
    if timeout_info.timed_out:
        _append_timeout_hint(resp, timeout_info.files_remaining)
    return resp

"""Pipeline orchestration and validation tool handlers for TappsMCP.

Functions are defined at module level (importable for tests) and
registered on the ``mcp`` instance via :func:`register`.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from mcp.server.fastmcp import (
    Context,  # noqa: TC002 — runtime import required for FastMCP annotation resolution
)
from mcp.types import ToolAnnotations

from tapps_core.config.settings import load_settings
from tapps_mcp.server_helpers import error_response, success_response

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from tapps_core.config.settings import TappsMCPSettings
    from tapps_mcp.scoring.scorer import CodeScorer

_logger = structlog.get_logger(__name__)

# Maximum files to validate concurrently (balances speed vs subprocess pressure).
_VALIDATE_CONCURRENCY = 10

# Track whether auto-GC has already run this session.
_session_gc_done: bool = False


def _reset_session_gc_flag() -> None:
    """Reset the auto-GC flag (for testing)."""
    global _session_gc_done  # noqa: PLW0603
    _session_gc_done = False

# Prevent garbage collection of fire-and-forget background tasks.
# Without strong references, asyncio tasks may be collected before completion.
_background_tasks: set[asyncio.Task[Any]] = set()

_ANNOTATIONS_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


_PROGRESS_HEARTBEAT_INTERVAL = 5  # seconds between progress notifications

# Marker file for stop hook: if present and recent, hook skips "run validate" reminder.
_VALIDATE_OK_MARKER = ".tapps-mcp/sessions/last_validate_ok"

# Severity ranking for impact analysis aggregation.
_SEVERITY_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0}


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
) -> object | None:
    """Run the interactive wizard if this is a true first-run.

    Returns a :class:`WizardResult` when the wizard ran and completed,
    or ``None`` when skipped.
    """
    # Skip if explicit params were provided (not all defaults)
    if llm_engagement_level is not None or platform or agent_teams:
        return None

    # Skip if existing config already present
    settings = load_settings()
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
        yaml_path.write_text(yaml_content, encoding="utf-8")

    return wizard


async def _validate_progress_heartbeat(
    ctx: object,
    total_files: int,
    start_ns: int,
    stop_event: asyncio.Event,
) -> None:
    """Send progress notifications every _PROGRESS_HEARTBEAT_INTERVAL seconds.
    Stops when stop_event is set. No-op if ctx has no report_progress.
    """
    report = getattr(ctx, "report_progress", None)
    if not callable(report):
        return
    while True:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=_PROGRESS_HEARTBEAT_INTERVAL)
        if stop_event.is_set():
            return
        elapsed_sec = (time.perf_counter_ns() - start_ns) / 1_000_000_000.0
        with contextlib.suppress(Exception):
            await report(
                progress=elapsed_sec,
                total=None,
                message=f"Validating {total_files} files... (in progress)",
            )


def _discover_changed_files(
    file_paths: str,
    base_ref: str,
    project_root: Path,
) -> list[Path]:
    """Resolve the list of Python files to validate.

    When *file_paths* is non-empty, parse the comma-separated list and
    validate each path.  Otherwise, auto-detect changed ``.py`` files
    via ``git diff``.
    """
    from tapps_mcp.server import _validate_file_path
    from tapps_mcp.tools.batch_validator import detect_changed_python_files

    paths: list[Path] = []
    if file_paths.strip():
        for raw_fp in file_paths.split(","):
            cleaned_fp = raw_fp.strip()
            if not cleaned_fp or not cleaned_fp.endswith(".py"):
                continue
            with contextlib.suppress(ValueError, FileNotFoundError):
                paths.append(_validate_file_path(cleaned_fp))
    else:
        paths = detect_changed_python_files(project_root, base_ref)
    return paths


async def _validate_single_file(
    path: Path,
    scorer: CodeScorer,
    preset: str,
    quick: bool,
    do_security_full: bool,
    sem: asyncio.Semaphore,
) -> dict[str, Any]:
    """Score and optionally security-scan a single file under concurrency limit."""
    from tapps_mcp.gates.evaluator import evaluate_gate

    async with sem:
        file_result: dict[str, Any] = {"file_path": str(path)}
        try:
            if quick:
                score = await asyncio.to_thread(scorer.score_file_quick, path)
            else:
                score = await scorer.score_file(path)
            file_result["overall_score"] = round(score.overall_score, 2)

            gate = evaluate_gate(score, preset=preset)
            file_result["gate_passed"] = gate.passed
            if gate.failures:
                file_result["gate_failures"] = [f.model_dump() for f in gate.failures]

            if do_security_full:
                from tapps_mcp.security.secret_scanner import SecretScanner

                secret_result = SecretScanner().scan_file(str(path))
                bandit_count = len(score.security_issues)
                secret_count = secret_result.total_findings
                bandit_crit_high = sum(
                    1 for i in score.security_issues if i.severity in ("critical", "high")
                )
                file_result["security_passed"] = (
                    bandit_crit_high + secret_result.high_severity
                ) == 0
                file_result["security_issues"] = bandit_count + secret_count
            elif quick:
                file_result["security_passed"] = True
                file_result["security_issues"] = 0
        except Exception as exc:
            file_result["errors"] = [str(exc)]
        return file_result


def _compute_impact_analysis(
    paths: list[Path],
    project_root: Path,
) -> dict[str, Any] | None:
    """Build impact analysis data for the given file paths.

    Returns a summary dict or ``None`` if impact analysis is not requested.
    On failure, returns ``{"error": "impact analysis failed"}``.
    """
    try:
        from tapps_mcp.project.impact_analyzer import analyze_impact, build_import_graph

        import_graph = build_import_graph(project_root)

        impact_results: list[dict[str, Any]] = []
        for p in paths:
            try:
                impact_report = analyze_impact(p, project_root, graph=import_graph)
                impact_results.append({
                    "file": str(p),
                    "severity": impact_report.severity,
                    "direct_dependents": len(impact_report.direct_dependents),
                    "transitive_dependents": len(impact_report.transitive_dependents),
                    "test_files": len(impact_report.test_files),
                })
            except Exception:
                _logger.debug("impact_analysis_file_failed", file=str(p), exc_info=True)
                impact_results.append({"file": str(p), "severity": "unknown", "error": True})

        max_severity = "low"
        for ir in impact_results:
            s = ir.get("severity", "low")
            if _SEVERITY_RANK.get(s, 0) > _SEVERITY_RANK.get(max_severity, 0):
                max_severity = s

        total_affected = sum(
            ir.get("direct_dependents", 0) + ir.get("transitive_dependents", 0)
            for ir in impact_results
        )
        return {
            "max_severity": max_severity,
            "total_affected_files": total_affected,
            "per_file": impact_results,
        }
    except Exception:
        _logger.debug("impact_analysis_failed", exc_info=True)
        return {"error": "impact analysis failed"}


def _build_structured_validation_output(
    results: list[dict[str, Any]],
    all_passed: bool,
    security_depth: str,
    impact_data: dict[str, Any] | None,
    resp: dict[str, Any],
) -> None:
    """Attach structured content to the response dict (best-effort)."""
    try:
        from tapps_mcp.common.output_schemas import (
            FileValidationResult,
            ValidateChangedOutput,
        )

        file_results = [
            FileValidationResult(
                file_path=r.get("file_path", ""),
                score=r.get("overall_score", 0.0),
                gate_passed=r.get("gate_passed", False),
                security_passed=r.get("security_passed", True),
            )
            for r in results
        ]
        failed_count = sum(1 for r in results if not r.get("gate_passed", False))
        structured = ValidateChangedOutput(
            files=file_results,
            overall_passed=all_passed,
            total_files=len(results),
            passed_count=len(results) - failed_count,
            failed_count=failed_count,
            security_depth=security_depth,
            impact_summary=impact_data,
        )
        resp["structuredContent"] = structured.to_structured_content()
    except Exception:
        _logger.debug("structured_output_failed: tapps_validate_changed", exc_info=True)


async def tapps_validate_changed(
    file_paths: str = "",
    base_ref: str = "HEAD",
    preset: str = "standard",
    include_security: bool = True,
    quick: bool = True,
    security_depth: str = "basic",
    include_impact: bool = True,
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    """REQUIRED before declaring work complete on multi-file changes.
    Detects changed Python files (via git diff) or accepts an explicit
    comma-separated list. Runs score + quality gate (+ optional security) on each
    file. Skipping means quality issues in changed files go undetected.

    If this tool is unavailable or rejected, use tapps_quick_check on
    individual changed files as a fallback.

    Default is quick=True (ruff-only, typically under 10s). Pass quick=False
    for full validation (ruff, mypy, bandit, radon, vulture per file, 1-5+ min).

    Args:
        file_paths: Comma-separated file paths (empty = auto-detect via git diff).
        base_ref: Git ref to diff against (default: HEAD for unstaged changes).
        preset: Quality gate preset - "standard", "strict", or "framework".
        include_security: Whether to run security scan on each file (ignored if quick=True).
        quick: If True (default), ruff-only scoring for speed. If False, full validation.
        security_depth: Security scan depth - "basic" (default) or "full". When "full",
            security scan runs even in quick mode.
        include_impact: Whether to run impact analysis on changed files (default: True).
        ctx: Optional MCP context (injected by host); used for progress notifications.
    """
    from tapps_mcp.server import _record_call, _record_execution, _with_nudges
    from tapps_mcp.server_helpers import _get_scorer, ensure_session_initialized
    from tapps_mcp.tools.batch_validator import MAX_BATCH_FILES, format_batch_summary

    start = time.perf_counter_ns()
    _record_call("tapps_validate_changed")

    settings = load_settings()
    paths = _discover_changed_files(file_paths, base_ref, settings.project_root)

    if not paths:
        return _handle_no_changed_files(start, settings, _record_execution, _with_nudges)

    capped = len(paths) > MAX_BATCH_FILES
    extra_count = len(paths) - MAX_BATCH_FILES if capped else 0
    paths = paths[:MAX_BATCH_FILES]
    total_files = len(paths)

    stop_progress = asyncio.Event()
    progress_task = _start_progress_reporting(ctx, total_files, start, stop_progress)

    try:
        await ensure_session_initialized()
        _maybe_warm_dependency_cache(settings, quick)

        scorer = _get_scorer()
        sem = asyncio.Semaphore(_VALIDATE_CONCURRENCY)
        do_security_full = (security_depth == "full") or (include_security and not quick)

        raw_results = await asyncio.gather(
            *[
                _validate_single_file(p, scorer, preset, quick, do_security_full, sem)
                for p in paths
            ],
            return_exceptions=True,
        )
    finally:
        if progress_task is not None:
            stop_progress.set()
            progress_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await progress_task

    results = _collect_results(raw_results, paths)
    all_passed = all(r.get("gate_passed", False) for r in results)
    total_sec = sum(r.get("security_issues", 0) for r in results)

    impact_data = (
        _compute_impact_analysis(paths, settings.project_root)
        if include_impact and paths
        else None
    )

    summary = format_batch_summary(results)
    if quick:
        summary = f"[Quick mode - ruff only] {summary}"
    if capped:
        summary += (
            f" ({extra_count} additional files not validated"
            f" - cap {MAX_BATCH_FILES})"
        )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_validate_changed", start, gate_passed=all_passed)
    if all_passed:
        _write_validate_ok_marker(settings.project_root)

    resp_data: dict[str, Any] = {
        "files_validated": len(results),
        "all_gates_passed": all_passed,
        "total_security_issues": total_sec,
        "results": results,
        "summary": summary,
    }
    if impact_data is not None:
        resp_data["impact_summary"] = impact_data

    resp = success_response("tapps_validate_changed", elapsed_ms, resp_data)
    _build_structured_validation_output(results, all_passed, security_depth, impact_data, resp)
    return _with_nudges("tapps_validate_changed", resp)


def _handle_no_changed_files(
    start: int,
    settings: TappsMCPSettings,
    record_execution: Any,  # noqa: ANN401
    with_nudges: Any,  # noqa: ANN401
) -> dict[str, Any]:
    """Return early response when no changed Python files are found."""
    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    def _deferred_record() -> None:
        record_execution("tapps_validate_changed", start)

    task = asyncio.create_task(asyncio.to_thread(_deferred_record))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    _write_validate_ok_marker(settings.project_root)
    resp = success_response(
        "tapps_validate_changed",
        elapsed_ms,
        {
            "files_validated": 0,
            "all_gates_passed": True,
            "total_security_issues": 0,
            "results": [],
            "summary": "No changed Python files found.",
        },
    )
    return with_nudges("tapps_validate_changed", resp)


def _start_progress_reporting(
    ctx: Context[Any, Any, Any] | None,
    total_files: int,
    start: int,
    stop_event: asyncio.Event,
) -> asyncio.Task[None] | None:
    """Start the progress heartbeat task if context supports it."""
    if ctx is None or total_files <= 0:
        return None
    report = getattr(ctx, "report_progress", None)
    if callable(report):
        with contextlib.suppress(Exception):
            # Fire initial progress via background task (store ref to prevent GC)
            init_task = asyncio.create_task(
                _report_initial_progress(report, total_files)
            )
            _background_tasks.add(init_task)
            init_task.add_done_callback(_background_tasks.discard)
    return asyncio.create_task(
        _validate_progress_heartbeat(ctx, total_files, start, stop_event),
    )


async def _report_initial_progress(
    report: Any,  # noqa: ANN401
    total_files: int,
) -> None:
    """Send the initial progress=0 notification."""
    with contextlib.suppress(Exception):
        await report(
            progress=0.0,
            total=None,
            message=f"Validating {total_files} files...",
        )


def _maybe_warm_dependency_cache(
    settings: TappsMCPSettings,
    quick: bool,
) -> None:
    """Warm dependency cache in background when empty (does not block)."""
    if not settings.dependency_scan_enabled or quick:
        return
    from tapps_mcp.tools.dependency_scan_cache import get_dependency_findings

    if not get_dependency_findings(str(settings.project_root)):
        task = asyncio.create_task(_warm_dependency_cache(settings))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)


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
            results.append(raw)  # type: ignore[arg-type]
    return results


async def _warm_dependency_cache(
    settings: TappsMCPSettings,
) -> None:
    """Best-effort background task to warm the dependency scan cache.

    Available for use by :func:`tapps_validate_changed` or on first
    :func:`tapps_score_file` so subsequent scoring can apply vulnerability
    penalties. Not called from :func:`tapps_session_start` (session start
    is kept lightweight). Failures are silently ignored.
    """
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


def _maybe_auto_gc(
    store: object,
    current_count: int,
    settings: object,
) -> dict[str, Any] | None:
    """Run garbage collection if memory usage exceeds the configured threshold.

    Returns a summary dict when GC ran, or ``None`` if skipped.
    Only runs once per session (guarded by ``_session_gc_done``).
    """
    global _session_gc_done  # noqa: PLW0603

    if _session_gc_done:
        return None

    mem_settings = getattr(settings, "memory", None)
    if mem_settings is None:
        return None

    gc_enabled = getattr(mem_settings, "gc_enabled", True)
    if not gc_enabled:
        return None

    max_memories = getattr(mem_settings, "max_memories", 500)
    threshold = getattr(mem_settings, "gc_auto_threshold", 0.8)
    trigger_count = int(max_memories * threshold)

    if current_count <= trigger_count:
        return None

    _session_gc_done = True

    try:
        from tapps_core.memory.decay import DecayConfig
        from tapps_core.memory.gc import MemoryGarbageCollector

        config = DecayConfig()
        gc = MemoryGarbageCollector(config)

        snapshot = store.snapshot()  # type: ignore[union-attr]
        candidates = gc.identify_candidates(snapshot.entries)

        archived_keys: list[str] = []
        for candidate in candidates:
            deleted = store.delete(candidate.key)  # type: ignore[union-attr]
            if deleted:
                archived_keys.append(candidate.key)

        remaining = store.count()  # type: ignore[union-attr]

        _logger.info(
            "session_auto_gc_completed",
            evicted=len(archived_keys),
            remaining=remaining,
            threshold=threshold,
        )

        return {
            "ran": True,
            "evicted": len(archived_keys),
            "remaining": remaining,
        }
    except Exception:
        _logger.debug("session_auto_gc_failed", exc_info=True)
        return {"ran": False, "error": "auto-gc failed"}


def _process_session_capture(
    project_root: Path,
    store: Any,  # noqa: ANN401
) -> dict[str, Any] | None:
    """Check for and process a session-capture.json left by the Stop hook.

    If the file exists, reads it, persists the data to memory, deletes
    the capture file, and returns a summary dict.  Returns ``None`` if
    no capture file exists.  Failures are logged and silently ignored.
    """
    import json as _json

    capture_path = project_root / ".tapps-mcp" / "session-capture.json"
    if not capture_path.exists():
        return None

    try:
        raw = capture_path.read_text(encoding="utf-8")
        data = _json.loads(raw)
        date_str = data.get("date", "unknown")
        validated = data.get("validated", False)
        files_edited = data.get("files_edited", 0)

        value = (
            f"Session on {date_str}: "
            f"{'validated' if validated else 'not validated'}, "
            f"{files_edited} Python file(s) edited."
        )
        store.save(
            key=f"session-capture.{date_str}",
            value=value,
            tier="context",
            source="system",
            source_agent="tapps-memory-capture-hook",
            scope="project",
            tags=["session-capture", "auto"],
        )

        capture_path.unlink(missing_ok=True)

        _logger.info(
            "session_capture_processed",
            date=date_str,
            validated=validated,
            files_edited=files_edited,
        )
        return {
            "date": date_str,
            "validated": validated,
            "files_edited": files_edited,
        }
    except Exception:
        _logger.debug("session_capture_processing_failed", exc_info=True)
        # Clean up even on failure to avoid re-processing bad data
        with contextlib.suppress(OSError):
            capture_path.unlink(missing_ok=True)
        return None


async def tapps_session_start(
    project_root: str = "",
) -> dict[str, Any]:
    """REQUIRED as the FIRST call in every session. Returns server info
    (version, checkers, configuration). Call :func:`tapps_project_profile`
    when you need project context (tech stack, type, CI/Docker/tests).

    Args:
        project_root: Unused; reserved for future use. Server uses configured root.
    """
    from tapps_mcp.server import (
        _record_call,
        _record_execution,
        _server_info_async,
        _with_nudges,
    )

    start = time.perf_counter_ns()
    _record_call("tapps_session_start")

    info = await _server_info_async()

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_session_start", start)

    # Memory status (lazy, non-blocking)
    memory_status: dict[str, Any] = {"enabled": False}
    memory_gc_result: dict[str, Any] | None = None
    session_capture_result: dict[str, Any] | None = None
    try:
        settings = load_settings()
        if settings.memory.enabled:
            from tapps_mcp.server_helpers import _get_memory_store

            mem_store = _get_memory_store()
            if mem_store is not None:
                snapshot = mem_store.snapshot()
                contradicted_count = sum(
                    1 for entry in snapshot.entries if entry.contradicted
                )
                memory_status = {
                    "enabled": True,
                    "total": snapshot.total_count,
                    "stale": 0,
                    "contradicted": contradicted_count,
                }

                # Auto-GC: run once per session when usage exceeds threshold
                memory_gc_result = _maybe_auto_gc(
                    mem_store, snapshot.total_count, settings,
                )

                # Process session capture from previous Stop hook (Epic 34.5)
                session_capture_result = _process_session_capture(
                    settings.project_root, mem_store,
                )
    except Exception:
        _logger.debug("memory_status_check_failed", exc_info=True)

    _project_profile_hint = (
        "Call tapps_project_profile when you need project context"
        " (tech stack, type, CI/Docker/tests)."
    )
    data: dict[str, Any] = {
        "server": info["data"]["server"],
        "configuration": info["data"]["configuration"],
        "installed_checkers": info["data"]["installed_checkers"],
        "diagnostics": info["data"]["diagnostics"],
        "quick_start": info["data"].get("quick_start", []),
        "critical_rules": info["data"].get("critical_rules", []),
        "pipeline": info["data"]["pipeline"],
        "memory_status": memory_status,
        "memory_gc": memory_gc_result,
        "session_capture": session_capture_result,
        "project_profile": None,
        "project_profile_hint": _project_profile_hint,
    }

    resp = success_response("tapps_session_start", elapsed_ms, data)

    # Attach structured output (no project fields; call tapps_project_profile for those)
    try:
        from tapps_mcp.common.output_schemas import SessionStartOutput

        checker_names = [
            c.get("name", "") if isinstance(c, dict) else getattr(c, "name", "")
            for c in info["data"].get("installed_checkers", [])
        ]
        structured = SessionStartOutput(
            server_version=info["data"]["server"].get("version", ""),
            project_root=info["data"]["configuration"].get("project_root", ""),
            project_type=None,
            quality_preset=info["data"]["configuration"].get(
                "quality_preset", "standard"
            ),
            installed_checkers=[n for n in checker_names if n],
            has_ci=False,
            has_docker=False,
            has_tests=False,
        )
        resp["structuredContent"] = structured.to_structured_content()
    except Exception:
        _logger.debug("structured_output_failed: tapps_session_start", exc_info=True)

    from tapps_mcp.server_helpers import mark_session_initialized

    mark_session_initialized({
        "project_root": info["data"]["configuration"].get("project_root", ""),
        "quality_preset": info["data"]["configuration"].get(
            "quality_preset", "standard"
        ),
        "auto_initialized": False,
        "project_profile": None,
    })

    return _with_nudges("tapps_session_start", resp, {})


async def tapps_init(
    create_handoff: bool = True,
    create_runlog: bool = True,
    create_agents_md: bool = True,
    create_tech_stack_md: bool = True,
    platform: str = "",
    verify_server: bool = True,
    install_missing_checkers: bool = False,
    warm_cache_from_tech_stack: bool = True,
    warm_expert_rag_from_tech_stack: bool = True,
    overwrite_platform_rules: bool = False,
    overwrite_agents_md: bool = False,
    agent_teams: bool = False,
    memory_capture: bool = False,
    dry_run: bool = False,
    verify_only: bool = False,
    llm_engagement_level: str | None = None,
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    """Bootstrap TAPPS pipeline in the current project.

    Verifies server info and optionally installs missing checkers (ruff, mypy,
    bandit, radon). Creates handoff, runlog, AGENTS.md, and TECH_STACK.md.
    Optionally warms the Context7 cache from the detected tech stack.
    Optionally generates platform-specific rule files for Claude Code or Cursor.

    On first run (no existing ``.claude/settings.json`` or ``.tapps-mcp.yaml``),
    an interactive 5-question wizard is presented via MCP elicitation (quality
    preset, engagement level, agent teams, skill tier, prompt hooks). Answers
    are persisted in ``.tapps-mcp.yaml``. The wizard is skipped when explicit
    parameters are provided or when the client does not support elicitation.

    Call once per project to set up the pipeline workflow.

    Duration: Full init can take 10-35+ seconds (profile, templates, cache/RAG
    warming). For timeout-prone MCP clients, use dry_run or verify_only first,
    or set warm_cache_from_tech_stack=False and warm_expert_rag_from_tech_stack=False
    for a faster init (~5-15s). See docs/MCP_CLIENT_TIMEOUTS.md for timeout guidance.

    Args:
        create_handoff: Create docs/TAPPS_HANDOFF.md template.
        create_runlog: Create docs/TAPPS_RUNLOG.md template.
        create_agents_md: Create AGENTS.md with AI assistant workflow (if missing).
        create_tech_stack_md: Create or update TECH_STACK.md from project profile.
        platform: Generate platform rules. One of: "claude", "cursor", "".
        verify_server: Verify server info and installed checkers.
        install_missing_checkers: Attempt to pip-install missing checkers (opt-in).
        warm_cache_from_tech_stack: Pre-fetch docs for tech stack libraries into cache.
        warm_expert_rag_from_tech_stack: Pre-build expert RAG indices for relevant domains.
        overwrite_platform_rules: When ``True``, refresh platform rule files even if
            they already exist (useful when templates are upgraded).
        overwrite_agents_md: When ``True``, replace AGENTS.md entirely with the latest
            template. When ``False`` (default), validate and smart-merge missing
            sections/tools.
        agent_teams: When ``True`` and platform is ``"claude"``, generate Agent Teams
            hooks (TeammateIdle, TaskCompleted) for quality watchdog teammate.
        memory_capture: When ``True`` and platform is ``"claude"``, generate a Stop
            hook that captures session quality data for memory persistence.
        dry_run: When ``True``, compute and return what would be created without
            writing files or warming caches. Keeps dry_run lightweight (~2-5s).
        verify_only: When ``True``, run only server verification and return (~1-3s).
            Use for quick connectivity/checker checks without creating files.
        llm_engagement_level: When set, use this level (high/medium/low) for
            AGENTS.md and platform rules. When ``None``, use config/settings.
    """
    from tapps_mcp.server import _record_call, _record_execution, _with_nudges

    start = time.perf_counter_ns()
    _record_call("tapps_init")

    # If context available, try elicitation confirmation (skip for verify_only/dry_run)
    if ctx is not None and not verify_only and not dry_run:
        from tapps_mcp.common.elicitation import elicit_init_confirmation

        settings_peek = load_settings()
        confirmed = await elicit_init_confirmation(ctx, str(settings_peek.project_root))
        if confirmed is False:
            elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
            _record_execution("tapps_init", start, status="cancelled")
            return success_response(
                "tapps_init",
                elapsed_ms,
                {"cancelled": True, "message": "tapps_init cancelled - no files were written."},
            )
        # confirmed is True or None (unsupported) - proceed normally

    # Interactive wizard (Epic 37.1): triggers on true first-run with no
    # explicit config and no explicit params, when elicitation is available.
    if ctx is not None and not verify_only and not dry_run:
        wizard_answers = await _maybe_run_wizard(
            ctx,
            llm_engagement_level=llm_engagement_level,
            platform=platform,
            agent_teams=agent_teams,
        )
        if wizard_answers is not None:
            llm_engagement_level = wizard_answers.engagement_level
            agent_teams = wizard_answers.agent_teams
            if not platform:
                platform = "claude"

    from tapps_mcp.pipeline.init import bootstrap_pipeline

    settings = load_settings()
    # Run in thread to avoid blocking the event loop - bootstrap_pipeline
    # is sync and may run subprocesses, file I/O, and cache warming.
    result = await asyncio.to_thread(
        bootstrap_pipeline,
        settings.project_root,
        create_handoff=create_handoff,
        create_runlog=create_runlog,
        create_agents_md=create_agents_md,
        create_tech_stack_md=create_tech_stack_md,
        platform=platform,
        verify_server=verify_server,
        install_missing_checkers=install_missing_checkers,
        warm_cache_from_tech_stack=warm_cache_from_tech_stack,
        warm_expert_rag_from_tech_stack=warm_expert_rag_from_tech_stack,
        overwrite_platform_rules=overwrite_platform_rules,
        overwrite_agents_md=overwrite_agents_md,
        agent_teams=agent_teams,
        memory_capture=memory_capture,
        dry_run=dry_run,
        verify_only=verify_only,
        llm_engagement_level=llm_engagement_level,
    )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution(
        "tapps_init",
        start,
        status="success" if not result["errors"] else "failed",
    )

    resp = success_response("tapps_init", elapsed_ms, result)
    resp["success"] = not result["errors"]
    return _with_nudges("tapps_init", resp)


def tapps_upgrade(
    platform: str = "",
    force: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Upgrade all TappsMCP-generated files after a version update.

    Validates and refreshes AGENTS.md, platform rules, hooks, agents,
    skills, and settings. Preserves custom command paths in MCP configs
    (e.g. PyInstaller exe paths are never overwritten).

    Creates a timestamped backup of all files that will be overwritten
    before making changes. Backups are stored in ``.tapps-mcp/backups/``
    and can be restored with ``tapps-mcp rollback`` (CLI) or
    ``tapps-mcp rollback --list`` to view available backups.

    Use ``dry_run=True`` to preview what would change.

    Args:
        platform: Target platform - "claude", "cursor", "both", or "" for auto-detection.
        force: If True, overwrite all generated files without prompting.
        dry_run: If True, show what would be updated without making changes.
    """
    from tapps_mcp.pipeline.upgrade import upgrade_pipeline
    from tapps_mcp.server import _record_call, _record_execution, _with_nudges

    start = time.perf_counter_ns()
    _record_call("tapps_upgrade")

    settings = load_settings()
    result = upgrade_pipeline(
        settings.project_root,
        platform=platform,
        force=force,
        dry_run=dry_run,
    )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution(
        "tapps_upgrade",
        start,
        status="success" if result.get("success") else "failed",
    )

    resp = success_response("tapps_upgrade", elapsed_ms, result)
    return _with_nudges("tapps_upgrade", resp)


def tapps_set_engagement_level(level: str) -> dict[str, Any]:
    """Set the LLM engagement level (high / medium / low) for the project.

    Writes or updates ``llm_engagement_level`` in the project's ``.tapps-mcp.yaml``.
    Use when the user asks to change enforcement intensity (e.g. \"set tappsmcp to high\"
    or \"make quality checks optional\").

    Args:
        level: One of ``\"high\"`` (mandatory), ``\"medium\"`` (balanced),
            ``\"low\"`` (optional guidance).
    """
    import yaml

    from tapps_core.security.path_validator import PathValidator
    from tapps_mcp.server import _record_call, _record_execution, _with_nudges

    start = time.perf_counter_ns()
    _record_call("tapps_set_engagement_level")

    valid = ("high", "medium", "low")
    if level not in valid:
        elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
        _record_execution("tapps_set_engagement_level", start, status="failed")
        return error_response(
            "tapps_set_engagement_level",
            elapsed_ms,
            f"Invalid level {level!r}. Use one of: {', '.join(valid)}",
        )

    settings = load_settings()
    root = Path(settings.project_root)
    validator = PathValidator(root)
    config_path = validator.validate_write_path(".tapps-mcp.yaml")

    data: dict[str, Any] = {}
    if config_path.exists():
        try:
            with config_path.open(encoding="utf-8-sig") as f:
                data = yaml.safe_load(f) or {}
        except Exception as e:
            elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
            _record_execution(
                "tapps_set_engagement_level", start, status="failed"
            )
            return error_response(
                "tapps_set_engagement_level",
                elapsed_ms,
                f"Could not read existing .tapps-mcp.yaml: {e}",
            )
    if not isinstance(data, dict):
        data = {}

    data["llm_engagement_level"] = level
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    except OSError as e:
        elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
        _record_execution(
            "tapps_set_engagement_level", start, status="failed"
        )
        return error_response(
            "tapps_set_engagement_level",
            elapsed_ms,
            f"Could not write .tapps-mcp.yaml: {e}",
        )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_set_engagement_level", start)

    next_step = (
        "Run tapps_init with overwrite_agents_md=True (and platform if needed) "
        "to regenerate AGENTS.md and platform rules with the new level."
    )
    msg = f"Engagement level set to {level!r}. {next_step}"
    resp = success_response(
        "tapps_set_engagement_level",
        elapsed_ms,
        {"level": level, "message": msg},
    )
    return _with_nudges("tapps_set_engagement_level", resp)


def tapps_doctor(
    project_root: str = "",
) -> dict[str, Any]:
    """Diagnose TappsMCP configuration and connectivity.

    Checks binary availability, MCP configs, platform rules, generated
    files (AGENTS.md, settings), hooks, and installed quality tools.

    Returns structured results with per-check pass/fail status and
    remediation hints for any failures.

    Args:
        project_root: Project root path (default: server's configured root).
    """
    from tapps_mcp.distribution.doctor import run_doctor_structured
    from tapps_mcp.server import _record_call, _record_execution, _with_nudges

    start = time.perf_counter_ns()
    _record_call("tapps_doctor")

    settings = load_settings()
    root = project_root or str(settings.project_root)

    result = run_doctor_structured(project_root=root)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_doctor", start)

    resp = success_response("tapps_doctor", elapsed_ms, result)
    return _with_nudges("tapps_doctor", resp)


def register(mcp_instance: FastMCP) -> None:
    """Register pipeline/validation tools on *mcp_instance*."""
    mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_validate_changed)
    mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(tapps_session_start)
    mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(tapps_init)
    mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(tapps_set_engagement_level)
    mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(tapps_upgrade)
    mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_doctor)

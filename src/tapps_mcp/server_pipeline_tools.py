"""Pipeline orchestration and validation tool handlers for TappsMCP.

Functions are defined at module level (importable for tests) and
registered on the ``mcp`` instance via :func:`register`.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import (
    Context,  # noqa: TC002 — runtime import required for FastMCP annotation resolution
)
from mcp.types import ToolAnnotations

from tapps_mcp.config.settings import load_settings
from tapps_mcp.server_helpers import success_response

if TYPE_CHECKING:
    from pathlib import Path

    from mcp.server.fastmcp import FastMCP

# Maximum files to validate concurrently (balances speed vs subprocess pressure).
_VALIDATE_CONCURRENCY = 10

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


def _write_validate_ok_marker(project_root: Path) -> None:
    """Write a marker so the Cursor stop hook can skip the reminder when validation just passed."""
    try:
        marker = project_root / _VALIDATE_OK_MARKER
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(str(time.time()), encoding="utf-8")
    except OSError:
        pass


async def _validate_progress_heartbeat(
    ctx: Any,
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
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=_PROGRESS_HEARTBEAT_INTERVAL)
        except asyncio.TimeoutError:
            pass
        if stop_event.is_set():
            return
        elapsed_sec = (time.perf_counter_ns() - start_ns) / 1_000_000_000.0
        try:
            await report(
                progress=elapsed_sec,
                total=None,
                message=f"Validating {total_files} files... (in progress)",
            )
        except Exception:
            pass


async def tapps_validate_changed(
    file_paths: str = "",
    base_ref: str = "HEAD",
    preset: str = "standard",
    include_security: bool = True,
    quick: bool = True,
    security_depth: str = "basic",
    include_impact: bool = False,
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
        include_impact: Whether to run impact analysis on changed files (default: False).
        ctx: Optional MCP context (injected by host); used for progress notifications.
    """
    from tapps_mcp.server import _record_call, _record_execution, _validate_file_path, _with_nudges
    from tapps_mcp.server_helpers import _get_scorer, ensure_session_initialized

    start = time.perf_counter_ns()
    _record_call("tapps_validate_changed")

    # Fast path: resolve changed files first. Session init and scorer are only
    # used when there are files to validate (see ensure_session_initialized below).
    from tapps_mcp.tools.batch_validator import (
        MAX_BATCH_FILES,
        detect_changed_python_files,
        format_batch_summary,
    )

    settings = load_settings()

    paths: list[Path] = []
    if file_paths.strip():
        for raw_fp in file_paths.split(","):
            cleaned_fp = raw_fp.strip()
            if not cleaned_fp or not cleaned_fp.endswith(".py"):
                continue
            with contextlib.suppress(ValueError, FileNotFoundError):
                paths.append(_validate_file_path(cleaned_fp))
    else:
        paths = detect_changed_python_files(settings.project_root, base_ref)

    if not paths:
        elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
        # Defer metrics recording so we return immediately and avoid client timeout/abort.
        # Metrics are recorded in a background task after the response is sent.
        def _deferred_record() -> None:
            _record_execution("tapps_validate_changed", start)

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
        return _with_nudges("tapps_validate_changed", resp)

    capped = len(paths) > MAX_BATCH_FILES
    extra_count = len(paths) - MAX_BATCH_FILES if capped else 0
    paths = paths[:MAX_BATCH_FILES]
    total_files = len(paths)

    stop_progress = asyncio.Event()
    progress_task: asyncio.Task[None] | None = None
    if ctx is not None and total_files > 0:
        report = getattr(ctx, "report_progress", None)
        if callable(report):
            try:
                await report(
                    progress=0.0,
                    total=None,
                    message=f"Validating {total_files} files...",
                )
            except Exception:
                pass
        progress_task = asyncio.create_task(
            _validate_progress_heartbeat(ctx, total_files, start, stop_progress),
        )

    try:
        await ensure_session_initialized()

        from tapps_mcp.gates.evaluator import evaluate_gate

        # Warm dependency cache in background when empty (do not block validation).
        if settings.dependency_scan_enabled and not quick:
            from tapps_mcp.tools.dependency_scan_cache import get_dependency_findings

            if not get_dependency_findings(str(settings.project_root)):
                task = asyncio.create_task(_warm_dependency_cache(settings))
                _background_tasks.add(task)
                task.add_done_callback(_background_tasks.discard)

        scorer = _get_scorer()
        sem = asyncio.Semaphore(_VALIDATE_CONCURRENCY)
        do_security_full = (security_depth == "full") or (include_security and not quick)

        async def _validate_one(path: Path) -> dict[str, Any]:
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

                        # Reuse bandit results from scoring; only run secret scanner
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

        raw_results = await asyncio.gather(
            *[_validate_one(p) for p in paths],
            return_exceptions=True,
        )
    finally:
        if progress_task is not None:
            stop_progress.set()
            progress_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await progress_task

    results: list[dict[str, Any]] = []
    for i, raw in enumerate(raw_results):
        if isinstance(raw, BaseException):
            results.append({"file_path": str(paths[i]), "errors": [str(raw)]})
        else:
            results.append(raw)

    all_passed = all(r.get("gate_passed", False) for r in results)
    total_sec = sum(r.get("security_issues", 0) for r in results)

    # Impact analysis (opt-in)
    impact_data: dict[str, Any] | None = None
    if include_impact and paths:
        try:
            from tapps_mcp.project.impact_analyzer import analyze_impact

            impact_results: list[dict[str, Any]] = []
            for p in paths:
                try:
                    report = analyze_impact(p, settings.project_root)
                    impact_results.append({
                        "file": str(p),
                        "severity": report.severity,
                        "direct_dependents": len(report.direct_dependents),
                        "transitive_dependents": len(report.transitive_dependents),
                        "test_files": len(report.test_files),
                    })
                except Exception:
                    impact_results.append({"file": str(p), "severity": "unknown", "error": True})

            max_severity = "low"
            for ir in impact_results:
                s = ir.get("severity", "low")
                if s == "critical":
                    max_severity = "critical"
                    break
                elif s == "high" and max_severity not in ("critical",):
                    max_severity = "high"
                elif s == "medium" and max_severity not in ("critical", "high"):
                    max_severity = "medium"

            total_affected = sum(
                ir.get("direct_dependents", 0) + ir.get("transitive_dependents", 0)
                for ir in impact_results
            )
            impact_data = {
                "max_severity": max_severity,
                "total_affected_files": total_affected,
                "per_file": impact_results,
            }
        except Exception:
            impact_data = {"error": "impact analysis failed"}

    summary = format_batch_summary(results)
    if quick:
        summary = f"[Quick mode - ruff only] {summary}"
    if capped:
        summary += f" ({extra_count} additional files not validated - cap {MAX_BATCH_FILES})"

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

    resp = success_response(
        "tapps_validate_changed",
        elapsed_ms,
        resp_data,
    )

    # Attach structured output
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
        import structlog

        structlog.get_logger(__name__).debug(
            "structured_output_failed: tapps_validate_changed", exc_info=True
        )

    return _with_nudges("tapps_validate_changed", resp)


async def _warm_dependency_cache(
    settings: Any,
) -> None:
    """Best-effort background task to warm the dependency scan cache.

    Called from :func:`tapps_session_start` so that subsequent
    ``tapps_score_file`` calls can apply vulnerability penalties.
    Failures are silently ignored — session start must never break.
    """
    import structlog

    logger = structlog.get_logger(__name__)
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
            logger.debug(
                "dependency_cache_warmed",
                findings=len(result.findings),
            )
    except Exception:
        logger.debug("dependency_cache_warming_failed", exc_info=True)


async def tapps_session_start(
    project_root: str = "",
) -> dict[str, Any]:
    """REQUIRED as the FIRST call in every session. Combines server info
    and project profile detection in a single call. Skipping means all
    subsequent tools lack project context and recommendations are generic.

    Args:
        project_root: Project root path (default: server's configured root).
    """
    from tapps_mcp.server import (
        _record_call,
        _record_execution,
        _server_info_async,
        _with_nudges,
        tapps_project_profile,
    )

    start = time.perf_counter_ns()
    _record_call("tapps_session_start")

    # Run server info (async, parallel tool detection) and project profile
    # (sync, wrapped in thread) concurrently for faster startup.
    info, profile = await asyncio.gather(
        _server_info_async(),
        asyncio.to_thread(tapps_project_profile, project_root=project_root),
    )

    # Fire-and-forget: warm the dependency scan cache in background so
    # subsequent tapps_score_file calls can apply vulnerability penalties.
    settings = load_settings()
    if settings.dependency_scan_enabled:
        task = asyncio.create_task(_warm_dependency_cache(settings))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_session_start", start)

    data: dict[str, Any] = {
        "server": info["data"]["server"],
        "configuration": info["data"]["configuration"],
        "installed_checkers": info["data"]["installed_checkers"],
        "diagnostics": info["data"]["diagnostics"],
        "quick_start": info["data"].get("quick_start", []),
        "critical_rules": info["data"].get("critical_rules", []),
        "pipeline": info["data"]["pipeline"],
    }

    if profile.get("success"):
        data["project_profile"] = profile["data"]
    else:
        data["project_profile"] = None
        err = profile.get("error")
        if isinstance(err, dict):
            err_msg = err.get("message", "unknown")
        else:
            err_msg = str(err) if err is not None else "unknown"
        data["project_profile_error"] = err_msg

    resp = success_response("tapps_session_start", elapsed_ms, data)

    # Attach structured output
    try:
        from tapps_mcp.common.output_schemas import SessionStartOutput

        checker_names = [
            c.get("name", "") if isinstance(c, dict) else getattr(c, "name", "")
            for c in info["data"].get("installed_checkers", [])
        ]
        pp = data.get("project_profile") or {}
        structured = SessionStartOutput(
            server_version=info["data"]["server"].get("version", ""),
            project_root=info["data"]["configuration"].get("project_root", ""),
            project_type=pp.get("project_type"),
            quality_preset=info["data"]["configuration"].get("quality_preset", "standard"),
            installed_checkers=[n for n in checker_names if n],
            has_ci=pp.get("has_ci", False),
            has_docker=pp.get("has_docker", False),
            has_tests=pp.get("has_tests", False),
        )
        resp["structuredContent"] = structured.to_structured_content()
    except Exception:
        import structlog as _structlog

        _structlog.get_logger(__name__).debug(
            "structured_output_failed: tapps_session_start", exc_info=True
        )

    from tapps_mcp.server_helpers import mark_session_initialized

    mark_session_initialized({
        "project_root": info["data"]["configuration"].get("project_root", ""),
        "quality_preset": info["data"]["configuration"].get("quality_preset", "standard"),
        "auto_initialized": False,
        "project_profile": data.get("project_profile"),
    })

    # Detect changed Python files for workflow nudges (run in thread to
    # avoid blocking the event loop with subprocess.run).
    nudge_ctx: dict[str, Any] = {}
    try:

        def _detect_changed_py() -> int:
            import subprocess

            diff_result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                capture_output=True,
                text=True,
                cwd=str(load_settings().project_root),
                timeout=5,
                check=False,
            )
            if diff_result.returncode == 0:
                return len([
                    f for f in diff_result.stdout.strip().splitlines() if f.endswith(".py")
                ])
            return 0

        count = await asyncio.to_thread(_detect_changed_py)
        nudge_ctx["changed_python_file_count"] = count
    except Exception:  # noqa: S110
        # Best-effort: git may not be available or repo may not exist
        pass

    return _with_nudges("tapps_session_start", resp, nudge_ctx)


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
    dry_run: bool = False,
    verify_only: bool = False,
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    """Bootstrap TAPPS pipeline in the current project.

    Verifies server info and optionally installs missing checkers (ruff, mypy,
    bandit, radon). Creates handoff, runlog, AGENTS.md, and TECH_STACK.md.
    Optionally warms the Context7 cache from the detected tech stack.
    Optionally generates platform-specific rule files for Claude Code or Cursor.

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
        dry_run: When ``True``, compute and return what would be created without
            writing files or warming caches. Keeps dry_run lightweight (~2-5s).
        verify_only: When ``True``, run only server verification and return (~1-3s).
            Use for quick connectivity/checker checks without creating files.
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
                {"cancelled": True, "message": "tapps_init cancelled — no files were written."},
            )
        # confirmed is True or None (unsupported) — proceed normally

    from tapps_mcp.pipeline.init import bootstrap_pipeline

    settings = load_settings()
    # Run in thread to avoid blocking the event loop — bootstrap_pipeline
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
        dry_run=dry_run,
        verify_only=verify_only,
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
    mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(tapps_upgrade)
    mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_doctor)

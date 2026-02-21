"""TappsMCP MCP server entry point.

Creates the FastMCP server instance, registers all tools, and provides
``run_server()`` for the CLI.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from tapps_mcp.metrics.collector import MetricsHub
    from tapps_mcp.project.session_notes import SessionNoteStore

import structlog
from mcp.server.fastmcp import FastMCP

from tapps_mcp import __version__
from tapps_mcp.common.logging import setup_logging
from tapps_mcp.config.settings import load_settings
from tapps_mcp.server_helpers import error_response, serialize_issues, success_response
from tapps_mcp.tools.tool_detection import detect_installed_tools

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# FastMCP server instance
# ---------------------------------------------------------------------------

mcp = FastMCP("TappsMCP")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_MIN_DRIVE_PATH_LEN = 2


def _normalize_path_for_mapping(path: str) -> str:
    """Normalize a path string for host-root prefix comparison (cross-platform)."""
    s = path.strip().replace("\\", "/")
    if s and s[1:2] == ":" and len(s) > _MIN_DRIVE_PATH_LEN and s[2:3] == "/":
        s = s[0].lower() + s[1:]
    return s.rstrip("/") or "/"


def _validate_file_path(file_path: str) -> Path:
    """Validate *file_path* against the project root boundary.

    When ``host_project_root`` is set (e.g. in Docker), paths that look like
    absolute host paths under that root are mapped to project_root so Cursor
    and other clients can send host paths without "path denied" errors.
    """
    from tapps_mcp.security.path_validator import PathValidator

    settings = load_settings()
    validator = PathValidator(settings.project_root)
    path_str = file_path.strip()

    if settings.host_project_root:
        host_norm = _normalize_path_for_mapping(settings.host_project_root)
        input_norm = _normalize_path_for_mapping(path_str)
        if host_norm and (
            input_norm == host_norm
            or input_norm.startswith(host_norm + "/")
            or (input_norm + "/").startswith(host_norm + "/")
        ):
            suffix = input_norm[len(host_norm) :].lstrip("/")
            path_str = suffix or "."

    return validator.validate_read_path(path_str)


def _record_call(tool_name: str) -> None:
    """Record a tool call in the session checklist tracker.

    If tapps_mcp.tools.checklist is unavailable (e.g. incomplete binary install),
    we no-op so other tools still run.
    """
    try:
        from tapps_mcp.tools.checklist import CallTracker

        CallTracker.record(tool_name)
    except ImportError:
        logger.debug("checklist module unavailable, skipping call record", tool=tool_name)


def _record_execution(
    tool_name: str,
    start_ns: int,
    *,
    status: str = "success",
    file_path: str | None = None,
    gate_passed: bool | None = None,
    score: float | None = None,
    error_code: str | None = None,
    degraded: bool = False,
) -> None:
    """Record tool execution metrics to the MetricsHub."""
    from datetime import UTC, datetime, timedelta

    elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
    now = datetime.now(tz=UTC)
    started = now - timedelta(milliseconds=elapsed_ms)

    hub = _get_metrics_hub()
    hub.execution.record(
        tool_name=tool_name,
        started_at=started,
        completed_at=now,
        status=status,
        file_path=file_path,
        gate_passed=gate_passed,
        score=score,
        error_code=error_code,
        degraded=degraded,
        session_id=hub.session_id,
    )


# ---------------------------------------------------------------------------
# Nudge helper — injects next_steps + pipeline_progress into any response
# ---------------------------------------------------------------------------


def _with_nudges(
    tool_name: str,
    response: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Inject ``next_steps`` and ``pipeline_progress`` into a response dict.

    Safe to call on error responses (they are returned unchanged).
    """
    if not response.get("success", False):
        return response
    from tapps_mcp.common.nudges import compute_next_steps, compute_pipeline_progress

    steps = compute_next_steps(tool_name, context)
    progress = compute_pipeline_progress()
    data = response.get("data", {})
    if steps:
        data["next_steps"] = steps
    if progress:
        data["pipeline_progress"] = progress
    return response


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def tapps_server_info() -> dict[str, Any]:
    """REQUIRED at session start. Discovers server version, available tools,
    installed checkers (ruff, mypy, bandit, radon), and configuration.
    Skipping means subsequent tools lack context and recommendations are generic.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_server_info")

    settings = load_settings()
    installed = detect_installed_tools()

    # Collect subsystem diagnostics (Context7, cache, RAG, knowledge base)
    from tapps_mcp.diagnostics import collect_diagnostics

    cache_dir = settings.project_root / ".tapps-mcp-cache"
    diagnostics = collect_diagnostics(
        api_key=settings.context7_api_key,
        cache_dir=cache_dir,
    )

    # Build tool list from the MCP server itself
    available_tools: list[str] = []
    try:
        tool_manager = mcp._tool_manager
        available_tools = list(tool_manager._tools.keys())
    except AttributeError:
        # Fallback if internal API changes
        available_tools = [
            "tapps_server_info",
            "tapps_session_start",
            "tapps_score_file",
            "tapps_security_scan",
            "tapps_quality_gate",
            "tapps_lookup_docs",
            "tapps_validate_config",
            "tapps_validate_changed",
            "tapps_quick_check",
            "tapps_consult_expert",
            "tapps_list_experts",
            "tapps_checklist",
            "tapps_project_profile",
            "tapps_session_notes",
            "tapps_impact_analysis",
            "tapps_report",
            "tapps_init",
            "tapps_dashboard",
            "tapps_stats",
            "tapps_feedback",
        ]

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_server_info", start)

    from tapps_mcp.pipeline.models import STAGE_TOOLS, PipelineStage

    resp = success_response("tapps_server_info", elapsed_ms, {
        "server": {
            "name": "TappsMCP",
            "version": __version__,
            "protocol_version": "2025-11-25",
        },
        "configuration": {
            "project_root": str(settings.project_root),
            "quality_preset": settings.quality_preset,
            "log_level": settings.log_level,
        },
        "available_tools": available_tools,
        "installed_checkers": [t.model_dump() for t in installed],
        "diagnostics": diagnostics.model_dump(),
        "recommended_workflow": (
            "FIRST: Call tapps_session_start() to initialize. "
            "BEFORE using any library: Call tapps_lookup_docs(). For domain+library questions, pair with tapps_consult_expert(). "
            "AFTER editing Python files: Call tapps_score_file(quick=True) or tapps_quick_check(). "
            "BEFORE declaring done: Call tapps_validate_changed() or tapps_quality_gate(). "
            "FINAL step: Call tapps_checklist()."
        ),
        "quick_start": [
            "1. FIRST: Call tapps_session_start() to initialize the session",
            "2. BEFORE using any library API: Call tapps_lookup_docs(library='<name>')",
            "3. DURING edits: Call tapps_quick_check(file_path='<path>') after each change",
            "4. BEFORE declaring done: Call tapps_validate_changed() - all gates MUST pass",
            "5. FINAL step: Call tapps_checklist(task_type='<type>') to verify completeness",
        ],
        "critical_rules": [
            "BLOCKING: tapps_quality_gate MUST pass before work is complete",
            "BLOCKING: tapps_lookup_docs MUST be called before using external library APIs",
            "REQUIRED: tapps_score_file MUST be called on every modified Python file",
            "NEVER skip tapps_checklist as the final verification step",
        ],
        "pipeline": {
            "name": "TAPPS Quality Pipeline",
            "stages": [s.value for s in PipelineStage],
            "current_hint": (
                "Start with tapps_pipeline_overview prompt, or follow stages in order."
            ),
            "stage_tools": {s.value: tools for s, tools in STAGE_TOOLS.items()},
            "handoff_file": "docs/TAPPS_HANDOFF.md",
            "runlog_file": "docs/TAPPS_RUNLOG.md",
            "prompts_available": True,
        },
    })
    return _with_nudges("tapps_server_info", resp)


@mcp.tool()
async def tapps_score_file(
    file_path: str,
    quick: bool = False,
    fix: bool = False,
    mode: str = "auto",
) -> dict[str, Any]:
    """REQUIRED after editing any Python file. Scores quality across 7
    categories (complexity, security, maintainability, test coverage,
    performance, structure, devex). Skipping means quality issues go
    undetected and the quality gate will likely fail.

    Use quick=True during edit-lint-fix loops; use full (quick=False) before
    declaring work complete.

    Args:
        file_path: Path to the Python file to score.
        quick: If True, run ruff-only scoring (< 500 ms).
        fix: If True (requires quick=True), apply ruff auto-fixes first.
        mode: Execution mode - "subprocess", "direct", or "auto" (default).
            "direct" uses radon as a library and sync subprocess in thread
            pool, avoiding async subprocess reliability issues.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_score_file")

    try:
        resolved = _validate_file_path(file_path)
    except (ValueError, FileNotFoundError) as exc:
        return error_response("tapps_score_file", "path_denied", str(exc))

    from tapps_mcp.scoring.scorer import CodeScorer

    scorer = CodeScorer()
    fixes_applied = 0

    if quick:
        if fix:
            from tapps_mcp.tools.ruff import run_ruff_fix

            fixes_applied = run_ruff_fix(str(resolved), cwd=str(resolved.parent))

        result = scorer.score_file_quick(resolved)
    else:
        result = await scorer.score_file(resolved, mode=mode)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    # Aggregate suggestions across all categories
    all_suggestions: list[str] = []
    for cat in result.categories.values():
        all_suggestions.extend(cat.suggestions)

    data: dict[str, Any] = {
        "file_path": result.file_path,
        "overall_score": round(result.overall_score, 2),
        "categories": {
            name: {
                "score": round(cat.score, 2),
                "weight": cat.weight,
                "details": cat.details,
                "suggestions": cat.suggestions,
            }
            for name, cat in result.categories.items()
        },
        "suggestions": all_suggestions,
        "lint_issue_count": len(result.lint_issues),
        "type_issue_count": len(result.type_issues),
        "security_issue_count": len(result.security_issues),
    }

    if quick and fix:
        data["fixes_applied"] = fixes_applied

    if result.lint_issues:
        data["lint_issues"] = serialize_issues(result.lint_issues)
    if result.type_issues:
        data["type_issues"] = serialize_issues(result.type_issues)
    if result.security_issues:
        data["security_issues"] = serialize_issues(result.security_issues)
    if result.tool_errors:
        data["tool_errors"] = result.tool_errors

    # Detect uncached library imports (non-critical enhancement)
    try:
        from tapps_mcp.knowledge.cache import KBCache
        from tapps_mcp.knowledge.import_analyzer import (
            extract_external_imports,
            find_uncached_libraries,
        )

        settings_cache = load_settings()
        cache = KBCache(settings_cache.project_root / ".tapps-mcp-cache")
        external = extract_external_imports(resolved, settings_cache.project_root)
        uncached = find_uncached_libraries(external, cache)
        if uncached:
            data["uncached_libraries"] = uncached[:10]
            data["docs_hint"] = (
                f"Call tapps_lookup_docs for {', '.join(uncached[:5])} "
                "to avoid hallucinated APIs"
            )
    except Exception as exc:  # Never fail scoring for import analysis
        logger.debug("score_file_import_analysis_skip", file_path=str(resolved), error=str(exc))

    _record_execution(
        "tapps_score_file",
        start,
        file_path=str(resolved),
        score=round(result.overall_score, 2),
        degraded=result.degraded,
    )

    resp = success_response("tapps_score_file", elapsed_ms, data, degraded=result.degraded)
    return _with_nudges("tapps_score_file", resp, {
        "security_issue_count": len(result.security_issues),
    })


@mcp.tool()
def tapps_security_scan(
    file_path: str,
    scan_secrets: bool = True,
) -> dict[str, Any]:
    """REQUIRED when changes touch security-sensitive code (auth, input handling,
    secrets, crypto). Runs bandit and secret detection on a Python file.
    Skipping risks shipping vulnerabilities to production.

    Args:
        file_path: Path to the Python file to scan.
        scan_secrets: Whether to scan for hardcoded secrets (default: True).
    """
    start = time.perf_counter_ns()
    _record_call("tapps_security_scan")

    try:
        resolved = _validate_file_path(file_path)
    except (ValueError, FileNotFoundError) as exc:
        return error_response("tapps_security_scan", "path_denied", str(exc))

    from tapps_mcp.security.security_scanner import run_security_scan

    settings = load_settings()
    result = run_security_scan(
        str(resolved),
        scan_secrets=scan_secrets,
        cwd=str(settings.project_root),
        timeout=settings.tool_timeout,
    )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution(
        "tapps_security_scan",
        start,
        file_path=str(resolved),
        degraded=not result.bandit_available,
    )

    resp = success_response(
        "tapps_security_scan",
        elapsed_ms,
        {
            "file_path": str(resolved),
            "passed": result.passed,
            "total_issues": result.total_issues,
            "critical_count": result.critical_count,
            "high_count": result.high_count,
            "medium_count": result.medium_count,
            "low_count": result.low_count,
            "bandit_available": result.bandit_available,
            "bandit_issues": serialize_issues(result.bandit_issues, limit=30),
            "secret_findings": serialize_issues(result.secret_findings, limit=30),
        },
        degraded=not result.bandit_available,
    )
    return _with_nudges("tapps_security_scan", resp)


@mcp.tool()
async def tapps_quality_gate(
    file_path: str,
    preset: str = "standard",
) -> dict[str, Any]:
    """BLOCKING REQUIREMENT before declaring work complete. Runs full scoring
    then evaluates pass/fail against the quality preset. Work is NOT done
    until this passes (or the user explicitly accepts the risk).

    Args:
        file_path: Path to the Python file to evaluate.
        preset: Quality preset — "standard" (70+), "strict" (80+), or "framework" (75+).
    """
    start = time.perf_counter_ns()
    _record_call("tapps_quality_gate")

    try:
        resolved = _validate_file_path(file_path)
    except (ValueError, FileNotFoundError) as exc:
        return error_response("tapps_quality_gate", "path_denied", str(exc))

    from tapps_mcp.gates.evaluator import evaluate_gate
    from tapps_mcp.scoring.scorer import CodeScorer

    scorer = CodeScorer()
    score_result = await scorer.score_file(resolved)
    gate_result = evaluate_gate(score_result, preset=preset)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution(
        "tapps_quality_gate",
        start,
        file_path=str(resolved),
        gate_passed=gate_result.passed,
        score=round(score_result.overall_score, 2),
        degraded=score_result.degraded,
    )

    # Collect suggestions for failing categories
    failing_cats = {f.category for f in gate_result.failures}
    gate_suggestions: list[str] = []
    for name, cat in score_result.categories.items():
        if name in failing_cats and cat.suggestions:
            gate_suggestions.extend(cat.suggestions)

    gate_data: dict[str, Any] = {
        "file_path": str(resolved),
        "passed": gate_result.passed,
        "preset": gate_result.preset,
        "overall_score": round(score_result.overall_score, 2),
        "scores": {k: round(v, 2) for k, v in gate_result.scores.items()},
        "thresholds": gate_result.thresholds.model_dump(),
        "failures": [f.model_dump() for f in gate_result.failures],
        "warnings": gate_result.warnings,
        "suggestions": gate_suggestions,
    }
    if score_result.tool_errors:
        gate_data["tool_errors"] = score_result.tool_errors

    resp = success_response(
        "tapps_quality_gate",
        elapsed_ms,
        gate_data,
        degraded=score_result.degraded,
    )
    return _with_nudges("tapps_quality_gate", resp, {
        "gate_passed": gate_result.passed,
    })


@mcp.tool()
async def tapps_lookup_docs(
    library: str,
    topic: str = "overview",
    mode: str = "code",
) -> dict[str, Any]:
    """BLOCKING REQUIREMENT before using any external library API. Returns
    current docs (Context7 + cache) to prevent hallucinated APIs. Skipping
    leads to incorrect API usage that must be fixed later. Resolves library
    names via fuzzy matching; content is safety-filtered before return.

    Args:
        library: Library name (fuzzy-matched, e.g. "fastapi", "react").
        topic: Specific topic within the library (default "overview").
        mode: "code" for API references, "info" for conceptual guides.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_lookup_docs")

    from tapps_mcp.knowledge.cache import KBCache
    from tapps_mcp.knowledge.lookup import LookupEngine

    settings = load_settings()
    cache_dir = settings.project_root / ".tapps-mcp-cache"
    cache = KBCache(cache_dir)
    engine = LookupEngine(cache, api_key=settings.context7_api_key)

    try:
        result = await engine.lookup(library, topic, mode=mode)
    finally:
        await engine.close()

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "library": result.library,
        "topic": result.topic,
        "source": result.source,
        "cache_hit": result.cache_hit,
        "response_time_ms": result.response_time_ms,
    }

    if result.content is not None:
        data["content"] = result.content
        data["token_estimate"] = len(result.content) // 4
    if result.context7_id is not None:
        data["context7_id"] = result.context7_id
    if result.fuzzy_score is not None:
        data["fuzzy_score"] = result.fuzzy_score

    _record_execution(
        "tapps_lookup_docs",
        start,
        status="success" if result.success else "failed",
        error_code="api_key_missing" if (result.error and "API key" in result.error) else None,
    )

    response = success_response("tapps_lookup_docs", elapsed_ms, data)
    response["success"] = result.success

    if result.error:
        err_code = "api_key_missing" if "API key" in result.error else "lookup_failed"
        response["error"] = {"code": err_code, "message": result.error}
    if result.warning:
        response["warning"] = result.warning

    return _with_nudges("tapps_lookup_docs", response)


@mcp.tool()
def tapps_validate_config(
    file_path: str,
    config_type: str = "auto",
) -> dict[str, Any]:
    """REQUIRED when changing Dockerfile, docker-compose, or infra config.
    Validates against best practices (e.g. non-root user, resource limits).
    Skipping risks deployment failures. Supports Dockerfile, docker-compose.yml,
    and WebSocket/MQTT/InfluxDB patterns.

    Args:
        file_path: Path to the config file to validate.
        config_type: Config type or "auto" for auto-detection.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_validate_config")

    try:
        resolved = _validate_file_path(file_path)
    except (ValueError, FileNotFoundError) as exc:
        return error_response("tapps_validate_config", "path_denied", str(exc))

    content = resolved.read_text(encoding="utf-8")

    from tapps_mcp.validators.base import validate_config

    explicit_type = None if config_type == "auto" else config_type
    result = validate_config(str(resolved), content, config_type=explicit_type)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_validate_config", start, file_path=str(resolved))

    resp = success_response("tapps_validate_config", elapsed_ms, {
        "file_path": result.file_path,
        "config_type": result.config_type,
        "valid": result.valid,
        "findings": [f.model_dump() for f in result.findings],
        "suggestions": result.suggestions,
        "finding_count": len(result.findings),
        "critical_count": sum(1 for f in result.findings if f.severity == "critical"),
        "warning_count": sum(1 for f in result.findings if f.severity == "warning"),
    })
    return _with_nudges("tapps_validate_config", resp)


@mcp.tool()
def tapps_consult_expert(
    question: str,
    domain: str = "",
) -> dict[str, Any]:
    """REQUIRED for domain-specific decisions (security, testing, APIs, DB,
    architecture). Routes to one of 16 built-in experts and returns
    RAG-backed guidance with confidence scores. Skipping risks incorrect
    patterns and missed best practices.

    Args:
        question: The technical question to ask (natural language).
        domain: Optional domain override (e.g. "security", "testing-strategies").
            When empty, the best domain is auto-detected from the question.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_consult_expert")

    from tapps_mcp.experts.engine import consult_expert

    result = consult_expert(
        question=question,
        domain=domain or None,
    )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_consult_expert", start)

    resp = success_response("tapps_consult_expert", elapsed_ms, {
        "domain": result.domain,
        "expert_id": result.expert_id,
        "expert_name": result.expert_name,
        "answer": result.answer,
        "confidence": round(result.confidence, 4),
        "factors": result.factors.model_dump(),
        "sources": result.sources,
        "chunks_used": result.chunks_used,
        "low_confidence_nudge": result.low_confidence_nudge,
        "suggested_tool": result.suggested_tool,
        "suggested_library": result.suggested_library,
        "suggested_topic": result.suggested_topic,
        "fallback_used": result.fallback_used,
        "fallback_library": result.fallback_library,
        "fallback_topic": result.fallback_topic,
    })
    return _with_nudges("tapps_consult_expert", resp)


@mcp.tool()
def tapps_list_experts() -> dict[str, Any]:
    """Call before tapps_consult_expert if unsure which domain fits. Returns
    the 16 built-in experts with domain, description, and knowledge-base status.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_list_experts")

    from tapps_mcp.experts.engine import list_experts

    experts = list_experts()
    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_list_experts", start)

    resp = success_response("tapps_list_experts", elapsed_ms, {
        "expert_count": len(experts),
        "experts": [e.model_dump() for e in experts],
    })
    return _with_nudges("tapps_list_experts", resp)


@mcp.tool()
def tapps_checklist(
    task_type: str = "review",
) -> dict[str, Any]:
    """REQUIRED as the FINAL step before declaring work complete. Reports which
    tools were called and which required/recommended steps were skipped.
    Skipping means no verification that the quality process was followed.

    Args:
        task_type: "feature" | "bugfix" | "refactor" | "security" | "review".
            Use "review" for general code review.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_checklist")

    try:
        from tapps_mcp.tools.checklist import CallTracker

        result = CallTracker.evaluate(task_type)
        elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
        _record_execution("tapps_checklist", start)
        resp = success_response("tapps_checklist", elapsed_ms, result.model_dump())
        return _with_nudges("tapps_checklist", resp, {"complete": result.complete})
    except ImportError:
        elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
        _record_execution("tapps_checklist", start)
        fallback_data = {
            "task_type": task_type,
            "called": [],
            "missing_required": [],
            "missing_recommended": [],
            "missing_optional": [],
            "missing_required_hints": [],
            "missing_recommended_hints": [],
            "missing_optional_hints": [],
            "complete": False,
            "total_calls": 0,
            "checklist_unavailable": True,
            "message": (
                "Module tapps_mcp.tools.checklist is not available (e.g. incomplete "
                "installation or binary). Other tools work; use tapps_quality_gate and "
                "tapps_security_scan for verification."
            ),
        }
        resp = success_response("tapps_checklist", elapsed_ms, fallback_data)
        return _with_nudges("tapps_checklist", resp, {"complete": False})


# ---------------------------------------------------------------------------
# Epic 4: Project Context & Session Management tools
# ---------------------------------------------------------------------------


@mcp.tool()
def tapps_project_profile(
    project_root: str = "",
) -> dict[str, Any]:
    """REQUIRED at session start. Detects the project's tech stack, type, CI,
    Docker, test frameworks, and package managers. Returns quality
    recommendations tailored to the detected stack. Skipping means
    recommendations are generic instead of project-specific.

    Args:
        project_root: Project root path (default: server's configured root).
    """
    start = time.perf_counter_ns()
    _record_call("tapps_project_profile")

    from tapps_mcp.project.profiler import detect_project_profile

    settings = load_settings()
    root = settings.project_root
    if project_root:
        from pathlib import Path

        root = Path(project_root).resolve()

    try:
        profile = detect_project_profile(root)
    except Exception as exc:
        elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
        _record_execution(
            "tapps_project_profile", start, status="failed", error_code="profile_failed",
        )
        return error_response("tapps_project_profile", "profile_failed", str(exc))

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_project_profile", start)

    resp = success_response("tapps_project_profile", elapsed_ms, {
        "project_root": str(root),
        "tech_stack": profile.tech_stack.model_dump(),
        "project_type": profile.project_type,
        "project_type_confidence": round(profile.project_type_confidence, 2),
        "project_type_reason": profile.project_type_reason,
        "has_ci": profile.has_ci,
        "ci_systems": profile.ci_systems,
        "has_docker": profile.has_docker,
        "has_tests": profile.has_tests,
        "test_frameworks": profile.test_frameworks,
        "package_managers": profile.package_managers,
        "quality_recommendations": profile.quality_recommendations,
    })
    return _with_nudges("tapps_project_profile", resp)


# Session note store - singleton, created on first use
_session_store: SessionNoteStore | None = None


def _get_session_store() -> SessionNoteStore:
    """Lazily create or return the session note store."""
    global _session_store  # noqa: PLW0603
    if _session_store is None:
        from tapps_mcp.project.session_notes import SessionNoteStore

        settings = load_settings()
        _session_store = SessionNoteStore(settings.project_root)
    return _session_store


@mcp.tool()
def tapps_session_notes(
    action: str,
    key: str = "",
    value: str = "",
) -> dict[str, Any]:
    """Persist notes across the session to avoid losing context.

    Use ``save`` to record a constraint or decision, ``get`` to recall one,
    ``list`` to see all notes, or ``clear`` to reset.

    Args:
        action: "save" | "get" | "list" | "clear".
        key: Note key (required for save/get, optional for clear).
        value: Note value (required for save).
    """
    start = time.perf_counter_ns()
    _record_call("tapps_session_notes")

    store = _get_session_store()
    data: dict[str, Any] = {}

    if action == "save":
        if not key or not value:
            return error_response(
                "tapps_session_notes", "missing_params", "save requires key and value",
            )
        note = store.save(key, value)
        data = {"action": "save", "note": note.model_dump()}

    elif action == "get":
        if not key:
            return error_response("tapps_session_notes", "missing_params", "get requires key")
        found = store.get(key)
        note_data = found.model_dump() if found else None
        data = {"action": "get", "note": note_data, "found": found is not None}

    elif action == "list":
        notes = store.list_all()
        data = {"action": "list", "notes": [n.model_dump() for n in notes]}

    elif action == "clear":
        cleared = store.clear(key or None)
        data = {"action": "clear", "cleared_count": cleared}

    else:
        return error_response(
            "tapps_session_notes", "invalid_action",
            f"Unknown action: {action}. Use save/get/list/clear.",
        )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_session_notes", start)
    data.update(store.metadata())

    resp = success_response("tapps_session_notes", elapsed_ms, data)
    return _with_nudges("tapps_session_notes", resp)


@mcp.tool()
def tapps_impact_analysis(
    file_path: str,
    change_type: str = "modified",
) -> dict[str, Any]:
    """REQUIRED before refactoring or deleting files. Uses AST-based import
    graph analysis to map the blast radius - direct dependents, transitive
    dependents, and test files that should be re-run. Skipping risks breaking
    dependent code.

    Args:
        file_path: Path to the file being changed.
        change_type: "added" | "modified" | "removed".
    """
    start = time.perf_counter_ns()
    _record_call("tapps_impact_analysis")

    try:
        resolved = _validate_file_path(file_path)
    except (ValueError, FileNotFoundError) as exc:
        return error_response("tapps_impact_analysis", "path_denied", str(exc))

    from tapps_mcp.project.impact_analyzer import analyze_impact

    settings = load_settings()
    report = analyze_impact(resolved, settings.project_root, change_type)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_impact_analysis", start, file_path=str(resolved))

    resp = success_response("tapps_impact_analysis", elapsed_ms, {
        "changed_file": report.changed_file,
        "change_type": report.change_type,
        "severity": report.severity,
        "total_affected": report.total_affected,
        "direct_dependents": [d.model_dump() for d in report.direct_dependents],
        "transitive_dependents": [d.model_dump() for d in report.transitive_dependents],
        "test_files": [t.model_dump() for t in report.test_files],
        "recommendations": report.recommendations,
    })
    return _with_nudges("tapps_impact_analysis", resp)


@mcp.tool()
async def tapps_report(
    file_path: str = "",
    report_format: str = "json",
) -> dict[str, Any]:
    """Generate a quality report combining scoring and gate results.

    When *file_path* is provided, scores that single file.
    Supports JSON (default), markdown, and HTML output.

    Args:
        file_path: Path to a Python file (optional - project-wide if omitted).
        report_format: "json" | "markdown" | "html".
    """
    start = time.perf_counter_ns()
    _record_call("tapps_report")

    from tapps_mcp.gates.evaluator import evaluate_gate
    from tapps_mcp.project.report import generate_report
    from tapps_mcp.scoring.scorer import CodeScorer

    settings = load_settings()
    scorer = CodeScorer()

    score_results = []
    gate_results = []

    if file_path:
        try:
            resolved = _validate_file_path(file_path)
        except (ValueError, FileNotFoundError) as exc:
            return error_response("tapps_report", "path_denied", str(exc))
        result = await scorer.score_file(resolved)
        score_results.append(result)
        gate_results.append(evaluate_gate(result, preset=settings.quality_preset))
    else:
        # Project-wide: score all .py files in project root (max 20)
        from pathlib import Path as _Path

        from tapps_mcp.common.utils import should_skip_path

        py_files = sorted(_Path(settings.project_root).rglob("*.py"))
        py_files = [f for f in py_files if not should_skip_path(f)][:20]

        for pf in py_files:
            try:
                result = await scorer.score_file(pf)
                score_results.append(result)
                gate_results.append(evaluate_gate(result, preset=settings.quality_preset))
            except (ValueError, OSError, RuntimeError) as e:
                logger.warning("report_file_skip", file=str(pf), error=str(e))

    report_data = generate_report(
        score_results,
        gate_results,
        report_format=report_format,
    )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_report", start, file_path=file_path or None)

    resp = success_response("tapps_report", elapsed_ms, report_data)
    return _with_nudges("tapps_report", resp)


# ---------------------------------------------------------------------------
# Composite tools — reduce LLM call count
# ---------------------------------------------------------------------------


@mcp.tool()
def tapps_session_start(
    project_root: str = "",
) -> dict[str, Any]:
    """REQUIRED as the FIRST call in every session. Combines server info
    and project profile detection in a single call. Skipping means all
    subsequent tools lack project context and recommendations are generic.

    Args:
        project_root: Project root path (default: server's configured root).
    """
    start = time.perf_counter_ns()
    _record_call("tapps_session_start")

    # Delegate to existing tools (they record their own calls)
    info = tapps_server_info()
    profile = tapps_project_profile(project_root=project_root)

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
        data["project_profile_error"] = (
            err.get("message", "unknown") if isinstance(err, dict) else (str(err) if err is not None else "unknown")
        )

    resp = success_response("tapps_session_start", elapsed_ms, data)
    return _with_nudges("tapps_session_start", resp)


@mcp.tool()
async def tapps_validate_changed(
    file_paths: str = "",
    base_ref: str = "HEAD",
    preset: str = "standard",
    include_security: bool = True,
) -> dict[str, Any]:
    """REQUIRED before declaring work complete on multi-file changes.
    Detects changed Python files (via git diff) or accepts an explicit
    comma-separated list. Runs score + quality gate + security scan on each
    file. Skipping means quality issues in changed files go undetected.

    Args:
        file_paths: Comma-separated file paths (empty = auto-detect via git diff).
        base_ref: Git ref to diff against (default: HEAD for unstaged changes).
        preset: Quality gate preset - "standard", "strict", or "framework".
        include_security: Whether to run security scan on each file.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_validate_changed")

    from tapps_mcp.gates.evaluator import evaluate_gate
    from tapps_mcp.scoring.scorer import CodeScorer
    from tapps_mcp.tools.batch_validator import (
        MAX_BATCH_FILES,
        detect_changed_python_files,
        format_batch_summary,
    )

    settings = load_settings()

    # Resolve files
    paths: list[Path] = []
    if file_paths.strip():
        for raw_fp in file_paths.split(","):
            cleaned_fp = raw_fp.strip()
            if not cleaned_fp:
                continue
            try:
                paths.append(_validate_file_path(cleaned_fp))
            except (ValueError, FileNotFoundError) as exc:
                logger.warning("validate_changed_skip", file=cleaned_fp, error=str(exc))
    else:
        paths = detect_changed_python_files(settings.project_root, base_ref)

    if not paths:
        elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
        _record_execution("tapps_validate_changed", start)
        resp = success_response("tapps_validate_changed", elapsed_ms, {
            "files_validated": 0,
            "all_gates_passed": True,
            "total_security_issues": 0,
            "results": [],
            "summary": "No changed Python files found.",
        })
        return _with_nudges("tapps_validate_changed", resp)

    # Cap at MAX_BATCH_FILES
    capped = len(paths) > MAX_BATCH_FILES
    extra_count = len(paths) - MAX_BATCH_FILES if capped else 0
    paths = paths[:MAX_BATCH_FILES]

    scorer = CodeScorer()
    results: list[dict[str, Any]] = []

    for path in paths:
        file_result: dict[str, Any] = {"file_path": str(path)}
        try:
            score = await scorer.score_file(path)
            file_result["overall_score"] = round(score.overall_score, 2)

            gate = evaluate_gate(score, preset=preset)
            file_result["gate_passed"] = gate.passed
            if gate.failures:
                file_result["gate_failures"] = [f.model_dump() for f in gate.failures]

            if include_security:
                from tapps_mcp.security.security_scanner import run_security_scan

                sec = run_security_scan(
                    str(path),
                    scan_secrets=True,
                    cwd=str(settings.project_root),
                    timeout=settings.tool_timeout,
                )
                file_result["security_passed"] = sec.passed
                file_result["security_issues"] = sec.total_issues
        except Exception as exc:
            file_result["errors"] = [str(exc)]
            logger.warning("validate_changed_error", file=str(path), exc_info=True)

        results.append(file_result)

    all_passed = all(r.get("gate_passed", False) for r in results)
    total_sec = sum(r.get("security_issues", 0) for r in results)

    summary = format_batch_summary(results)
    if capped:
        summary += f" ({extra_count} additional files not validated - cap {MAX_BATCH_FILES})"

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution(
        "tapps_validate_changed", start,
        gate_passed=all_passed,
    )

    resp = success_response("tapps_validate_changed", elapsed_ms, {
        "files_validated": len(results),
        "all_gates_passed": all_passed,
        "total_security_issues": total_sec,
        "results": results,
        "summary": summary,
    })
    return _with_nudges("tapps_validate_changed", resp)


@mcp.tool()
async def tapps_quick_check(
    file_path: str,
    preset: str = "standard",
) -> dict[str, Any]:
    """REQUIRED at minimum after editing any Python file. Runs quick
    score + quality gate + basic security check in one fast call. For
    thorough validation, use tapps_validate_changed or individual tools.
    Skipping means quality regressions go unnoticed.

    Args:
        file_path: Path to the Python file to check.
        preset: Quality gate preset - "standard", "strict", or "framework".
    """
    start = time.perf_counter_ns()
    _record_call("tapps_quick_check")

    try:
        resolved = _validate_file_path(file_path)
    except (ValueError, FileNotFoundError) as exc:
        return error_response("tapps_quick_check", "path_denied", str(exc))

    from tapps_mcp.gates.evaluator import evaluate_gate
    from tapps_mcp.scoring.scorer import CodeScorer
    from tapps_mcp.security.security_scanner import run_security_scan

    settings = load_settings()
    scorer = CodeScorer()

    # Quick score (ruff-only, fast)
    score_result = scorer.score_file_quick(resolved)

    # Gate evaluation
    gate_result = evaluate_gate(score_result, preset=preset)

    # Security scan
    sec_result = run_security_scan(
        str(resolved),
        scan_secrets=True,
        cwd=str(settings.project_root),
        timeout=settings.tool_timeout,
    )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution(
        "tapps_quick_check",
        start,
        file_path=str(resolved),
        gate_passed=gate_result.passed,
        score=round(score_result.overall_score, 2),
    )

    data: dict[str, Any] = {
        "file_path": str(resolved),
        "overall_score": round(score_result.overall_score, 2),
        "gate_passed": gate_result.passed,
        "gate_preset": preset,
        "security_passed": sec_result.passed,
        "lint_issue_count": len(score_result.lint_issues),
        "security_issue_count": sec_result.total_issues,
    }

    if gate_result.failures:
        data["gate_failures"] = [f.model_dump() for f in gate_result.failures]
    if score_result.lint_issues:
        data["lint_issues"] = serialize_issues(score_result.lint_issues)
    if sec_result.total_issues > 0:
        data["security_issues"] = serialize_issues(
            sec_result.bandit_issues + sec_result.secret_findings, limit=10,
        )

    # Aggregate suggestions
    suggestions: list[str] = []
    for cat in score_result.categories.values():
        suggestions.extend(cat.suggestions)
    if suggestions:
        data["suggestions"] = suggestions

    resp = success_response(
        "tapps_quick_check", elapsed_ms, data,
        degraded=not sec_result.bandit_available,
    )
    return _with_nudges("tapps_quick_check", resp)


# ---------------------------------------------------------------------------
# Epic 8: Pipeline Orchestration — MCP Prompts & Bootstrap Tool
# ---------------------------------------------------------------------------


@mcp.prompt()
def tapps_pipeline(stage: str = "discover") -> str:
    """TAPPS quality pipeline - structured 5-stage workflow.

    Get instructions for a specific pipeline stage. Stages run in order:
    discover -> research -> develop -> validate -> verify.

    Args:
        stage: Pipeline stage to get instructions for.
               One of: discover, research, develop, validate, verify.
    """
    from tapps_mcp.prompts.prompt_loader import load_stage_prompt

    return load_stage_prompt(stage)


@mcp.prompt()
def tapps_pipeline_overview() -> str:
    """Get a summary of the full TAPPS 5-stage quality pipeline.

    Returns stage names, tool assignments, flow diagram, and
    handoff file format. Use this to understand the full pipeline
    before starting.
    """
    from tapps_mcp.prompts.prompt_loader import load_overview

    return load_overview()


@mcp.tool()
def tapps_init(
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
) -> dict[str, Any]:
    """Bootstrap TAPPS pipeline in the current project.

    Verifies server info and optionally installs missing checkers (ruff, mypy,
    bandit, radon). Creates handoff, runlog, AGENTS.md, and TECH_STACK.md.
    Optionally warms the Context7 cache from the detected tech stack.
    Optionally generates platform-specific rule files for Claude Code or Cursor.

    Call once per project to set up the pipeline workflow.

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
    """
    start = time.perf_counter_ns()
    _record_call("tapps_init")

    from tapps_mcp.pipeline.init import bootstrap_pipeline

    settings = load_settings()
    result = bootstrap_pipeline(
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


# ---------------------------------------------------------------------------
# Epic 7: Metrics, Observability & Dashboard tools
# ---------------------------------------------------------------------------


def _get_metrics_hub() -> MetricsHub:
    """Lazily import and return the global MetricsHub."""
    from tapps_mcp.metrics.collector import get_metrics_hub

    return get_metrics_hub()


_PERIOD_DAYS: dict[str, int] = {"1d": 1, "7d": 7, "30d": 30}


def _session_stats(
    hub: MetricsHub, tool_name: str | None,
) -> tuple[Any, list[dict[str, Any]]]:
    """Compute stats from in-memory session data."""
    from tapps_mcp.metrics.execution_metrics import ToolCallMetricsCollector

    recent = hub.execution.get_recent(limit=100)
    summary = ToolCallMetricsCollector._compute_summary(recent)

    by_tool: dict[str, list[Any]] = {}
    for m in recent:
        by_tool.setdefault(m.tool_name, []).append(m)

    breakdowns = []
    for tname, tmetrics in sorted(by_tool.items()):
        if tool_name and tname != tool_name:
            continue
        ts = ToolCallMetricsCollector._compute_summary(tmetrics)
        breakdowns.append({
            "tool_name": tname,
            "call_count": ts.total_calls,
            "success_rate": ts.success_rate,
            "avg_duration_ms": ts.avg_duration_ms,
            "p95_duration_ms": ts.p95_duration_ms,
        })
    return summary, breakdowns


def _period_stats(
    hub: MetricsHub, tool_name: str | None, period: str,
) -> tuple[Any, list[dict[str, Any]]]:
    """Compute stats from persisted data for a given time period."""
    from datetime import UTC, datetime, timedelta

    since: datetime | None = None
    days = _PERIOD_DAYS.get(period)
    if days is not None:
        since = datetime.now(tz=UTC) - timedelta(days=days)

    summary = hub.execution.get_summary(since=since)
    raw = hub.execution.get_summary_by_tool(since=since)
    breakdowns = [
        {
            "tool_name": b.tool_name,
            "call_count": b.call_count,
            "success_rate": b.success_rate,
            "avg_duration_ms": b.avg_duration_ms,
            "p95_duration_ms": b.p95_duration_ms,
        }
        for b in raw
        if not tool_name or b.tool_name == tool_name
    ]
    return summary, breakdowns


@mcp.tool()
async def tapps_dashboard(
    output_format: str = "json",
    time_range: str = "7d",
    sections: list[str] | None = None,
) -> dict[str, Any]:
    """Generate a comprehensive metrics dashboard.

    Call this to review how well TappsMCP is performing - scoring accuracy,
    gate pass rates, expert effectiveness, cache performance, quality trends,
    and alerts.

    Args:
        output_format: Output format - "json" (default), "markdown", "html", or "otel".
        time_range: Time range - "1d", "7d", "30d", "90d".
        sections: Specific sections to include (default: all).
            Options: summary, tool_metrics, scoring_trends, expert_metrics,
            cache_metrics, quality_distribution, alerts, business_metrics,
            recommendations.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_dashboard")

    hub = _get_metrics_hub()

    if output_format == "otel":
        from tapps_mcp.metrics.otel_export import export_otel_trace

        recent = hub.execution.get_recent(limit=100)
        otel_data = export_otel_trace(recent)
        elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
        _record_execution("tapps_dashboard", start)
        resp = success_response("tapps_dashboard", elapsed_ms, otel_data)
        return _with_nudges("tapps_dashboard", resp)

    dashboard = hub.get_dashboard_generator()

    if output_format == "json":
        data = dashboard.generate_json_dashboard(sections=sections)
    elif output_format == "markdown":
        content = dashboard.generate_markdown_dashboard(sections=sections)
        data = {"format": "markdown", "content": content}
    elif output_format == "html":
        content = dashboard.generate_html_dashboard(sections=sections)
        path = dashboard.save_dashboard(fmt="html", sections=sections)
        data = {"format": "html", "content": content, "saved_to": str(path)}
    else:
        data = dashboard.generate_json_dashboard(sections=sections)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_dashboard", start)
    resp = success_response("tapps_dashboard", elapsed_ms, data)
    return _with_nudges("tapps_dashboard", resp)


@mcp.tool()
def tapps_stats(
    tool_name: str | None = None,
    period: str = "session",
) -> dict[str, Any]:
    """Return usage statistics for TappsMCP tools.

    Shows call counts, success rates, average durations, cache hit rates,
    and gate pass rates.

    Args:
        tool_name: Filter stats to a specific tool (optional).
        period: Stats period - "session", "1d", "7d", "30d", "all".
    """
    start = time.perf_counter_ns()
    _record_call("tapps_stats")

    hub = _get_metrics_hub()

    if period == "session":
        summary, tool_breakdowns = _session_stats(hub, tool_name)
    else:
        summary, tool_breakdowns = _period_stats(hub, tool_name, period)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_stats", start)

    resp = success_response("tapps_stats", elapsed_ms, {
        "period": period,
        "total_calls": summary.total_calls,
        "success_rate": summary.success_rate,
        "avg_duration_ms": summary.avg_duration_ms,
        "p95_duration_ms": summary.p95_duration_ms,
        "gate_pass_rate": summary.gate_pass_rate,
        "avg_score": summary.avg_score,
        "tools": tool_breakdowns,
    })
    return _with_nudges("tapps_stats", resp)


@mcp.tool()
def tapps_feedback(
    tool_name: str,
    helpful: bool,
    context: str | None = None,
) -> dict[str, Any]:
    """Report whether a tool's output was helpful.

    This feedback improves TappsMCP's adaptive scoring and expert weights
    over time.

    Args:
        tool_name: Which tool to provide feedback on.
        helpful: Was the output helpful?
        context: Additional context about why it was or wasn't helpful.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_feedback")

    from tapps_mcp.metrics.feedback import FeedbackTracker

    hub = _get_metrics_hub()
    tracker = FeedbackTracker(hub.metrics_dir)

    tracker.record(
        tool_name=tool_name,
        helpful=helpful,
        context=context or "",
        session_id=hub.session_id,
    )

    stats = tracker.get_statistics(tool_name=tool_name)
    overall_stats = tracker.get_statistics()

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_feedback", start)

    resp = success_response("tapps_feedback", elapsed_ms, {
        "recorded": True,
        "tool_name": tool_name,
        "helpful": helpful,
        "tool_stats": stats,
        "overall_stats": overall_stats,
    })
    return _with_nudges("tapps_feedback", resp)


# ---------------------------------------------------------------------------
# MCP Resources -- browsable knowledge and configuration
# ---------------------------------------------------------------------------


@mcp.resource("tapps://knowledge/{domain}/{topic}")
def get_knowledge_resource(domain: str, topic: str) -> str:
    """Retrieve expert knowledge for a domain and topic.

    Browse the 119 knowledge files across 16 expert domains.
    """
    import re
    from pathlib import Path

    from tapps_mcp.experts.registry import ExpertRegistry

    if domain not in ExpertRegistry.TECHNICAL_DOMAINS:
        valid = ", ".join(sorted(ExpertRegistry.TECHNICAL_DOMAINS))
        return f"Unknown domain: {domain}. Valid domains: {valid}"

    # Sanitise topic to prevent path traversal (alphanumeric, hyphens, underscores only)
    if not re.match(r"^[a-zA-Z0-9_-]+$", topic):
        return f"Invalid topic name: '{topic}'. Use only alphanumeric, hyphens, underscores."

    knowledge_dir = Path(__file__).parent / "experts" / "knowledge" / domain
    topic_file = knowledge_dir / f"{topic}.md"

    # Verify resolved path stays within the knowledge directory
    try:
        topic_file.resolve().relative_to(knowledge_dir.resolve())
    except ValueError:
        return f"Invalid topic path: '{topic}'."

    if not topic_file.exists():
        # List available topics
        if knowledge_dir.exists():
            available = [f.stem for f in knowledge_dir.glob("*.md")]
            avail_str = ", ".join(sorted(available))
            return f"Topic '{topic}' not found in domain '{domain}'. Available: {avail_str}"
        return f"No knowledge directory for domain '{domain}'."

    return topic_file.read_text(encoding="utf-8")


@mcp.resource("tapps://knowledge/domains")
def list_knowledge_domains() -> str:
    """List all available expert knowledge domains and their topics."""
    from pathlib import Path

    knowledge_base = Path(__file__).parent / "experts" / "knowledge"
    lines = ["# TappsMCP Knowledge Domains\n"]

    for domain_dir in sorted(knowledge_base.iterdir()):
        if not domain_dir.is_dir():
            continue
        topics = sorted(f.stem for f in domain_dir.glob("*.md") if f.stem != "README")
        lines.append(f"\n## {domain_dir.name}")
        lines.append(f"Topics ({len(topics)}):")
        for t in topics:
            lines.append(f"  - {t}")

    return "\n".join(lines)


@mcp.resource("tapps://config/quality-presets")
def get_quality_presets() -> str:
    """Get available quality gate presets and their thresholds."""
    from tapps_mcp.config.settings import PRESETS

    lines = ["# Quality Gate Presets\n"]
    for name, thresholds in PRESETS.items():
        lines.append(f"## {name}")
        for key, value in thresholds.items():
            lines.append(f"  {key}: {value}")
        lines.append("")

    return "\n".join(lines)


@mcp.resource("tapps://config/scoring-weights")
def get_scoring_weights() -> str:
    """Get current scoring category weights."""
    settings = load_settings()
    w = settings.scoring_weights

    lines = ["# Scoring Weights\n"]
    from tapps_mcp.config.settings import ScoringWeights

    for field_name in ScoringWeights.model_fields:
        lines.append(f"  {field_name}: {getattr(w, field_name)}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MCP Prompts -- workflow guidance
# ---------------------------------------------------------------------------


@mcp.prompt()
def tapps_workflow(task_type: str = "general") -> str:
    """Generate the TappsMCP workflow prompt for a specific task type.

    Provides tool call order and recommendations based on the task type.

    Args:
        task_type: One of: general, feature, bugfix, refactor, security, review.
    """
    workflows = {
        "general": (
            "TappsMCP Workflow - General\n\n"
            "1. tapps_server_info - discover capabilities\n"
            "2. tapps_project_profile - understand the project\n"
            "3. tapps_score_file(quick=True) - quick scoring during edits\n"
            "4. tapps_score_file - full scoring before completion\n"
            "5. tapps_quality_gate - verify quality bar\n"
            "6. tapps_checklist(task_type='review') - verify completeness"
        ),
        "feature": (
            "TappsMCP Workflow - New Feature\n\n"
            "1. tapps_server_info - discover capabilities\n"
            "2. tapps_project_profile - understand the project\n"
            "3. tapps_lookup_docs - check library APIs before coding\n"
            "4. tapps_consult_expert - get domain guidance\n"
            "5. tapps_score_file(quick=True) - quick scoring during edits\n"
            "6. tapps_score_file - full scoring\n"
            "7. tapps_security_scan - check for vulnerabilities\n"
            "8. tapps_quality_gate - verify quality bar\n"
            "9. tapps_checklist(task_type='feature') - verify completeness"
        ),
        "bugfix": (
            "TappsMCP Workflow - Bug Fix\n\n"
            "1. tapps_server_info - discover capabilities\n"
            "2. tapps_impact_analysis - understand blast radius\n"
            "3. tapps_score_file(quick=True) - quick scoring during fix\n"
            "4. tapps_score_file - full scoring after fix\n"
            "5. tapps_quality_gate - verify quality bar\n"
            "6. tapps_checklist(task_type='bugfix') - verify completeness"
        ),
        "refactor": (
            "TappsMCP Workflow - Refactoring\n\n"
            "1. tapps_server_info - discover capabilities\n"
            "2. tapps_impact_analysis - understand dependencies\n"
            "3. tapps_consult_expert(domain='software-architecture') - get guidance\n"
            "4. tapps_score_file(quick=True) - quick scoring during refactor\n"
            "5. tapps_score_file - full scoring\n"
            "6. tapps_quality_gate - verify quality bar\n"
            "7. tapps_checklist(task_type='refactor') - verify completeness"
        ),
        "security": (
            "TappsMCP Workflow - Security Review\n\n"
            "1. tapps_server_info - discover capabilities\n"
            "2. tapps_security_scan - comprehensive security scan\n"
            "3. tapps_consult_expert(domain='security') - get security guidance\n"
            "4. tapps_score_file - full scoring with security focus\n"
            "5. tapps_quality_gate(preset='strict') - strict quality bar\n"
            "6. tapps_checklist(task_type='security') - verify completeness"
        ),
        "review": (
            "TappsMCP Workflow - Code Review\n\n"
            "1. tapps_server_info - discover capabilities\n"
            "2. tapps_score_file - full scoring\n"
            "3. tapps_security_scan - security check\n"
            "4. tapps_quality_gate - verify quality bar\n"
            "5. tapps_checklist(task_type='review') - verify completeness"
        ),
    }
    return workflows.get(task_type, workflows["general"])


# ---------------------------------------------------------------------------
# Server runner
# ---------------------------------------------------------------------------


def run_server(
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """Start the TappsMCP MCP server.

    Args:
        transport: ``"stdio"`` for local MCP hosts, ``"http"`` for remote.
        host: Bind address for HTTP transport.
        port: Bind port for HTTP transport.
    """
    settings = load_settings()
    setup_logging(level=settings.log_level, json_output=settings.log_json)

    logger.info(
        "tapps_mcp_starting",
        version=__version__,
        transport=transport,
        project_root=str(settings.project_root),
        quality_preset=settings.quality_preset,
    )

    if transport == "stdio":
        mcp.run(transport="stdio")
    elif transport == "http":
        # Streamable HTTP via uvicorn; wrap so GET / returns a simple "running" page
        import uvicorn
        from starlette.requests import Request  # noqa: TC002
        from starlette.responses import HTMLResponse
        from starlette.routing import Route

        mcp_app = mcp.streamable_http_app()

        def _root(_request: Request) -> HTMLResponse:
            return HTMLResponse(
                "<!DOCTYPE html><html><head><title>TappMCP</title></head><body>"
                "<h1>TappMCP is running</h1><p>MCP endpoint: <a href='/mcp'>/mcp</a></p>"
                "<p>Version: " + __version__ + "</p></body></html>",
                status_code=200,
            )

        # Add root route directly to the MCP app so its lifespan
        # (task group init) runs properly — wrapping in a parent
        # Starlette breaks the lifespan chain.
        mcp_app.routes.insert(0, Route("/", _root))
        uvicorn.run(mcp_app, host=host, port=port)
    else:
        msg = f"Unsupported transport: {transport}"
        raise ValueError(msg)

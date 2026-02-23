"""TappsMCP MCP server entry point.

Creates the FastMCP server instance, registers all tools, and provides
``run_server()`` for the CLI.

Tool handlers are split across modules for maintainability:
  - ``server_scoring_tools``: tapps_score_file, tapps_quality_gate, tapps_quick_check
  - ``server_pipeline_tools``: tapps_validate_changed, tapps_session_start, tapps_init
  - ``server_metrics_tools``: tapps_dashboard, tapps_stats, tapps_feedback, tapps_research
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
from mcp.types import ToolAnnotations

from tapps_mcp import __version__
from tapps_mcp.common.logging import setup_logging
from tapps_mcp.config.settings import load_settings
from tapps_mcp.server_helpers import error_response, serialize_issues, success_response
from tapps_mcp.tools.tool_detection import detect_installed_tools

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Tool annotation presets
# ---------------------------------------------------------------------------

_ANNOTATIONS_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

_ANNOTATIONS_READ_ONLY_OPEN = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=True,
)

# ---------------------------------------------------------------------------
# FastMCP server instance
# ---------------------------------------------------------------------------

mcp = FastMCP("TappsMCP")


# ---------------------------------------------------------------------------
# Helpers (shared by tool modules via lazy import)
# ---------------------------------------------------------------------------


_MIN_DRIVE_PATH_LEN = 2


def _normalize_path_for_mapping(path: str) -> str:
    """Normalize a path string for host-root prefix comparison (cross-platform)."""
    s = path.strip().replace("\\", "/")
    if s and s[1:2] == ":" and len(s) >= _MIN_DRIVE_PATH_LEN:
        s = s[0].lower() + s[1:]
    return s.rstrip("/") or "/"


def _validate_file_path(file_path: str) -> Path:
    """Validate *file_path* against the project root boundary."""
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


_LIBRARY_DOMAIN_MAP: dict[str, str] = {}
for _domain, _libs in {
    "testing-strategies": ("pytest", "unittest", "mock", "coverage", "hypothesis"),
    "api-design-integration": ("fastapi", "flask", "django", "starlette", "httpx", "requests"),
    "database-data-management": ("sqlalchemy", "alembic", "psycopg", "redis"),
    "cloud-infrastructure": ("docker", "kubernetes", "docker-compose"),
    "code-quality-analysis": ("pydantic", "mypy", "ruff"),
    "security": ("security", "cryptography", "pyjwt", "bandit"),
}.items():
    for _lib in _libs:
        _LIBRARY_DOMAIN_MAP[_lib] = _domain

_EXPERT_FALLBACK_MIN_CONFIDENCE = 0.3


def _library_to_domain(library: str) -> str:
    """Map library name to best-matching expert domain for fallback lookup."""
    return _LIBRARY_DOMAIN_MAP.get(library.lower(), "software-architecture")


_checklist_persist_configured: bool = False


def _record_call(tool_name: str) -> None:
    """Record a tool call in the session checklist tracker."""
    global _checklist_persist_configured  # noqa: PLW0603
    try:
        from tapps_mcp.tools.checklist import CallTracker

        if not _checklist_persist_configured:
            settings = load_settings()
            sessions_dir = settings.project_root / ".tapps-mcp" / "sessions"
            persist_path = sessions_dir / "checklist_calls.jsonl"
            CallTracker.set_persist_path(persist_path)
            _checklist_persist_configured = True
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


def _get_metrics_hub() -> MetricsHub:
    """Lazily import and return the global MetricsHub."""
    from tapps_mcp.metrics.collector import get_metrics_hub

    return get_metrics_hub()


def _with_nudges(
    tool_name: str,
    response: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Inject ``next_steps`` and ``pipeline_progress`` into a response dict."""
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
# Core tools (kept in server.py — simple, few dependencies)
# ---------------------------------------------------------------------------


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY)
def tapps_server_info() -> dict[str, Any]:
    """REQUIRED at session start. Discovers server version, available tools,
    installed checkers (ruff, mypy, bandit, radon), and configuration.
    Skipping means subsequent tools lack context and recommendations are generic.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_server_info")

    settings = load_settings()
    installed = detect_installed_tools()

    from tapps_mcp.diagnostics import collect_diagnostics

    cache_dir = settings.project_root / ".tapps-mcp-cache"
    diagnostics = collect_diagnostics(api_key=settings.context7_api_key, cache_dir=cache_dir)

    available_tools: list[str] = []
    try:
        tool_manager = mcp._tool_manager
        available_tools = list(tool_manager._tools.keys())
    except AttributeError:
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
            "tapps_research",
        ]

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_server_info", start)

    from tapps_mcp.pipeline.models import STAGE_TOOLS, PipelineStage

    resp = success_response(
        "tapps_server_info",
        elapsed_ms,
        {
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
                "BEFORE using any library: Call tapps_lookup_docs(). "
                "AFTER editing Python files: "
                "Call tapps_score_file(quick=True) or tapps_quick_check(). "
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
        },
    )
    return _with_nudges("tapps_server_info", resp)


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY)
def tapps_security_scan(file_path: str, scan_secrets: bool = True) -> dict[str, Any]:
    """REQUIRED when changes touch security-sensitive code. Runs bandit and
    secret detection on a Python file.

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


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY_OPEN)
async def tapps_lookup_docs(
    library: str,
    topic: str = "overview",
    mode: str = "code",
) -> dict[str, Any]:
    """BLOCKING REQUIREMENT before using any external library API. Returns
    current docs (Context7 + cache) to prevent hallucinated APIs.

    Args:
        library: Library name (fuzzy-matched).
        topic: Specific topic within the library (default "overview").
        mode: "code" for API references, "info" for conceptual guides.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_lookup_docs")

    from tapps_mcp.knowledge.cache import KBCache
    from tapps_mcp.knowledge.lookup import LookupEngine

    settings = load_settings()
    cache = KBCache(settings.project_root / ".tapps-mcp-cache")
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
        # Expert fallback when Context7 and cache fail — provide RAG-backed guidance
        try:
            from tapps_mcp.experts.engine import consult_expert

            cr = consult_expert(
                question=f"How do I use {library} for {topic}? Best practices and API usage.",
                domain=_library_to_domain(library),
                max_chunks=3,
                max_context_length=1500,
            )
            if cr.confidence >= _EXPERT_FALLBACK_MIN_CONFIDENCE and cr.answer:
                response["expert_fallback"] = {
                    "content": cr.answer,
                    "confidence": round(cr.confidence, 2),
                    "sources": cr.sources[:3],
                }
                response["error"]["message"] += (
                    " Expert knowledge base fallback provided — use tapps_consult_expert "
                    "for more targeted questions."
                )
        except Exception:
            logger.debug("expert_fallback_failed", library=library, topic=topic)
    if result.warning:
        response["warning"] = result.warning
    return _with_nudges("tapps_lookup_docs", response)


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY)
def tapps_validate_config(file_path: str, config_type: str = "auto") -> dict[str, Any]:
    """REQUIRED when changing Dockerfile, docker-compose, or infra config.

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

    resp = success_response(
        "tapps_validate_config",
        elapsed_ms,
        {
            "file_path": result.file_path,
            "config_type": result.config_type,
            "valid": result.valid,
            "findings": [f.model_dump() for f in result.findings],
            "suggestions": result.suggestions,
            "finding_count": len(result.findings),
            "critical_count": sum(1 for f in result.findings if f.severity == "critical"),
            "warning_count": sum(1 for f in result.findings if f.severity == "warning"),
        },
    )
    return _with_nudges("tapps_validate_config", resp)


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY)
def tapps_consult_expert(question: str, domain: str = "") -> dict[str, Any]:
    """REQUIRED for domain-specific decisions. Routes to one of 16 built-in
    experts and returns RAG-backed guidance with confidence scores.

    Args:
        question: The technical question to ask (natural language).
        domain: Optional domain override (e.g. "security", "testing-strategies").
    """
    start = time.perf_counter_ns()
    _record_call("tapps_consult_expert")

    from tapps_mcp.experts.engine import consult_expert

    result = consult_expert(question=question, domain=domain or None)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_consult_expert", start)

    resp = success_response(
        "tapps_consult_expert",
        elapsed_ms,
        {
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
        },
    )
    return _with_nudges("tapps_consult_expert", resp)


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY)
def tapps_list_experts() -> dict[str, Any]:
    """Returns the 16 built-in experts with domain, description, and knowledge-base status."""
    start = time.perf_counter_ns()
    _record_call("tapps_list_experts")

    from tapps_mcp.experts.engine import list_experts

    experts = list_experts()
    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_list_experts", start)

    resp = success_response(
        "tapps_list_experts",
        elapsed_ms,
        {
            "expert_count": len(experts),
            "experts": [e.model_dump() for e in experts],
        },
    )
    return _with_nudges("tapps_list_experts", resp)


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY)
def tapps_checklist(task_type: str = "review") -> dict[str, Any]:
    """REQUIRED as the FINAL step before declaring work complete.

    Args:
        task_type: "feature" | "bugfix" | "refactor" | "security" | "review".
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
                "Module tapps_mcp.tools.checklist is not available. "
                "Use tapps_quality_gate and tapps_security_scan for verification."
            ),
        }
        resp = success_response("tapps_checklist", elapsed_ms, fallback_data)
        return _with_nudges("tapps_checklist", resp, {"complete": False})


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY)
def tapps_project_profile(project_root: str = "") -> dict[str, Any]:
    """REQUIRED at session start. Detects the project's tech stack, type, CI,
    Docker, test frameworks, and package managers.

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
            "tapps_project_profile",
            start,
            status="failed",
            error_code="profile_failed",
        )
        return error_response("tapps_project_profile", "profile_failed", str(exc))

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_project_profile", start)

    resp = success_response(
        "tapps_project_profile",
        elapsed_ms,
        {
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
        },
    )
    return _with_nudges("tapps_project_profile", resp)


# Session note store singleton
_session_store: SessionNoteStore | None = None


def _get_session_store() -> SessionNoteStore:
    """Lazily create or return the session note store."""
    global _session_store  # noqa: PLW0603
    if _session_store is None:
        from tapps_mcp.project.session_notes import SessionNoteStore

        settings = load_settings()
        _session_store = SessionNoteStore(settings.project_root)
    return _session_store


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY)
def tapps_session_notes(action: str, key: str = "", value: str = "") -> dict[str, Any]:
    """Persist notes across the session to avoid losing context.

    Args:
        action: "save" | "get" | "list" | "clear".
        key: Note key (required for save/get).
        value: Note value (required for save).
    """
    start = time.perf_counter_ns()
    _record_call("tapps_session_notes")

    store = _get_session_store()
    data: dict[str, Any] = {}

    if action == "save":
        if not key or not value:
            return error_response(
                "tapps_session_notes",
                "missing_params",
                "save requires key and value",
            )
        note = store.save(key, value)
        data = {"action": "save", "note": note.model_dump()}
    elif action == "get":
        if not key:
            return error_response("tapps_session_notes", "missing_params", "get requires key")
        found = store.get(key)
        data = {
            "action": "get",
            "note": found.model_dump() if found else None,
            "found": found is not None,
        }
    elif action == "list":
        data = {"action": "list", "notes": [n.model_dump() for n in store.list_all()]}
    elif action == "clear":
        data = {"action": "clear", "cleared_count": store.clear(key or None)}
    else:
        return error_response(
            "tapps_session_notes",
            "invalid_action",
            f"Unknown action: {action}. Use save/get/list/clear.",
        )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_session_notes", start)
    data.update(store.metadata())
    resp = success_response("tapps_session_notes", elapsed_ms, data)
    return _with_nudges("tapps_session_notes", resp)


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY)
def tapps_impact_analysis(file_path: str, change_type: str = "modified") -> dict[str, Any]:
    """REQUIRED before refactoring or deleting files. Maps the blast radius.

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

    resp = success_response(
        "tapps_impact_analysis",
        elapsed_ms,
        {
            "changed_file": report.changed_file,
            "change_type": report.change_type,
            "severity": report.severity,
            "total_affected": report.total_affected,
            "direct_dependents": [d.model_dump() for d in report.direct_dependents],
            "transitive_dependents": [d.model_dump() for d in report.transitive_dependents],
            "test_files": [t.model_dump() for t in report.test_files],
            "recommendations": report.recommendations,
        },
    )
    return _with_nudges("tapps_impact_analysis", resp)


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY)
async def tapps_report(
    file_path: str = "",
    report_format: str = "json",
    max_files: int = 20,
) -> dict[str, Any]:
    """Generate a quality report combining scoring and gate results.

    Args:
        file_path: Path to a Python file (optional - project-wide if omitted).
        report_format: "json" | "markdown" | "html".
        max_files: Maximum files to score for project-wide report (default 20).
    """
    import asyncio

    start = time.perf_counter_ns()
    _record_call("tapps_report")

    from tapps_mcp.gates.evaluator import evaluate_gate
    from tapps_mcp.project.report import generate_report
    from tapps_mcp.scoring.scorer import CodeScorer

    settings = load_settings()
    scorer = CodeScorer()
    score_results: list[Any] = []
    gate_results: list[Any] = []

    if file_path:
        try:
            resolved = _validate_file_path(file_path)
        except (ValueError, FileNotFoundError) as exc:
            return error_response("tapps_report", "path_denied", str(exc))
        result = await scorer.score_file(resolved)
        score_results.append(result)
        gate_results.append(evaluate_gate(result, preset=settings.quality_preset))
    else:
        from pathlib import Path as _Path

        from tapps_mcp.common.utils import should_skip_path

        py_files = sorted(_Path(settings.project_root).rglob("*.py"))
        py_files = [f for f in py_files if not should_skip_path(f)][: max(1, max_files)]

        async def _score_one(pf: _Path) -> tuple[Any, Any] | None:
            try:
                res = await scorer.score_file(pf)
                return res, evaluate_gate(res, preset=settings.quality_preset)
            except (ValueError, OSError, RuntimeError) as e:
                logger.warning("report_file_skip", file=str(pf), error=str(e))
                return None

        tasks = [_score_one(pf) for pf in py_files]
        outcomes = await asyncio.gather(*tasks, return_exceptions=False)
        for out in outcomes:
            if out is not None:
                score_results.append(out[0])
                gate_results.append(out[1])

    report_data = generate_report(score_results, gate_results, report_format=report_format)
    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_report", start, file_path=file_path or None)
    resp = success_response("tapps_report", elapsed_ms, report_data)
    return _with_nudges("tapps_report", resp)


# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------


@mcp.resource("tapps://knowledge/{domain}/{topic}")
def get_knowledge_resource(domain: str, topic: str) -> str:
    """Retrieve expert knowledge for a domain and topic."""
    import re
    from pathlib import Path

    from tapps_mcp.experts.registry import ExpertRegistry

    if domain not in ExpertRegistry.TECHNICAL_DOMAINS:
        valid = ", ".join(sorted(ExpertRegistry.TECHNICAL_DOMAINS))
        return f"Unknown domain: {domain}. Valid domains: {valid}"

    if not re.match(r"^[a-zA-Z0-9_-]+$", topic):
        return f"Invalid topic name: '{topic}'. Use only alphanumeric, hyphens, underscores."

    knowledge_dir = Path(__file__).parent / "experts" / "knowledge" / domain
    topic_file = knowledge_dir / f"{topic}.md"

    try:
        topic_file.resolve().relative_to(knowledge_dir.resolve())
    except ValueError:
        return f"Invalid topic path: '{topic}'."

    if not topic_file.exists():
        if knowledge_dir.exists():
            available = [f.stem for f in knowledge_dir.glob("*.md")]
            avail = ", ".join(sorted(available))
            return f"Topic '{topic}' not found in domain '{domain}'. Available: {avail}"
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
    from tapps_mcp.config.settings import ScoringWeights

    lines = ["# Scoring Weights\n"]
    for field_name in ScoringWeights.model_fields:
        lines.append(f"  {field_name}: {getattr(w, field_name)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MCP Prompts
# ---------------------------------------------------------------------------


@mcp.prompt()
def tapps_pipeline(stage: str = "discover") -> str:
    """TAPPS quality pipeline - structured 5-stage workflow.

    Args:
        stage: Pipeline stage to get instructions for.
    """
    from tapps_mcp.prompts.prompt_loader import load_stage_prompt

    return load_stage_prompt(stage)


@mcp.prompt()
def tapps_pipeline_overview() -> str:
    """Get a summary of the full TAPPS 5-stage quality pipeline."""
    from tapps_mcp.prompts.prompt_loader import load_overview

    return load_overview()


@mcp.prompt()
def tapps_workflow(task_type: str = "general") -> str:
    """Generate the TappsMCP workflow prompt for a specific task type.

    Args:
        task_type: One of: general, feature, bugfix, refactor, security, review.
    """
    workflows = {
        "general": (
            "TappsMCP Workflow - General\n\n"
            "1. tapps_server_info\n2. tapps_project_profile\n"
            "3. tapps_score_file(quick=True)\n4. tapps_score_file\n"
            "5. tapps_quality_gate\n6. tapps_checklist(task_type='review')"
        ),
        "feature": (
            "TappsMCP Workflow - New Feature\n\n"
            "1. tapps_server_info\n2. tapps_project_profile\n"
            "3. tapps_lookup_docs\n4. tapps_consult_expert\n"
            "5. tapps_score_file(quick=True)\n6. tapps_score_file\n"
            "7. tapps_security_scan\n8. tapps_quality_gate\n"
            "9. tapps_checklist(task_type='feature')"
        ),
        "bugfix": (
            "TappsMCP Workflow - Bug Fix\n\n"
            "1. tapps_server_info\n2. tapps_impact_analysis\n"
            "3. tapps_score_file(quick=True)\n4. tapps_score_file\n"
            "5. tapps_quality_gate\n6. tapps_checklist(task_type='bugfix')"
        ),
        "refactor": (
            "TappsMCP Workflow - Refactoring\n\n"
            "1. tapps_server_info\n2. tapps_impact_analysis\n"
            "3. tapps_consult_expert(domain='software-architecture')\n"
            "4. tapps_score_file(quick=True)\n5. tapps_score_file\n"
            "6. tapps_quality_gate\n7. tapps_checklist(task_type='refactor')"
        ),
        "security": (
            "TappsMCP Workflow - Security Review\n\n"
            "1. tapps_server_info\n2. tapps_security_scan\n"
            "3. tapps_consult_expert(domain='security')\n"
            "4. tapps_score_file\n5. tapps_quality_gate(preset='strict')\n"
            "6. tapps_checklist(task_type='security')"
        ),
        "review": (
            "TappsMCP Workflow - Code Review\n\n"
            "1. tapps_server_info\n2. tapps_score_file\n"
            "3. tapps_security_scan\n4. tapps_quality_gate\n"
            "5. tapps_checklist(task_type='review')"
        ),
    }
    return workflows.get(task_type, workflows["general"])


# ---------------------------------------------------------------------------
# Register tools from extracted modules & re-export for backward compatibility
# ---------------------------------------------------------------------------

from tapps_mcp import (  # noqa: E402
    server_metrics_tools,
    server_pipeline_tools,
    server_scoring_tools,
)

server_scoring_tools.register(mcp)
server_pipeline_tools.register(mcp)
server_metrics_tools.register(mcp)

# Re-export so ``from tapps_mcp.server import tapps_X`` keeps working
tapps_score_file = server_scoring_tools.tapps_score_file
tapps_quality_gate = server_scoring_tools.tapps_quality_gate
tapps_quick_check = server_scoring_tools.tapps_quick_check
tapps_validate_changed = server_pipeline_tools.tapps_validate_changed
tapps_session_start = server_pipeline_tools.tapps_session_start
tapps_init = server_pipeline_tools.tapps_init
tapps_dashboard = server_metrics_tools.tapps_dashboard
tapps_stats = server_metrics_tools.tapps_stats
tapps_feedback = server_metrics_tools.tapps_feedback
tapps_research = server_metrics_tools.tapps_research


# ---------------------------------------------------------------------------
# Server runner
# ---------------------------------------------------------------------------


def run_server(
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """Start the TappsMCP MCP server."""
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
        import uvicorn
        from starlette.requests import Request  # noqa: TC002
        from starlette.responses import HTMLResponse
        from starlette.routing import Route

        mcp_app = mcp.streamable_http_app()

        def _root(_request: Request) -> HTMLResponse:
            return HTMLResponse(
                "<!DOCTYPE html><html><head><title>TappsMCP</title></head><body>"
                "<h1>TappsMCP is running</h1><p>MCP endpoint: <a href='/mcp'>/mcp</a></p>"
                "<p>Version: " + __version__ + "</p></body></html>",
                status_code=200,
            )

        mcp_app.routes.insert(0, Route("/", _root))
        uvicorn.run(mcp_app, host=host, port=port)
    else:
        msg = f"Unsupported transport: {transport}"
        raise ValueError(msg)

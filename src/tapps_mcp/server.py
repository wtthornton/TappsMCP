"""TappsMCP MCP server entry point.

Creates the FastMCP server instance, registers all tools, and provides
``run_server()`` for the CLI.

Tool handlers are split across modules for maintainability:
  - ``server_scoring_tools``: tapps_score_file, tapps_quality_gate, tapps_quick_check
  - ``server_pipeline_tools``: tapps_validate_changed, tapps_session_start, tapps_init
  - ``server_metrics_tools``: tapps_dashboard, tapps_stats, tapps_feedback, tapps_research
"""

from __future__ import annotations

import asyncio
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
from tapps_mcp.tools.tool_detection import (
    detect_installed_tools,
    detect_installed_tools_async,
)

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

# ---------------------------------------------------------------------------
# Constants extracted to avoid duplication
# ---------------------------------------------------------------------------

_FALLBACK_TOOL_LIST: list[str] = [
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
    "tapps_upgrade",
    "tapps_doctor",
    "tapps_set_engagement_level",
    "tapps_dashboard",
    "tapps_stats",
    "tapps_feedback",
    "tapps_research",
    "tapps_dead_code",
    "tapps_dependency_scan",
    "tapps_dependency_graph",
]

_SECURITY_SCAN_FINDING_LIMIT: int = 50

_VALID_CONFIG_TYPES: frozenset[str] = frozenset({
    "dockerfile",
    "docker_compose",
    "websocket",
    "mqtt",
    "influxdb",
})

_MAX_CONFIG_FILE_SIZE: int = 1_048_576  # 1 MB

_VALID_LOOKUP_MODES: frozenset[str] = frozenset({"code", "info"})


def _get_available_tools() -> list[str]:
    """Return the list of registered MCP tools, with fallback to a static list."""
    try:
        tool_manager = mcp._tool_manager
        return list(tool_manager._tools.keys())
    except AttributeError:
        logger.warning("mcp_tool_manager_inaccessible", hint="using fallback tool list")
        return list(_FALLBACK_TOOL_LIST)


def _build_server_info_data(
    settings: Any,
    installed: Any,
    diagnostics: Any,
    available_tools: list[str],
) -> dict[str, Any]:
    """Build the data dict for tapps_server_info / _server_info_async."""
    from tapps_mcp.pipeline.models import STAGE_TOOLS, PipelineStage

    return {
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
    }


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
    """Inject ``next_steps``, ``pipeline_progress``, and ``suggested_workflow`` into a response."""
    if not response.get("success", False):
        return response
    from tapps_mcp.common.nudges import (
        compute_next_steps,
        compute_pipeline_progress,
        compute_suggested_workflow,
    )

    steps = compute_next_steps(tool_name, context)
    progress = compute_pipeline_progress()
    workflow = compute_suggested_workflow(tool_name, context)
    data = response.get("data", {})
    if steps:
        data["next_steps"] = steps
    if progress:
        data["pipeline_progress"] = progress
    if workflow:
        data["suggested_workflow"] = workflow
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

    available_tools = _get_available_tools()

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_server_info", start)

    data = _build_server_info_data(settings, installed, diagnostics, available_tools)
    resp = success_response("tapps_server_info", elapsed_ms, data)
    return _with_nudges("tapps_server_info", resp)


async def _server_info_async() -> dict[str, Any]:
    """Async variant of ``tapps_server_info`` for use by ``tapps_session_start``.

    Runs tool detection in parallel (via ``detect_installed_tools_async``)
    and diagnostics in a thread pool to avoid blocking the event loop.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_server_info")

    settings = load_settings()

    from tapps_mcp.diagnostics import collect_diagnostics

    cache_dir = settings.project_root / ".tapps-mcp-cache"

    # Run tool detection (parallel subprocesses) and diagnostics concurrently
    installed, diagnostics = await asyncio.gather(
        detect_installed_tools_async(),
        asyncio.to_thread(
            collect_diagnostics, api_key=settings.context7_api_key, cache_dir=cache_dir
        ),
    )

    available_tools = _get_available_tools()

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_server_info", start)

    data = _build_server_info_data(settings, installed, diagnostics, available_tools)
    resp = success_response("tapps_server_info", elapsed_ms, data)
    return _with_nudges("tapps_server_info", resp)


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY)
def tapps_security_scan(file_path: str, scan_secrets: bool = True) -> dict[str, Any]:
    """REQUIRED when changes touch security-sensitive code. Runs bandit and
    secret detection on a Python file.

    Args:
        file_path: Path to the Python file to scan.
        scan_secrets: Whether to scan for hardcoded secrets (default: True).
    """
    from tapps_mcp.server_helpers import ensure_session_initialized_sync

    start = time.perf_counter_ns()
    _record_call("tapps_security_scan")
    ensure_session_initialized_sync()

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
            "bandit_issues": serialize_issues(
                result.bandit_issues, limit=_SECURITY_SCAN_FINDING_LIMIT
            ),
            "secret_findings": serialize_issues(
                result.secret_findings, limit=_SECURITY_SCAN_FINDING_LIMIT
            ),
        },
        degraded=not result.bandit_available,
    )

    # Attach structured output
    try:
        from tapps_mcp.common.output_schemas import (
            SecurityFindingOutput,
            SecurityScanOutput,
        )

        findings: list[SecurityFindingOutput] = []
        for i in result.bandit_issues[:_SECURITY_SCAN_FINDING_LIMIT]:
            findings.append(
                SecurityFindingOutput(
                    code=i.code,
                    message=i.message,
                    file=i.file,
                    line=i.line,
                    severity=i.severity,
                    confidence=i.confidence,
                )
            )
        for f in result.secret_findings[:_SECURITY_SCAN_FINDING_LIMIT]:
            findings.append(
                SecurityFindingOutput(
                    code=f.secret_type,
                    message=f.context or f.secret_type,
                    file=f.file_path,
                    line=f.line_number,
                    severity=f.severity,
                    confidence="medium",
                )
            )
        structured = SecurityScanOutput(
            file_path=str(resolved),
            passed=result.passed,
            total_issues=result.total_issues,
            critical_count=result.critical_count,
            high_count=result.high_count,
            medium_count=result.medium_count,
            low_count=result.low_count,
            bandit_available=result.bandit_available,
            findings=findings,
        )
        resp["structuredContent"] = structured.to_structured_content()
    except Exception:
        logger.warning("structured_output_failed", tool="tapps_security_scan", exc_info=True)

    return _with_nudges("tapps_security_scan", resp)


def _sanitize_lookup_param(value: str, max_len: int = 100) -> str:
    """Strip control characters and truncate lookup parameters."""
    import re as _re

    cleaned = _re.sub(r"[\x00-\x1f\x7f]", "", value).strip()
    return cleaned[:max_len]


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

    # Validate mode parameter
    if mode not in _VALID_LOOKUP_MODES:
        return error_response(
            "tapps_lookup_docs",
            "invalid_mode",
            f"Invalid mode '{mode}'. Must be one of: {', '.join(sorted(_VALID_LOOKUP_MODES))}",
        )

    # Sanitize inputs
    library = _sanitize_lookup_param(library)
    topic = _sanitize_lookup_param(topic)

    if not library:
        return error_response("tapps_lookup_docs", "invalid_library", "Library name is required.")

    from tapps_mcp.server_helpers import _get_lookup_engine

    engine = _get_lookup_engine()

    try:
        result = await engine.lookup(library, topic, mode=mode)
    except Exception:
        logger.warning("lookup_engine_error", library=library, topic=topic, exc_info=True)
        return error_response(
            "tapps_lookup_docs",
            "lookup_failed",
            f"Documentation lookup failed for '{library}' / '{topic}'.",
        )

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

    response = success_response("tapps_lookup_docs", elapsed_ms, data)
    response["success"] = result.success
    if result.error:
        err_code = "api_key_missing" if "API key" in result.error else "lookup_failed"
        response["error"] = {"code": err_code, "message": result.error}
        # Expert fallback when Context7 and cache fail — provide RAG-backed guidance
        try:
            from tapps_mcp.experts.engine import consult_expert

            cr = await asyncio.to_thread(
                consult_expert,
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
            logger.warning(
                "expert_fallback_failed", library=library, topic=topic, exc_info=True
            )
    if result.warning:
        response["warning"] = result.warning

    _record_execution(
        "tapps_lookup_docs",
        start,
        status="success" if result.success else "failed",
        error_code="api_key_missing" if (result.error and "API key" in result.error) else None,
    )

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

    # Validate config_type against allowlist
    explicit_type = None if config_type == "auto" else config_type
    if explicit_type is not None and explicit_type not in _VALID_CONFIG_TYPES:
        return error_response(
            "tapps_validate_config",
            "invalid_config_type",
            f"Invalid config_type '{explicit_type}'. "
            f"Must be 'auto' or one of: {', '.join(sorted(_VALID_CONFIG_TYPES))}",
        )

    # Enforce file size limit
    try:
        file_size = resolved.stat().st_size
    except OSError as exc:
        return error_response("tapps_validate_config", "file_error", str(exc))
    if file_size > _MAX_CONFIG_FILE_SIZE:
        return error_response(
            "tapps_validate_config",
            "file_too_large",
            f"Config file is {file_size:,} bytes, "
            f"exceeding the {_MAX_CONFIG_FILE_SIZE:,} byte limit.",
        )

    try:
        content = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return error_response(
            "tapps_validate_config",
            "decode_error",
            f"Cannot decode file as UTF-8: {exc}",
        )

    from tapps_mcp.validators.base import validate_config

    result = validate_config(str(resolved), content, config_type=explicit_type)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_validate_config", start, file_path=str(resolved))

    finding_count = len(result.findings)
    critical_count = sum(1 for f in result.findings if f.severity == "critical")
    warning_count = sum(1 for f in result.findings if f.severity == "warning")

    resp = success_response(
        "tapps_validate_config",
        elapsed_ms,
        {
            "file_path": result.file_path,
            "config_type": result.config_type,
            "valid": result.valid,
            "findings": [f.model_dump() for f in result.findings],
            "suggestions": result.suggestions,
            "finding_count": finding_count,
            "critical_count": critical_count,
            "warning_count": warning_count,
        },
    )

    # Attach structured output
    try:
        from tapps_mcp.common.output_schemas import (
            ConfigFindingOutput,
            ValidateConfigOutput,
        )

        config_findings = [
            ConfigFindingOutput(
                severity=f.severity,
                message=f.message,
                line=f.line,
                category=f.category,
            )
            for f in result.findings
        ]
        structured = ValidateConfigOutput(
            file_path=result.file_path,
            config_type=result.config_type,
            valid=result.valid,
            finding_count=finding_count,
            critical_count=critical_count,
            warning_count=warning_count,
            findings=config_findings,
            suggestions=result.suggestions,
        )
        resp["structuredContent"] = structured.to_structured_content()
    except Exception:
        logger.warning("structured_output_failed", tool="tapps_validate_config", exc_info=True)

    return _with_nudges("tapps_validate_config", resp)


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY)
def tapps_consult_expert(question: str, domain: str = "") -> dict[str, Any]:
    """REQUIRED for domain-specific decisions. Routes to one of 16 built-in
    experts and returns RAG-backed guidance with confidence scores.

    Available domains (omit domain to auto-detect from question):
      security, performance-optimization, testing-strategies,
      code-quality-analysis, software-architecture, development-workflow,
      data-privacy-compliance, accessibility, user-experience,
      documentation-knowledge-management, ai-frameworks, agent-learning,
      observability-monitoring, api-design-integration, cloud-infrastructure,
      database-data-management

    For combined expert + docs in one call, use tapps_research instead.

    Args:
        question: The technical question to ask (natural language).
        domain: Optional domain from the list above. Omit to auto-detect from question.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_consult_expert")

    # Validate inputs
    question = _sanitize_lookup_param(question, max_len=2000)
    if not question:
        return error_response(
            "tapps_consult_expert", "invalid_question", "Question is required."
        )

    from tapps_mcp.experts.engine import consult_expert

    try:
        result = consult_expert(question=question, domain=domain or None)
    except Exception:
        logger.warning("consult_expert_error", question=question[:80], exc_info=True)
        return error_response(
            "tapps_consult_expert",
            "consultation_failed",
            "Expert consultation failed. Try a different question or domain.",
        )

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
            "detected_domains": [
                {"domain": d.domain, "confidence": d.confidence}
                for d in result.detected_domains
            ],
            "recommendation": result.recommendation,
            "low_confidence_nudge": result.low_confidence_nudge,
            "suggested_tool": result.suggested_tool,
            "suggested_library": result.suggested_library,
            "suggested_topic": result.suggested_topic,
            "fallback_used": result.fallback_used,
            "fallback_library": result.fallback_library,
            "fallback_topic": result.fallback_topic,
        },
    )

    # Attach structured output
    try:
        from tapps_mcp.common.output_schemas import ExpertOutput

        structured = ExpertOutput(
            domain=result.domain,
            expert_name=result.expert_name,
            answer=result.answer,
            confidence=round(result.confidence, 4),
            sources=result.sources,
        )
        resp["structuredContent"] = structured.to_structured_content()
    except Exception:
        logger.debug("structured_output_failed: tapps_consult_expert", exc_info=True)

    return _with_nudges(
        "tapps_consult_expert",
        resp,
        context={"confidence": round(result.confidence, 4)},
    )


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY)
def tapps_list_experts() -> dict[str, Any]:
    """Returns the 16 built-in experts with domain, description, and knowledge-base status.

    Not required before calling tapps_consult_expert - that tool's description
    lists all domains and auto-detects from the question when domain is omitted.
    Use this only when you need expert metadata (knowledge file counts, RAG status).
    """
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
async def tapps_checklist(
    task_type: str = "review",
    auto_run: bool = False,
) -> dict[str, Any]:
    """REQUIRED as the FINAL step before declaring work complete.

    Args:
        task_type: "feature" | "bugfix" | "refactor" | "security" | "review".
        auto_run: When True, automatically run missing required validations
            (via tapps_validate_changed) and re-evaluate the checklist.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_checklist")

    try:
        from tapps_mcp.tools.checklist import CallTracker

        result = CallTracker.evaluate(task_type)

        auto_run_results: dict[str, Any] = {}

        if auto_run and result.missing_required:
            missing = set(result.missing_required)

            # validate_changed covers score_file + quality_gate + security_scan
            needs_validate = missing & {
                "tapps_score_file",
                "tapps_quality_gate",
                "tapps_security_scan",
                "tapps_validate_changed",
                "tapps_quick_check",
            }

            if needs_validate:
                try:
                    from tapps_mcp.server_pipeline_tools import tapps_validate_changed

                    settings = load_settings()
                    vc_result = await tapps_validate_changed(
                        preset=settings.quality_preset,
                    )
                    vc_data = vc_result.get("data", {})
                    auto_run_results["validate_changed"] = {
                        "success": vc_result.get("success", False),
                        "files_validated": vc_data.get("files_validated", 0),
                        "all_gates_passed": vc_data.get("all_gates_passed", False),
                    }
                except Exception as exc:
                    auto_run_results["validate_changed"] = {
                        "success": False,
                        "error": str(exc),
                    }

            # Re-evaluate after auto-running
            result = CallTracker.evaluate(task_type)

        elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
        _record_execution("tapps_checklist", start)
        resp_data = result.model_dump()
        if auto_run_results:
            resp_data["auto_run_results"] = auto_run_results
        resp = success_response("tapps_checklist", elapsed_ms, resp_data)

        # Attach structured output
        try:
            from tapps_mcp.common.output_schemas import ChecklistOutput

            structured = ChecklistOutput(
                task_type=result.task_type,
                complete=result.complete,
                called=result.called,
                missing_required=result.missing_required,
                missing_recommended=result.missing_recommended,
                total_calls=result.total_calls,
                auto_run_results=auto_run_results or None,
            )
            resp["structuredContent"] = structured.to_structured_content()
        except Exception:
            logger.debug("structured_output_failed: tapps_checklist", exc_info=True)

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

    # Attach structured output
    try:
        from tapps_mcp.common.output_schemas import ProfileOutput

        structured = ProfileOutput(
            project_root=str(root),
            project_type=profile.project_type,
            project_type_confidence=round(profile.project_type_confidence, 2),
            has_ci=profile.has_ci,
            has_docker=profile.has_docker,
            has_tests=profile.has_tests,
            test_frameworks=profile.test_frameworks,
            package_managers=profile.package_managers,
            quality_recommendations=profile.quality_recommendations,
        )
        resp["structuredContent"] = structured.to_structured_content()
    except Exception:
        logger.debug("structured_output_failed: tapps_project_profile", exc_info=True)

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

    # Attach structured output
    try:
        from tapps_mcp.common.output_schemas import ImpactOutput

        structured = ImpactOutput(
            changed_file=report.changed_file,
            change_type=report.change_type,
            severity=report.severity,
            total_affected=report.total_affected,
            direct_dependents=[d.file_path for d in report.direct_dependents],
            test_files=[t.file_path for t in report.test_files],
            recommendations=report.recommendations,
        )
        resp["structuredContent"] = structured.to_structured_content()
    except Exception:
        logger.debug("structured_output_failed: tapps_impact_analysis", exc_info=True)

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
    from tapps_mcp.server_helpers import _get_scorer

    settings = load_settings()
    scorer = _get_scorer()
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


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY)
async def tapps_dead_code(
    file_path: str = "",
    min_confidence: int = 80,
    scope: str = "file",
) -> dict[str, Any]:
    """Scan a Python file for dead code (unused functions, classes, imports, variables).

    Args:
        file_path: Path to the Python file to scan (required when scope="file").
        min_confidence: Minimum confidence threshold (0-100, default 80).
        scope: Scan scope - "file" (single file), "project" (all .py files),
            or "changed" (git-changed .py files only).
    """
    from tapps_mcp.server_helpers import ensure_session_initialized
    from tapps_mcp.tools.vulture import (
        clamp_confidence,
        collect_changed_python_files,
        collect_python_files,
        is_vulture_available,
        run_vulture_async,
        run_vulture_multi_async,
    )

    start = time.perf_counter_ns()
    _record_call("tapps_dead_code")
    await ensure_session_initialized()

    min_confidence = clamp_confidence(min_confidence)

    valid_scopes = {"file", "project", "changed"}
    if scope not in valid_scopes:
        return error_response(
            "tapps_dead_code",
            "invalid_scope",
            f"Invalid scope '{scope}'. Must be one of: {', '.join(sorted(valid_scopes))}",
        )

    settings = load_settings()

    if scope == "file":
        # Original single-file behavior
        if not file_path:
            return error_response(
                "tapps_dead_code", "missing_file_path",
                "file_path is required when scope='file'",
            )
        try:
            resolved = _validate_file_path(file_path)
        except (ValueError, FileNotFoundError) as exc:
            return error_response("tapps_dead_code", "path_denied", str(exc))

        degraded = not is_vulture_available()
        findings = await run_vulture_async(
            str(resolved),
            min_confidence=min_confidence,
            whitelist_patterns=settings.dead_code_whitelist_patterns,
            cwd=str(resolved.parent),
        )
        files_scanned = 1
        display_path = str(resolved)
    else:
        # Project-wide or changed-file scope
        project_root = settings.project_root
        if scope == "project":
            file_list = collect_python_files(project_root)
        else:
            file_list = collect_changed_python_files(project_root)

        if not file_list:
            elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
            _record_execution("tapps_dead_code", start)
            resp = success_response(
                "tapps_dead_code",
                elapsed_ms,
                {
                    "file_path": "",
                    "scope": scope,
                    "total_findings": 0,
                    "files_scanned": 0,
                    "degraded": not is_vulture_available(),
                    "min_confidence": min_confidence,
                    "by_type": {},
                    "type_counts": {},
                    "summary": f"No Python files found for scope '{scope}'",
                },
            )
            return _with_nudges("tapps_dead_code", resp)

        result = await run_vulture_multi_async(
            file_list,
            min_confidence=min_confidence,
            whitelist_patterns=settings.dead_code_whitelist_patterns,
            cwd=str(project_root),
            timeout=120,
        )
        findings = result.findings
        files_scanned = result.files_scanned
        degraded = result.degraded
        display_path = str(project_root)

    # Group by type
    by_type: dict[str, list[dict[str, Any]]] = {}
    for f in findings:
        entry: dict[str, Any] = {
            "name": f.name,
            "line": f.line,
            "confidence": f.confidence,
            "message": f.message,
        }
        if scope != "file":
            entry["file_path"] = f.file_path
        by_type.setdefault(f.finding_type, []).append(entry)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_dead_code", start, file_path=display_path)

    type_counts = {k: len(v) for k, v in by_type.items()}
    summary = f"Found {len(findings)} dead code items in {files_scanned} file(s)"
    if type_counts:
        parts = [f"{count} {typ}" for typ, count in sorted(type_counts.items())]
        summary += f" ({', '.join(parts)})"

    resp = success_response(
        "tapps_dead_code",
        elapsed_ms,
        {
            "file_path": display_path,
            "scope": scope,
            "total_findings": len(findings),
            "files_scanned": files_scanned,
            "degraded": degraded,
            "min_confidence": min_confidence,
            "by_type": by_type,
            "type_counts": type_counts,
            "summary": summary,
        },
    )
    return _with_nudges("tapps_dead_code", resp)


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY_OPEN)
async def tapps_dependency_scan(project_root: str = "") -> dict[str, Any]:
    """Scan project dependencies for known vulnerabilities using pip-audit.

    Args:
        project_root: Project root path (default: server's configured root).
    """
    from tapps_mcp.server_helpers import ensure_session_initialized

    start = time.perf_counter_ns()
    _record_call("tapps_dependency_scan")
    await ensure_session_initialized()

    settings = load_settings()

    if not settings.dependency_scan_enabled:
        elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
        _record_execution("tapps_dependency_scan", start)
        resp = success_response(
            "tapps_dependency_scan",
            elapsed_ms,
            {
                "scanned_packages": 0,
                "vulnerable_packages": 0,
                "total_findings": 0,
                "scan_source": "disabled",
                "by_severity": {},
                "severity_counts": {},
                "summary": "Dependency scanning is disabled (dependency_scan_enabled=False).",
            },
        )
        return _with_nudges("tapps_dependency_scan", resp)

    from tapps_mcp.tools.pip_audit import run_pip_audit_async

    root = project_root if project_root else str(settings.project_root)

    result = await run_pip_audit_async(
        project_root=root,
        source=settings.dependency_scan_source,
        severity_threshold=settings.dependency_scan_severity_threshold,
        ignore_ids=settings.dependency_scan_ignore_ids or None,
    )

    # Populate session cache so scorer.py applies dependency penalties
    if not result.error:
        from tapps_mcp.tools.dependency_scan_cache import set_dependency_findings

        set_dependency_findings(root, result.findings)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_dependency_scan", start)

    # Group by severity
    by_severity: dict[str, list[dict[str, str]]] = {}
    for f in result.findings:
        by_severity.setdefault(f.severity, []).append(
            {
                "package": f.package,
                "installed_version": f.installed_version,
                "fixed_version": f.fixed_version,
                "vulnerability_id": f.vulnerability_id,
                "description": f.description[:200] if f.description else "",
            }
        )

    sev_counts = {k: len(v) for k, v in by_severity.items()}
    summary = f"Scanned {result.scanned_packages} packages: {len(result.findings)} vulnerabilities"
    if sev_counts:
        parts = [f"{count} {sev}" for sev, count in sorted(sev_counts.items())]
        summary += f" ({', '.join(parts)})"

    data: dict[str, Any] = {
        "scanned_packages": result.scanned_packages,
        "vulnerable_packages": result.vulnerable_packages,
        "total_findings": len(result.findings),
        "scan_source": result.scan_source,
        "by_severity": by_severity,
        "severity_counts": sev_counts,
        "summary": summary,
    }
    if result.error:
        data["error"] = result.error

    resp = success_response("tapps_dependency_scan", elapsed_ms, data)
    return _with_nudges("tapps_dependency_scan", resp)


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY)
async def tapps_dependency_graph(
    project_root: str = "",
    detect_cycles: bool = True,
    include_coupling: bool = True,
) -> dict[str, Any]:
    """Analyze import dependencies: detect circular imports and measure coupling.

    Args:
        project_root: Project root path (default: server's configured root).
        detect_cycles: Whether to detect circular dependency cycles.
        include_coupling: Whether to calculate coupling metrics.
    """
    from tapps_mcp.server_helpers import ensure_session_initialized

    start = time.perf_counter_ns()
    _record_call("tapps_dependency_graph")
    await ensure_session_initialized()

    settings = load_settings()
    root = settings.project_root
    if project_root:
        from pathlib import Path

        root = Path(project_root).resolve()

    def _build_graph_sync() -> dict[str, Any]:
        """Run graph building, cycle detection, and coupling analysis synchronously."""
        from tapps_mcp.project.import_graph import build_import_graph

        graph = build_import_graph(root)
        result: dict[str, Any] = {
            "project_root": str(root),
            "total_modules": len(graph.modules),
            "total_edges": len(graph.edges),
        }

        if detect_cycles:
            from tapps_mcp.project.cycle_detector import (
                detect_cycles as _detect,
            )
            from tapps_mcp.project.cycle_detector import (
                suggest_cycle_fixes,
            )

            analysis = _detect(graph)
            result["cycles"] = {
                "total": len(analysis.cycles),
                "runtime_cycles": analysis.runtime_cycles,
                "type_checking_cycles": analysis.type_checking_cycles,
                "details": [
                    {
                        "modules": c.modules,
                        "length": c.length,
                        "severity": c.severity,
                        "description": c.description,
                    }
                    for c in analysis.cycles[:10]
                ],
            }
            result["cycle_suggestions"] = suggest_cycle_fixes(analysis.cycles[:5])

        if include_coupling:
            from tapps_mcp.project.coupling_metrics import (
                calculate_coupling,
                suggest_coupling_fixes,
            )

            couplings = calculate_coupling(graph)
            hubs = [c for c in couplings if c.is_hub]
            result["coupling"] = {
                "total_modules_analysed": len(couplings),
                "hub_count": len(hubs),
                "top_coupled": [
                    {
                        "module": c.module,
                        "afferent": c.afferent,
                        "efferent": c.efferent,
                        "instability": round(c.instability, 3),
                        "is_hub": c.is_hub,
                    }
                    for c in couplings[:10]
                ],
            }
            result["coupling_suggestions"] = suggest_coupling_fixes(couplings[:5])

        # Attach external imports for cross-tool integration
        result["_external_imports"] = {
            pkg: list(mods) for pkg, mods in graph.external_imports.items()
        }
        return result

    data = await asyncio.to_thread(_build_graph_sync)

    # Cross-reference with cached vulnerability findings when available
    external_imports = data.pop("_external_imports", {})
    if external_imports:
        from tapps_mcp.tools.dependency_scan_cache import get_dependency_findings

        dep_findings = get_dependency_findings(str(root))
        if dep_findings:
            from tapps_mcp.project.vulnerability_impact import analyze_vulnerability_impact

            impact = analyze_vulnerability_impact(dep_findings, external_imports)
            if impact.impacts:
                data["vulnerability_impact"] = {
                    "total_vulnerable_imports": impact.total_vulnerable_imports,
                    "most_exposed_modules": impact.most_exposed_modules[:10],
                    "impacts": [
                        {
                            "package": vi.package,
                            "vulnerability_id": vi.vulnerability_id,
                            "severity": vi.severity,
                            "importing_modules": vi.importing_modules[:10],
                            "import_count": vi.import_count,
                        }
                        for vi in impact.impacts[:10]
                    ],
                }

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_dependency_graph", start)

    resp = success_response("tapps_dependency_graph", elapsed_ms, data)
    return _with_nudges("tapps_dependency_graph", resp)


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
def tapps_workflow(
    task_type: str = "general",
    engagement_level: str | None = None,
) -> str:
    """Generate the TappsMCP workflow prompt for a specific task type.

    Args:
        task_type: One of: general, feature, bugfix, refactor, security, review.
        engagement_level: When set (high/medium/low), varies framing. When None,
            uses load_settings().llm_engagement_level.
    """
    from tapps_mcp.config.settings import load_settings

    level = engagement_level or load_settings().llm_engagement_level
    if level not in ("high", "medium", "low"):
        level = "medium"

    workflows = {
        "general": (
            "TappsMCP Workflow - General\n\n"
            "1. tapps_session_start\n2. tapps_project_profile (when project context needed)\n"
            "3. tapps_score_file(quick=True)\n4. tapps_score_file\n"
            "5. tapps_quality_gate\n6. tapps_checklist(task_type='review')"
        ),
        "feature": (
            "TappsMCP Workflow - New Feature\n\n"
            "1. tapps_session_start\n2. tapps_project_profile (when project context needed)\n"
            "3. tapps_lookup_docs\n4. tapps_consult_expert\n"
            "5. tapps_score_file(quick=True)\n6. tapps_score_file\n"
            "7. tapps_security_scan\n8. tapps_quality_gate\n"
            "9. tapps_checklist(task_type='feature')"
        ),
        "bugfix": (
            "TappsMCP Workflow - Bug Fix\n\n"
            "1. tapps_session_start\n2. tapps_impact_analysis\n"
            "3. tapps_score_file(quick=True)\n4. tapps_score_file\n"
            "5. tapps_quality_gate\n6. tapps_checklist(task_type='bugfix')"
        ),
        "refactor": (
            "TappsMCP Workflow - Refactoring\n\n"
            "1. tapps_session_start\n2. tapps_impact_analysis\n"
            "3. tapps_consult_expert(domain='software-architecture')\n"
            "4. tapps_score_file(quick=True)\n5. tapps_score_file\n"
            "6. tapps_quality_gate\n7. tapps_checklist(task_type='refactor')"
        ),
        "security": (
            "TappsMCP Workflow - Security Review\n\n"
            "1. tapps_session_start\n2. tapps_security_scan\n"
            "3. tapps_consult_expert(domain='security')\n"
            "4. tapps_score_file\n5. tapps_quality_gate(preset='strict')\n"
            "6. tapps_checklist(task_type='security')"
        ),
        "review": (
            "TappsMCP Workflow - Code Review\n\n"
            "1. tapps_session_start\n2. tapps_score_file\n"
            "3. tapps_security_scan\n4. tapps_quality_gate\n"
            "5. tapps_checklist(task_type='review')"
        ),
    }
    body = workflows.get(task_type, workflows["general"])
    if level == "high":
        return "You MUST call these tools in order.\n\n" + body
    if level == "low":
        return "Optional workflow — consider these tools when useful.\n\n" + body
    return "Recommended tool call order:\n\n" + body


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

# ---------------------------------------------------------------------------
# outputSchema wiring (Epic 13) — DISABLED in v0.4.1
# ---------------------------------------------------------------------------
# The MCP SDK validates the tool's full return dict against the declared
# outputSchema.  Our handlers return an envelope dict (tool, success,
# elapsed_ms, data) which does not match the inner-content schemas
# (SessionStartOutput, ProfileOutput, etc.), causing validation errors like
# "Output validation error: 'server_version' is a required property".
#
# Schema wiring is disabled until handlers are migrated to return
# CallToolResult with proper structuredContent.  The schema model classes
# are still used to build the "structuredContent" key inside the JSON text.

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

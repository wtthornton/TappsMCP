"""TappsMCP MCP server entry point.

Creates the FastMCP server instance, registers all tools, and provides
``run_server()`` for the CLI.

Tool handlers are split across modules for maintainability:
  - ``server_scoring_tools``: tapps_score_file, tapps_quality_gate, tapps_quick_check
  - ``server_pipeline_tools``: tapps_validate_changed, tapps_session_start, tapps_init
  - ``server_metrics_tools``: tapps_dashboard, tapps_stats, tapps_feedback, tapps_research
  - ``server_memory_tools``: tapps_memory
  - ``server_expert_tools``: tapps_manage_experts
  - ``server_analysis_tools``: tapps_session_notes, tapps_impact_analysis, tapps_report,
    tapps_dead_code, tapps_dependency_scan, tapps_dependency_graph
  - ``server_resources``: MCP resources and prompts
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tapps_core.common.models import InstalledTool, StartupDiagnostics
    from tapps_core.config.settings import TappsMCPSettings
    from tapps_core.knowledge.models import LookupResult
    from tapps_core.metrics.collector import MetricsHub
    from tapps_mcp.tools.checklist import ChecklistResult

import structlog
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from tapps_core.common.logging import setup_logging
from tapps_core.config.settings import load_settings
from tapps_mcp import __version__
from tapps_mcp.common.developer_workflow import (
    DAILY_STEPS,
    RECOMMENDED_WORKFLOW_TEXT,
)
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


def _bootstrap_cache_dir(project_root: Path) -> tuple[Path, bool]:
    """Create cache directory, returning ``(cache_dir, fallback_used)``.

    Priority:
    1. ``TAPPS_CACHE_DIR`` env var (if set)
    2. ``<project_root>/.tapps-mcp-cache``
    3. ``<tempdir>/.tapps-mcp-cache`` (fallback when project root not writable)
    """
    cache_dir = Path(os.environ["TAPPS_CACHE_DIR"]) if os.environ.get("TAPPS_CACHE_DIR") else (
        project_root / ".tapps-mcp-cache"
    )
    fallback_used = False

    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError):
        # Fall back to temp directory if primary path not writable
        cache_dir = Path(tempfile.gettempdir()) / ".tapps-mcp-cache"
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            fallback_used = True
        except (PermissionError, OSError):
            logger.debug("cache_dir_creation_failed", cache_dir=str(cache_dir))

    return cache_dir, fallback_used


def _cache_info_dict(cache_dir: Path, fallback_used: bool) -> dict[str, object]:
    """Build the ``cache`` sub-dict for server info responses."""
    return {
        "dir": str(cache_dir),
        "exists": cache_dir.is_dir(),
        "writable": os.access(str(cache_dir), os.W_OK) if cache_dir.is_dir() else False,
        "fallback_used": fallback_used,
    }


def _normalize_path_for_mapping(path: str) -> str:
    """Normalize a path string for host-root prefix comparison (cross-platform)."""
    s = path.strip().replace("\\", "/")
    if s and s[1:2] == ":" and len(s) >= _MIN_DRIVE_PATH_LEN:
        s = s[0].lower() + s[1:]
    return s.rstrip("/") or "/"


def _validate_file_path(file_path: str) -> Path:
    """Validate *file_path* against the project root boundary."""
    from tapps_core.security.path_validator import PathValidator

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
    "api-design-integration": (
        "fastapi", "flask", "django", "starlette", "httpx", "requests",
    ),
    "database-data-management": ("sqlalchemy", "alembic", "psycopg", "redis"),
    "cloud-infrastructure": ("docker", "kubernetes", "docker-compose"),
    "development-workflow": ("github-actions", "ci"),
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
    "mcp",
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
    settings: TappsMCPSettings,
    installed: list[InstalledTool],
    diagnostics: StartupDiagnostics,
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
        "recommended_workflow": RECOMMENDED_WORKFLOW_TEXT,
        "quick_start": list(DAILY_STEPS),
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


_checklist_state: dict[str, bool] = {"persist_configured": False}


def _record_call(tool_name: str) -> None:
    """Record a tool call in the session checklist tracker."""
    try:
        from tapps_mcp.tools.checklist import CallTracker

        if not _checklist_state["persist_configured"]:
            settings = load_settings()
            sessions_dir = settings.project_root / ".tapps-mcp" / "sessions"
            persist_path = sessions_dir / "checklist_calls.jsonl"
            CallTracker.set_persist_path(persist_path)
            _checklist_state["persist_configured"] = True
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
    from tapps_core.metrics.collector import get_metrics_hub

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
async def tapps_server_info() -> dict[str, Any]:
    """Discovers server version, available tools, installed checkers (ruff, mypy,
    bandit, radon), and configuration. Side effects: none (read-only).

    Prefer tapps_session_start as the FIRST call—it returns the same info plus
    memory status, auto-GC, and session capture. Use tapps_server_info only when
    you need lightweight discovery without session initialization.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_server_info")

    settings = load_settings()

    from tapps_mcp.diagnostics import collect_diagnostics

    # Story 75.3: Auto-create cache directory for faster subsequent starts
    cache_dir, cache_fallback = _bootstrap_cache_dir(settings.project_root)

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
    data["cache"] = _cache_info_dict(cache_dir, cache_fallback)
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

    # Story 75.3: Auto-create cache directory for faster subsequent starts
    cache_dir, cache_fallback = _bootstrap_cache_dir(settings.project_root)

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
    data["cache"] = _cache_info_dict(cache_dir, cache_fallback)
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


def _lookup_error_code(error: str | None) -> str | None:
    """Derive the error code from a lookup error message, or None if no error."""
    if not error:
        return None
    return "api_key_missing" if "API key" in error else "lookup_failed"


def _build_lookup_data(result: LookupResult) -> dict[str, Any]:
    """Build the data dict from a LookupResult, including optional fields."""
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
    return data


async def _attach_expert_fallback(
    response: dict[str, Any],
    library: str,
    topic: str,
) -> None:
    """Attach expert fallback to a lookup response when the primary lookup failed."""
    try:
        from tapps_core.experts.engine import consult_expert

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

    data = _build_lookup_data(result)
    response = success_response("tapps_lookup_docs", elapsed_ms, data)
    response["success"] = result.success
    err_code = _lookup_error_code(result.error)
    if result.error:
        response["error"] = {"code": err_code, "message": result.error}
        await _attach_expert_fallback(response, library, topic)
    if result.warning:
        response["warning"] = result.warning

    _record_execution(
        "tapps_lookup_docs",
        start,
        status="success" if result.success else "failed",
        error_code=err_code,
    )

    return _with_nudges("tapps_lookup_docs", response)


# ---------------------------------------------------------------------------
# tapps_validate_config helpers
# ---------------------------------------------------------------------------


def _resolve_config_type(config_type: str) -> str | None | dict[str, Any]:
    """Resolve config_type. Returns None for 'auto', the type string, or error_response."""
    if config_type == "auto":
        return None
    if config_type not in _VALID_CONFIG_TYPES:
        return error_response(
            "tapps_validate_config",
            "invalid_config_type",
            f"Invalid config_type '{config_type}'. "
            f"Must be 'auto' or one of: {', '.join(sorted(_VALID_CONFIG_TYPES))}",
        )
    return config_type


def _read_config_content(resolved: Path) -> str | dict[str, Any]:
    """Read config file with size and encoding validation.

    Returns file content string on success, or error_response dict on failure.
    """
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
        return resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return error_response(
            "tapps_validate_config",
            "decode_error",
            f"Cannot decode file as UTF-8: {exc}",
        )


def _build_config_response_data(result: Any) -> dict[str, Any]:
    """Build the response data dict from a validation result."""
    finding_count = len(result.findings)
    critical_count = sum(1 for f in result.findings if f.severity == "critical")
    warning_count = sum(1 for f in result.findings if f.severity == "warning")
    return {
        "file_path": result.file_path,
        "config_type": result.config_type,
        "valid": result.valid,
        "findings": [f.model_dump() for f in result.findings],
        "suggestions": result.suggestions,
        "finding_count": finding_count,
        "critical_count": critical_count,
        "warning_count": warning_count,
    }


def _attach_config_structured_output(resp: dict[str, Any], result: Any) -> None:
    """Attach structured output to config validation response in-place."""
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
        data = resp.get("data", {})
        structured = ValidateConfigOutput(
            file_path=result.file_path,
            config_type=result.config_type,
            valid=result.valid,
            finding_count=data.get("finding_count", len(result.findings)),
            critical_count=data.get("critical_count", 0),
            warning_count=data.get("warning_count", 0),
            findings=config_findings,
            suggestions=result.suggestions,
        )
        resp["structuredContent"] = structured.to_structured_content()
    except Exception:
        logger.warning("structured_output_failed", tool="tapps_validate_config", exc_info=True)


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

    explicit_type = _resolve_config_type(config_type)
    if isinstance(explicit_type, dict):
        return explicit_type  # error_response

    content_or_err = _read_config_content(resolved)
    if isinstance(content_or_err, dict):
        return content_or_err  # error_response

    from tapps_mcp.validators.base import validate_config

    result = validate_config(str(resolved), content_or_err, config_type=explicit_type)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_validate_config", start, file_path=str(resolved))

    resp = success_response(
        "tapps_validate_config",
        elapsed_ms,
        _build_config_response_data(result),
    )

    _attach_config_structured_output(resp, result)

    return _with_nudges("tapps_validate_config", resp)


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY)
def tapps_consult_expert(question: str, domain: str = "") -> dict[str, Any]:
    """REQUIRED for domain-specific decisions. Routes to one of 17+ built-in
    experts or user-defined business experts and returns RAG-backed guidance
    with confidence scores.

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

    from tapps_core.experts.engine import consult_expert

    try:
        result = consult_expert(question=question, domain=domain or None)
    except Exception:
        logger.warning("consult_expert_error", question=question[:80], exc_info=True)
        return error_response(
            "tapps_consult_expert",
            "consultation_failed",
            "Expert consultation failed. Try a different question or domain.",
        )

    # Memory injection (Epic 25)
    answer = result.answer
    memory_injected = 0
    try:
        from tapps_core.memory.injection import append_memory_to_answer, inject_memories
        from tapps_mcp.server_helpers import _get_memory_store

        settings = load_settings()
        store = _get_memory_store()
        mem_result = inject_memories(
            question, store, settings.llm_engagement_level
        )
        answer = append_memory_to_answer(answer, mem_result)
        memory_injected = mem_result.get("memory_injected", 0)
    except Exception:
        logger.debug("memory_injection_failed: tapps_consult_expert", exc_info=True)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_consult_expert", start)

    # Determine expert type from registry
    from tapps_core.experts.registry import ExpertRegistry

    _is_builtin = ExpertRegistry.is_technical_domain(result.domain)
    _expert_type = "builtin" if _is_builtin else "business"

    resp = success_response(
        "tapps_consult_expert",
        elapsed_ms,
        {
            "domain": result.domain,
            "expert_id": result.expert_id,
            "expert_name": result.expert_name,
            "answer": answer,
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
            "stale_knowledge": result.stale_knowledge,
            "oldest_chunk_age_days": result.oldest_chunk_age_days,
            "freshness_caveat": result.freshness_caveat,
            "memory_injected": memory_injected,
            "is_builtin": _is_builtin,
            "expert_type": _expert_type,
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
        context={
            "confidence": round(result.confidence, 4),
            "stale_knowledge": result.stale_knowledge,
        },
    )


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY)
def tapps_list_experts() -> dict[str, Any]:
    """Returns built-in and business experts with domain, description, and knowledge-base status.

    Not required before calling tapps_consult_expert - that tool's description
    lists all domains and auto-detects from the question when domain is omitted.
    Use this only when you need expert metadata (knowledge file counts, RAG status).
    """
    start = time.perf_counter_ns()
    _record_call("tapps_list_experts")

    from tapps_core.experts.engine import list_experts

    experts = list_experts()

    builtin_count = sum(1 for e in experts if e.is_builtin)
    business_count = sum(1 for e in experts if not e.is_builtin)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_list_experts", start)

    resp = success_response(
        "tapps_list_experts",
        elapsed_ms,
        {
            "expert_count": len(experts),
            "builtin_count": builtin_count,
            "business_count": business_count,
            "experts": [e.model_dump() for e in experts],
        },
    )
    return _with_nudges("tapps_list_experts", resp)


def _checklist_json_format(
    result: ChecklistResult,
    auto_run_results: dict[str, Any],
) -> dict[str, Any]:
    """Build structured JSON output with computed counts for checklist."""
    required_called = [t for t in result.called if t not in result.missing_required]
    recommended_missing = result.missing_recommended
    recommended_called = [
        t for t in result.called if t not in result.missing_recommended
    ]
    optional_missing = result.missing_optional
    optional_called = [t for t in result.called if t not in result.missing_optional]

    data: dict[str, Any] = {
        "task_type": result.task_type,
        "complete": result.complete,
        "total_calls": result.total_calls,
        "required_called": required_called,
        "required_missing": result.missing_required,
        "recommended_called": recommended_called,
        "recommended_missing": recommended_missing,
        "optional_called": optional_called,
        "optional_missing": optional_missing,
        "priority_actions": result.missing_required[:3] if result.missing_required else [],
    }
    if auto_run_results:
        data["auto_run_results"] = auto_run_results
    return data


def _checklist_compact_format(
    result: ChecklistResult,
    auto_run_results: dict[str, Any],
) -> dict[str, Any]:
    """Build a short 1-2 line compact summary for checklist."""
    req_ok = len(result.called) - len(result.missing_required)
    parts = [f"complete={result.complete}"]

    if req_ok > 0:
        parts.append(f"{req_ok} required OK")
    if result.missing_required:
        missing_names = ", ".join(result.missing_required)
        parts.append(f"{len(result.missing_required)} required missing ({missing_names})")
    if result.missing_recommended:
        missing_names = ", ".join(result.missing_recommended)
        parts.append(
            f"{len(result.missing_recommended)} recommended missing ({missing_names})"
        )

    summary = f"Checklist {result.task_type}: {', '.join(parts)}"

    data: dict[str, Any] = {
        "summary": summary,
        "complete": result.complete,
        "task_type": result.task_type,
        "total_calls": result.total_calls,
    }
    if auto_run_results:
        data["auto_run_results"] = auto_run_results
    return data


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY)
async def tapps_checklist(
    task_type: str = "review",
    auto_run: bool = False,
    output_format: str = "markdown",
    commit_sha: str = "",
) -> dict[str, Any]:
    """REQUIRED as the FINAL step before declaring work complete.

    Args:
        task_type: "feature" | "bugfix" | "refactor" | "security" | "review".
        auto_run: When True, automatically run missing required validations
            (via tapps_validate_changed) and re-evaluate the checklist.
        output_format: "markdown" (default, full table), "json" (structured counts),
            or "compact" (short 1-2 line summary).
        commit_sha: Optional git SHA to embed in response. If empty, auto-detects HEAD.
    """
    start = time.perf_counter_ns()
    _record_call("tapps_checklist")

    valid_formats = {"markdown", "json", "compact"}
    if output_format not in valid_formats:
        return error_response(
            "tapps_checklist",
            "invalid_format",
            f"output_format must be one of {sorted(valid_formats)}, got '{output_format}'",
        )

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
                    # Epic 66.2: Add validation_note when 0 files validated
                    if vc_data.get("files_validated", 0) == 0:
                        auto_run_results["validate_changed"]["validation_note"] = (
                            "Validation ran but 0 files validated. "
                            "Consider tapps_quick_check on changed files."
                        )
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

        # Story 75.5: Add git context for audit trail linkage
        try:
            from tapps_mcp.tools.checklist import _get_git_context

            git_context = await _get_git_context(commit_sha=commit_sha)
            resp_data["git_context"] = git_context
        except Exception:
            resp_data["git_context"] = None

        # Format output based on output_format
        if output_format == "json":
            resp_data = _checklist_json_format(result, auto_run_results)
        elif output_format == "compact":
            resp_data = _checklist_compact_format(result, auto_run_results)

        resp = success_response("tapps_checklist", elapsed_ms, resp_data)

        # Epic 66.2: Surface validation_note in next_steps
        if auto_run_results.get("validate_changed", {}).get("validation_note"):
            next_steps = resp_data.get("next_steps", [])
            if not isinstance(next_steps, list):
                next_steps = []
            next_steps.append(
                "tapps_validate_changed ran but validated 0 files. "
                "Use tapps_quick_check on individual changed files as fallback."
            )
            resp_data["next_steps"] = next_steps

        # Attach structured output (markdown/json only - compact is already minimal)
        if output_format != "compact":
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
    """Call when you need project context. Detects tech stack, type, CI, Docker,
    test frameworks, and package managers. Session start does NOT include profile;
    call this on demand when you need project-specific recommendations.

    Returns: project_type, tech_stack, has_ci, has_docker, has_tests, recommendations.

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


# ---------------------------------------------------------------------------
# Register tools from extracted modules & re-export for backward compatibility
# ---------------------------------------------------------------------------


def _register_tool_modules() -> None:
    """Import and register tools from extracted server modules.

    Wrapped in a function to avoid E402 (module-level import not at top).
    The modules register their ``@mcp.tool()`` handlers on the shared ``mcp``
    instance when ``.register(mcp)`` is called.
    """
    from tapps_mcp import (
        server_analysis_tools,
        server_expert_tools,
        server_memory_tools,
        server_metrics_tools,
        server_pipeline_tools,
        server_resources,
        server_scoring_tools,
    )

    server_scoring_tools.register(mcp)
    server_pipeline_tools.register(mcp)
    server_metrics_tools.register(mcp)
    server_memory_tools.register(mcp)
    server_expert_tools.register(mcp)
    server_analysis_tools.register(mcp)
    server_resources.register(mcp)


_register_tool_modules()

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

# Re-export so ``from tapps_mcp.server import tapps_X`` keeps working.
# Modules were imported inside _register_tool_modules(); access via sys.modules.
_scoring = sys.modules["tapps_mcp.server_scoring_tools"]
_pipeline = sys.modules["tapps_mcp.server_pipeline_tools"]
_metrics = sys.modules["tapps_mcp.server_metrics_tools"]
_memory = sys.modules["tapps_mcp.server_memory_tools"]
_experts = sys.modules["tapps_mcp.server_expert_tools"]
_analysis = sys.modules["tapps_mcp.server_analysis_tools"]

tapps_score_file = _scoring.tapps_score_file
tapps_quality_gate = _scoring.tapps_quality_gate
tapps_quick_check = _scoring.tapps_quick_check
tapps_validate_changed = _pipeline.tapps_validate_changed
tapps_session_start = _pipeline.tapps_session_start
tapps_init = _pipeline.tapps_init
tapps_dashboard = _metrics.tapps_dashboard
tapps_stats = _metrics.tapps_stats
tapps_feedback = _metrics.tapps_feedback
tapps_research = _metrics.tapps_research
tapps_memory = _memory.tapps_memory
tapps_manage_experts = _experts.tapps_manage_experts
tapps_session_notes = _analysis.tapps_session_notes
tapps_impact_analysis = _analysis.tapps_impact_analysis
tapps_report = _analysis.tapps_report
tapps_dead_code = _analysis.tapps_dead_code
tapps_dependency_scan = _analysis.tapps_dependency_scan
tapps_dependency_graph = _analysis.tapps_dependency_graph
_promote_note_to_memory = _analysis._promote_note_to_memory


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

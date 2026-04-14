"""TappsMCP MCP server entry point.

Creates the FastMCP server instance, registers all tools, and provides
``run_server()`` for the CLI.

Tool handlers are split across modules for maintainability:
  - ``server_scoring_tools``: tapps_score_file, tapps_quality_gate, tapps_quick_check
  - ``server_pipeline_tools``: tapps_validate_changed, tapps_session_start, tapps_init
  - ``server_metrics_tools``: tapps_dashboard, tapps_stats, tapps_feedback
  - ``server_memory_tools``: tapps_memory
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
from tapps_mcp.server_helpers import (
    error_response,
    serialize_issues,
    success_response,
)
from tapps_mcp.tools.tool_detection import (
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



# ---------------------------------------------------------------------------
# Constants extracted to avoid duplication
# ---------------------------------------------------------------------------

# Canonical list of all TappsMCP tools (26, including 2 deprecated stubs).
# Used for filtering and fallback.
ALL_TOOL_NAMES: frozenset[str] = frozenset({
    "tapps_server_info",
    "tapps_session_start",
    "tapps_score_file",
    "tapps_security_scan",
    "tapps_quality_gate",
    "tapps_lookup_docs",
    "tapps_validate_config",
    "tapps_validate_changed",
    "tapps_quick_check",
    "tapps_checklist",
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
    "tapps_dead_code",
    "tapps_dependency_scan",
    "tapps_dependency_graph",
    "tapps_memory",
    "tapps_consult_expert",
    "tapps_research",
    "tapps_pipeline",
})

# Tier 1 from TOOL-TIER-RANKING (Epic 79.1)
TOOL_PRESET_CORE: frozenset[str] = frozenset({
    "tapps_session_start",
    "tapps_quick_check",
    "tapps_validate_changed",
    "tapps_quality_gate",
    "tapps_checklist",
    "tapps_lookup_docs",
    "tapps_security_scan",
    "tapps_pipeline",
})

# Tier 1 + Tier 2
TOOL_PRESET_PIPELINE: frozenset[str] = TOOL_PRESET_CORE | frozenset({
    "tapps_score_file",
    "tapps_memory",
    "tapps_impact_analysis",
    "tapps_validate_config",
})

# Role presets Phase 1 (Epic 79.5) — from ROLE-PRESETS-IMPLEMENT-FIRST.md
TOOL_PRESET_REVIEWER: frozenset[str] = frozenset({
    "tapps_session_start", "tapps_quick_check", "tapps_validate_changed",
    "tapps_quality_gate", "tapps_checklist", "tapps_security_scan",
    "tapps_score_file", "tapps_dead_code", "tapps_dependency_scan",
})
TOOL_PRESET_PLANNER: frozenset[str] = frozenset({
    "tapps_session_start", "tapps_checklist", "tapps_validate_changed",
    "tapps_quality_gate", "tapps_score_file", "tapps_memory",
})
TOOL_PRESET_FRONTEND: frozenset[str] = frozenset({
    "tapps_session_start", "tapps_quick_check", "tapps_score_file",
    "tapps_lookup_docs", "tapps_quality_gate",
})
TOOL_PRESET_DEVELOPER: frozenset[str] = frozenset({
    "tapps_session_start", "tapps_quick_check", "tapps_validate_changed",
    "tapps_quality_gate", "tapps_checklist", "tapps_score_file",
    "tapps_security_scan", "tapps_lookup_docs", "tapps_memory",
    "tapps_impact_analysis",
})

_FALLBACK_TOOL_LIST: list[str] = sorted(ALL_TOOL_NAMES)

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


def _resolve_allowed_tools(settings: TappsMCPSettings) -> frozenset[str]:
    """Compute the set of tool names to register from config (Epic 79.1).

    Precedence: enabled_tools (if non-empty) > tool_preset > full set; then
    subtract disabled_tools. Invalid names in enabled_tools are ignored and logged.
    """
    allowed: set[str]
    if settings.enabled_tools:
        allowed = set(settings.enabled_tools) & ALL_TOOL_NAMES
        invalid = set(settings.enabled_tools) - ALL_TOOL_NAMES
        if invalid:
            logger.debug(
                "enabled_tools_invalid_ignored",
                invalid=sorted(invalid),
                valid_count=len(allowed),
            )
    elif settings.tool_preset == "core":
        allowed = set(TOOL_PRESET_CORE)
    elif settings.tool_preset == "pipeline":
        allowed = set(TOOL_PRESET_PIPELINE)
    elif settings.tool_preset == "reviewer":
        allowed = set(TOOL_PRESET_REVIEWER)
    elif settings.tool_preset == "planner":
        allowed = set(TOOL_PRESET_PLANNER)
    elif settings.tool_preset == "frontend":
        allowed = set(TOOL_PRESET_FRONTEND)
    elif settings.tool_preset == "developer":
        allowed = set(TOOL_PRESET_DEVELOPER)
    elif settings.tool_preset == "full":
        allowed = set(ALL_TOOL_NAMES)
    else:
        allowed = set(ALL_TOOL_NAMES)
    allowed -= set(settings.disabled_tools)
    return frozenset(allowed)


def _get_available_tools() -> list[str]:
    """Return the list of registered MCP tools, with fallback to a static list."""
    try:
        tool_manager = mcp._tool_manager
        return list(tool_manager._tools.keys())
    except AttributeError:
        logger.warning("mcp_tool_manager_inaccessible", hint="using fallback tool list")
        return list(_FALLBACK_TOOL_LIST)


def _current_docs_provider_summary() -> dict[str, Any]:
    """Return the active docs-lookup provider summary (Issue #79)."""
    has_key = bool(
        os.environ.get("TAPPS_MCP_CONTEXT7_API_KEY")
        or os.environ.get("CONTEXT7_API_KEY")
    )
    summary: dict[str, Any] = {
        "primary": "context7" if has_key else "llmstxt",
        "context7_configured": has_key,
    }
    if not has_key:
        summary["hint"] = (
            "Set TAPPS_MCP_CONTEXT7_API_KEY for richer docs via Context7. "
            "https://context7.com"
        )
    return summary


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
        "checker_environment": "mcp_server",
        "checker_environment_note": (
            "Checker availability reflects the MCP server process environment. "
            "Target project may have different tools installed."
        ),
        "docs_provider": _current_docs_provider_summary(),
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


_checklist_state: dict[str, bool] = {"persist_configured": False}


def _record_call(tool_name: str, *, success: bool = True) -> None:
    """Record a tool call in the session checklist tracker."""
    try:
        from tapps_mcp.tools.checklist import CallTracker

        if not _checklist_state["persist_configured"]:
            settings = load_settings()
            sessions_dir = settings.project_root / ".tapps-mcp" / "sessions"
            persist_path = sessions_dir / "checklist_calls.jsonl"
            CallTracker.set_persist_path(persist_path)
            _checklist_state["persist_configured"] = True
        CallTracker.record(tool_name, success=success)
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
        # Story 74.2: preserve checklist next_steps for json/compact (CI) output
        if tool_name == "tapps_checklist" and data.get("next_steps"):
            pass  # keep machine-readable next_steps from _checklist_*_format
        else:
            data["next_steps"] = steps
    if progress:
        data["pipeline_progress"] = progress
    if workflow:
        data["suggested_workflow"] = workflow
    return response


# ---------------------------------------------------------------------------
# Core tools (kept in server.py — simple, few dependencies).
# Registered conditionally in register_core_tools() (Epic 79.1).
# ---------------------------------------------------------------------------


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
        _record_call("tapps_security_scan", success=False)
        return error_response("tapps_security_scan", "path_denied", str(exc))

    from tapps_mcp.security.security_scanner import run_security_scan

    settings = load_settings()
    result = run_security_scan(
        str(resolved),
        scan_secrets=scan_secrets,
        cwd=str(settings.project_root),
        timeout=settings.tool_timeout,
    )

    if not result.passed:
        _record_call("tapps_security_scan", success=False)

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
    # Issue #79: surface a hint when Context7 is not configured and we're
    # serving from the LlmsTxt fallback — users often don't realize they're
    # running in degraded mode.
    source_str = str(result.source or "").lower()
    has_key = bool(
        os.environ.get("TAPPS_MCP_CONTEXT7_API_KEY")
        or os.environ.get("CONTEXT7_API_KEY")
    )
    if not has_key and ("llmstxt" in source_str or source_str == "fallback"):
        data["context7_hint"] = (
            "Set TAPPS_MCP_CONTEXT7_API_KEY for richer docs via Context7 "
            "(currently using LlmsTxt fallback)."
        )
    return data


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


def _checklist_json_format(
    result: ChecklistResult,
    auto_run_results: dict[str, Any],
    *,
    checklist_session_id: str | None,
    trace_hint: dict[str, str] | None,
) -> dict[str, Any]:
    """Build structured JSON output with computed counts and next_steps for checklist."""
    next_steps: list[str] = [h.reason for h in result.missing_required_hints]
    next_steps.extend(h.reason for h in result.missing_recommended_hints)

    data: dict[str, Any] = {
        "task_type": result.task_type,
        "resolved_policy_task_type": result.resolved_policy_task_type,
        "policy_fallback": result.policy_fallback,
        "checklist_policy_version": result.checklist_policy_version,
        "checklist_session_id": checklist_session_id,
        "otel_trace_hint": trace_hint,
        "complete": result.complete,
        "total_calls": result.total_calls,
        "required": {
            "total": (
                len(result.required_tool_names)
                if result.required_tool_names
                else len(result.missing_required) + len(result.satisfied_required_tools)
            ),
            "satisfied": result.satisfied_required_tools,
            "missing": result.missing_required,
        },
        "recommended": {
            "total": (
                len(result.recommended_tool_names)
                if result.recommended_tool_names
                else len(result.missing_recommended) + len(result.satisfied_recommended_tools)
            ),
            "satisfied": result.satisfied_recommended_tools,
            "missing": result.missing_recommended,
        },
        "optional": {
            "total": (
                len(result.optional_tool_names)
                if result.optional_tool_names
                else len(result.missing_optional) + len(result.satisfied_optional_tools)
            ),
            "satisfied": result.satisfied_optional_tools,
            "missing": result.missing_optional,
        },
        "priority_actions": result.missing_required[:3] if result.missing_required else [],
        "next_steps": next_steps,
        "full": result.model_dump(),
    }
    if auto_run_results:
        data["auto_run_results"] = auto_run_results
    return data


def _checklist_compact_format(
    result: ChecklistResult,
    auto_run_results: dict[str, Any],
    *,
    checklist_session_id: str | None,
    trace_hint: dict[str, str] | None,
) -> dict[str, Any]:
    """Build a short 1-2 line compact summary for checklist."""
    req_tot = len(result.required_tool_names)
    if req_tot == 0:
        req_tot = len(result.missing_required) + len(result.satisfied_required_tools)
    req_sat = len(result.satisfied_required_tools)
    parts = [
        f"complete={result.complete}",
        f"required {req_sat}/{req_tot} satisfied",
    ]
    if result.missing_required:
        missing_names = ", ".join(result.missing_required)
        parts.append(f"{len(result.missing_required)} required missing ({missing_names})")
    if result.missing_recommended:
        missing_names = ", ".join(result.missing_recommended)
        parts.append(
            f"{len(result.missing_recommended)} recommended missing ({missing_names})"
        )

    summary = f"Checklist {result.task_type}: {', '.join(parts)}"

    next_steps: list[str] = [h.reason for h in result.missing_required_hints]
    next_steps.extend(h.reason for h in result.missing_recommended_hints)

    data: dict[str, Any] = {
        "summary": summary,
        "complete": result.complete,
        "task_type": result.task_type,
        "resolved_policy_task_type": result.resolved_policy_task_type,
        "checklist_policy_version": result.checklist_policy_version,
        "checklist_session_id": checklist_session_id,
        "otel_trace_hint": trace_hint,
        "total_calls": result.total_calls,
        "next_steps": next_steps,
        "full": result.model_dump(),
    }
    if auto_run_results:
        data["auto_run_results"] = auto_run_results
    return data


def _optional_otel_trace_hint() -> dict[str, str] | None:
    tid = (os.environ.get("TAPPS_OTEL_TRACE_ID") or "").strip()
    sid = (os.environ.get("TAPPS_OTEL_SPAN_ID") or "").strip()
    if not tid and not sid:
        return None
    return {"trace_id": tid, "span_id": sid}


async def tapps_checklist(
    task_type: str = "review",
    auto_run: bool = False,
    output_format: str = "markdown",
    commit_sha: str = "",
    epic_file_path: str = "",
    reset_checklist_session: bool = False,
) -> dict[str, Any]:
    """REQUIRED as the FINAL step before declaring work complete.

    Args:
        task_type: feature | bugfix | refactor | security | review | epic.
        auto_run: When True, automatically run missing required validations
            (via tapps_validate_changed) and re-evaluate the checklist.
        output_format: "markdown" (default, full table), "json" (structured counts),
            or "compact" (short 1-2 line summary).
        commit_sha: Optional git SHA to embed in response. If empty, auto-detects HEAD.
        epic_file_path: When non-empty, runs epic markdown structural validation
            (``task_type`` should usually be ``epic``).
        reset_checklist_session: When True, starts a new checklist session boundary
            before evaluating (rotates session id; call from long-lived servers).
    """
    start = time.perf_counter_ns()

    valid_formats = {"markdown", "json", "compact"}
    if output_format not in valid_formats:
        return error_response(
            "tapps_checklist",
            "invalid_format",
            f"output_format must be one of {sorted(valid_formats)}, got '{output_format}'",
        )

    try:
        from tapps_mcp.tools.checklist import CallTracker

        if reset_checklist_session:
            CallTracker.begin_session()
        _record_call("tapps_checklist")

        settings = load_settings()
        eval_kw: dict[str, Any] = {
            "require_success": settings.checklist_require_success,
            "strict_unknown_task_type": settings.checklist_strict_unknown_task_types,
            "project_root": settings.project_root,
        }

        def _eval_checklist() -> ChecklistResult:
            epic = epic_file_path.strip()
            if epic:
                epic_res = CallTracker.evaluate_epic(file_path=epic, **eval_kw)
                return epic_res
            return CallTracker.evaluate(task_type, **eval_kw)

        try:
            result = _eval_checklist()
        except ValueError as exc:
            return error_response(
                "tapps_checklist",
                "invalid_task_type",
                str(exc),
            )

        auto_run_results: dict[str, Any] = {}

        if auto_run and result.missing_required:
            # validate_changed covers score_file + quality_gate + security_scan
            needs_validate = set(result.missing_required) & {
                "tapps_score_file",
                "tapps_quality_gate",
                "tapps_security_scan",
                "tapps_validate_changed",
                "tapps_quick_check",
            }

            if needs_validate:
                try:
                    from tapps_mcp.server_pipeline_tools import tapps_validate_changed

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
            result = _eval_checklist()

        elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
        _record_execution("tapps_checklist", start)
        trace_hint = _optional_otel_trace_hint()
        session_id = CallTracker.get_active_checklist_session_id()

        git_context: dict[str, Any] | None = None
        try:
            from tapps_mcp.tools.checklist import _get_git_context

            git_context = await _get_git_context(commit_sha=commit_sha)
        except Exception:
            git_context = None

        resp_data: dict[str, Any]
        if output_format == "json":
            resp_data = _checklist_json_format(
                result,
                auto_run_results,
                checklist_session_id=session_id,
                trace_hint=trace_hint,
            )
        elif output_format == "compact":
            resp_data = _checklist_compact_format(
                result,
                auto_run_results,
                checklist_session_id=session_id,
                trace_hint=trace_hint,
            )
        else:
            resp_data = result.model_dump()
            if auto_run_results:
                resp_data["auto_run_results"] = auto_run_results

        resp_data["git_context"] = git_context
        resp_data["checklist_session_id"] = session_id
        resp_data["otel_trace_hint"] = trace_hint
        if result.checklist_policy_version:
            resp_data["checklist_policy_version"] = result.checklist_policy_version

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

        # Surface epic_validation on markdown path when present
        ev = getattr(result, "epic_validation", None)
        if ev is not None:
            resp_data["epic_validation"] = ev.model_dump()

        resp = success_response("tapps_checklist", elapsed_ms, resp_data)

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
                    checklist_policy_version=result.checklist_policy_version or None,
                    resolved_policy_task_type=result.resolved_policy_task_type or None,
                    checklist_session_id=session_id,
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


# ---------------------------------------------------------------------------
# Register tools from extracted modules & re-export for backward compatibility
# ---------------------------------------------------------------------------


def _register_core_tools(mcp_instance: FastMCP, allowed_tools: frozenset[str]) -> None:
    """Register core tools (server.py) when their name is in allowed_tools (Epic 79.1)."""
    if "tapps_server_info" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_server_info)
    if "tapps_security_scan" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_security_scan)
    if "tapps_lookup_docs" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY_OPEN)(tapps_lookup_docs)
    if "tapps_validate_config" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_validate_config)
    if "tapps_checklist" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_checklist)


def _register_tool_modules() -> None:
    """Import and register tools from extracted server modules.

    Loads settings, resolves allowed_tools (Epic 79.1), registers core tools
    conditionally, then each module's register(mcp, allowed_tools).
    """
    settings = load_settings()
    allowed_tools = _resolve_allowed_tools(settings)

    _register_core_tools(mcp, allowed_tools)

    from tapps_mcp import (
        server_analysis_tools,
        server_memory_tools,
        server_metrics_tools,
        server_pipeline_tools,
        server_resources,
        server_scoring_tools,
    )

    server_scoring_tools.register(mcp, allowed_tools)
    server_pipeline_tools.register(mcp, allowed_tools)
    server_metrics_tools.register(mcp, allowed_tools)
    server_memory_tools.register(mcp, allowed_tools)
    server_analysis_tools.register(mcp, allowed_tools)
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
tapps_memory = _memory.tapps_memory
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
        from starlette.requests import Request
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

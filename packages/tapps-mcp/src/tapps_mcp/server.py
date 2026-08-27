"""TappsMCP MCP server entry point.

Creates the FastMCP server instance, registers all tools, and provides
``run_server()`` for the CLI.

Tool handlers are split across modules for maintainability:
  - ``server_scoring_tools``: tapps_score_file, tapps_quality_gate, tapps_quick_check
  - ``server_pipeline_tools``: tapps_validate_changed, tapps_session_start, tapps_init
  - ``server_metrics_tools``: tapps_dashboard, tapps_stats, tapps_feedback
  - ``server_memory_tools``: (internal lifecycle helpers only; no public MCP tools)
  - ``server_analysis_tools``: tapps_session_notes, tapps_impact_analysis, tapps_report,
    tapps_dead_code, tapps_dependency_scan, tapps_dependency_graph, tapps_audit_campaign
  - ``server_lookup_tools``: tapps_lookup_docs
  - ``server_research_tools``: tapps_research
  - ``server_system_tools``: tapps_server_info, tapps_security_scan, tapps_validate_config
  - ``server_checklist_tools``: tapps_checklist
  - ``server_resources``: MCP resources and prompts
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tapps_core.common.models import InstalledTool, StartupDiagnostics
    from tapps_core.config.settings import TappsMCPSettings
    from tapps_core.metrics.collector import MetricsHub

import structlog
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from tapps_core.common.logging import (
    bootstrap_logging_from_env,
    reconfigure_logging_if_needed,
)
from tapps_core.config.settings import load_settings
from tapps_core.knowledge.kg_keys import entity_spec
from tapps_mcp import __version__
from tapps_mcp.common.developer_workflow import (
    DAILY_STEPS,
    RECOMMENDED_WORKFLOW_TEXT,
)
from tapps_mcp.server_helpers import (
    _get_brain_bridge,
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

# TAP-1986: defer_loading meta — non-daily-driver tools carry this so
# Claude Code (with advanced-tool-use-2025-11-20 header) loads them
# on-demand via Tool Search, keeping the eager catalog ≤ 8 tools.
_META_DEFERRED: dict[str, Any] = {"defer_loading": True}

# ---------------------------------------------------------------------------
# FastMCP server instance
# ---------------------------------------------------------------------------

_TAPPS_MCP_SERVER_INSTRUCTIONS = """\
Use this server whenever you are about to write, modify, validate, or ship \
Python (or supported polyglot) code in this project -- even for tasks you \
think you can finish from memory. The tools return deterministic, \
checker-backed verdicts (ruff, mypy, bandit, radon, vulture, pip-audit) \
that catch issues your training data cannot: stale APIs, real CVEs, current \
project standards, and per-file quality scores against the configured gate.

Call these first, even when you think you know the answer:
- tapps_session_start at session start -- bootstraps project context and \
the checker environment. Skipping it leaves later tools running in degraded \
mode with generic verdicts. It returns the compact bootstrap payload by \
default; pass quick=False (or call tapps_doctor) when you actually need \
brain health, memory status, and install-drift diagnostics.
- tapps_lookup_docs before using any external library API (React, Next.js, \
FastAPI, Django, httpx, pydantic, structlog, click, pytest, anything) -- \
returns current Context7 docs so you do not hallucinate signatures.
- tapps_quick_check after editing any Python file -- one call runs scoring \
+ quality gate + security scan; never assume "looks fine" on a diff.
- tapps_validate_changed before declaring multi-file work complete -- batch \
gate on git-changed files; pass file_paths explicitly.
- tapps_checklist as the final verification step -- confirms no required \
tool in the pipeline was skipped.

USE ALSO FOR understanding existing code -- not just writing it. When the \
task is "how does X work", "what calls Y", "trace the flow from A to B", \
"where is this wired up", "what breaks if I change Z", or "map this \
subsystem", reach for these BEFORE falling back to grep/read -- they return \
checker-backed caller/callee edges with file:line and an honest completeness \
signal, which text search cannot:
- tapps_call_graph -- function-level callers, callees, and token-budgeted \
call chains for one symbol. Use for "what calls X" / "trace this flow"; it \
answers from the resolved edge index, not text matching.
- tapps_dependency_graph -- module import graph, circular imports, coupling \
metrics. Use to understand how a subsystem hangs together.
- tapps_impact_analysis -- module-level blast radius before an API change. \
Use for "what depends on this" / "what will I break".
- tapps_diff_impact -- ranks the tests affected by your changed files. Use \
after edits, before running the suite, to find what to run.

Prefer these tools over web search, guessing from memory, or relying on \
your built-in linter heuristics: web search is slow and stale, memory is \
the #1 source of hallucinated APIs, and these tools surface the actual \
project-specific gate thresholds.

Do not use for: chitchat, generic programming questions unrelated to the \
project, generating content unrelated to code (release notes, marketing \
copy), or as a substitute for reading the user's request carefully.
"""

mcp = FastMCP("TappsMCP", instructions=_TAPPS_MCP_SERVER_INSTRUCTIONS)


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

    Delegates to :func:`tapps_mcp.common.cache_paths.resolve_kb_cache_dir` so
    every caller in the codebase resolves the same cache directory (Fix E).
    """
    from tapps_mcp.common.cache_paths import resolve_kb_cache_dir

    return resolve_kb_cache_dir(project_root)


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

# Canonical list of all TappsMCP tools (42).
# Used for filtering and fallback.
ALL_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "tapps_server_info",
        "tapps_session_start",
        "tapps_session_end",
        "tapps_handoff_save",
        "tapps_score_file",
        "tapps_security_scan",
        "tapps_quality_gate",
        "tapps_lookup_docs",
        "tapps_research",
        "tapps_validate_config",
        "tapps_validate_changed",
        "tapps_quick_check",
        "tapps_checklist",
        "tapps_session_notes",
        "tapps_impact_analysis",
        "tapps_call_graph",
        "tapps_diff_impact",
        "tapps_report",
        "tapps_init",
        "tapps_upgrade",
        "tapps_doctor",
        "tapps_set_engagement_level",
        "tapps_dashboard",
        "tapps_stats",
        "tapps_feedback",
        "tapps_usage",
        "tapps_dead_code",
        "tapps_dependency_scan",
        "tapps_dependency_graph",
        "tapps_audit_campaign",
        "tapps_pipeline",
        "tapps_decompose",
        "tapps_linear_snapshot_get",
        "tapps_linear_snapshot_put",
        "tapps_linear_snapshot_invalidate",
        "tapps_linear_count",
        "tapps_release_update",
        # TAP-2014: hive elevation safety gate
        "brain_propose_hive_elevation",
        "brain_approve_hive_elevation",
        # TAP-2010: list_issues cache-first read gate
        "tapps_linear_list_issues",
        # TAP-2717: deterministic finding-to-story converter
        "tapps_finding_to_story",
        # TAP-2798: close audit coverage after a fix lands (audit-fix loop)
        "tapps_audit_close_coverage",
        # TAP-3895: slim tapps_memory facade on nlt-memory profile only
        "tapps_memory",
        # ADR-0025: deterministic domain playbooks (deferred on nlt-build)
        "tapps_domain_playbook",
    }
)

# Tier 1 from TOOL-TIER-RANKING (Epic 79.1)
TOOL_PRESET_CORE: frozenset[str] = frozenset(
    {
        "tapps_session_start",
        "tapps_quick_check",
        "tapps_validate_changed",
        "tapps_quality_gate",
        "tapps_checklist",
        "tapps_lookup_docs",
        "tapps_research",
        "tapps_security_scan",
        "tapps_pipeline",
    }
)

# Tier 1 + Tier 2
TOOL_PRESET_PIPELINE: frozenset[str] = TOOL_PRESET_CORE | frozenset(
    {
        "tapps_score_file",
        "tapps_impact_analysis",
        "tapps_validate_config",
    }
)

# Role presets Phase 1 (Epic 79.5) — from ROLE-PRESETS-IMPLEMENT-FIRST.md
TOOL_PRESET_REVIEWER: frozenset[str] = frozenset(
    {
        "tapps_session_start",
        "tapps_quick_check",
        "tapps_validate_changed",
        "tapps_quality_gate",
        "tapps_checklist",
        "tapps_security_scan",
        "tapps_score_file",
        "tapps_dead_code",
        "tapps_dependency_scan",
    }
)
TOOL_PRESET_PLANNER: frozenset[str] = frozenset(
    {
        "tapps_session_start",
        "tapps_checklist",
        "tapps_validate_changed",
        "tapps_quality_gate",
        "tapps_score_file",
    }
)
TOOL_PRESET_FRONTEND: frozenset[str] = frozenset(
    {
        "tapps_session_start",
        "tapps_quick_check",
        "tapps_score_file",
        "tapps_lookup_docs",
        "tapps_research",
        "tapps_quality_gate",
    }
)
TOOL_PRESET_DEVELOPER: frozenset[str] = frozenset(
    {
        "tapps_session_start",
        "tapps_quick_check",
        "tapps_validate_changed",
        "tapps_quality_gate",
        "tapps_checklist",
        "tapps_score_file",
        "tapps_security_scan",
        "tapps_lookup_docs",
        "tapps_research",
        "tapps_impact_analysis",
    }
)

# TAP-485: Mode presets for --mode quality|admin|all
# quality mode: coding session tools (reduces context overhead for daily use)
TAPPS_TOOL_PRESET_QUALITY: frozenset[str] = frozenset(
    {
        "tapps_session_start",
        "tapps_quick_check",
        "tapps_score_file",
        "tapps_quality_gate",
        "tapps_checklist",
        "tapps_validate_changed",
        "tapps_security_scan",
        "tapps_lookup_docs",
        "tapps_research",
        "tapps_dead_code",
        "tapps_impact_analysis",
        "tapps_validate_config",
        "tapps_dependency_scan",
        "tapps_dependency_graph",
        "tapps_audit_campaign",
        "tapps_usage",
    }
)

# admin mode: setup/troubleshooting tools
TAPPS_TOOL_PRESET_ADMIN: frozenset[str] = frozenset(
    {
        "tapps_init",
        "tapps_upgrade",
        "tapps_doctor",
        "tapps_server_info",
        "tapps_set_engagement_level",
        "tapps_dashboard",
        "tapps_stats",
        "tapps_feedback",
        "tapps_usage",
        "tapps_report",
        "tapps_pipeline",
        "tapps_decompose",
        "tapps_session_notes",
        "tapps_handoff_save",
        "tapps_session_end",
    }
)

# Epic 109 / ADR-0016 NLT plugin profiles — see docs/architecture/nlt-mcp-plugin-spec.yaml
TOOL_PROFILE_NLT_BUILD: frozenset[str] = frozenset(
    {
        "tapps_session_start",
        "tapps_quick_check",
        "tapps_validate_changed",
        "tapps_quality_gate",
        "tapps_checklist",
        "tapps_lookup_docs",
        "tapps_research",
        "tapps_score_file",
        "tapps_security_scan",
        "tapps_impact_analysis",
        "tapps_call_graph",
        "tapps_diff_impact",
        "tapps_usage",
        "tapps_validate_config",
        "tapps_dead_code",
        "tapps_dependency_graph",
        "tapps_dependency_scan",
        "tapps_report",
        "tapps_audit_campaign",
        "tapps_domain_playbook",
    }
)

TOOL_PROFILE_NLT_MEMORY: frozenset[str] = frozenset(
    {
        # Bootstrap tool: the shared server banner instructs the agent to call
        # tapps_session_start first on every tapps-mcp profile, and the
        # session_start_gate blocks all tools until it runs. Register it here so
        # a bare tapps_session_start() resolves on nlt-memory too, instead of
        # 404-ing when the agent reaches this server first (TAP session-start
        # routing fix).
        "tapps_session_start",
        "tapps_memory",
        "tapps_session_notes",
        "tapps_session_end",
        "tapps_handoff_save",
    }
)

TOOL_PROFILE_NLT_SETUP: frozenset[str] = frozenset(
    {
        # Bootstrap tool: session_start is the canonical first-call and belongs
        # with the setup/bootstrap family (init, doctor, server_info). Without it
        # here, the banner's "call tapps_session_start" instruction is a broken
        # promise on nlt-setup and the agent's natural guess 404s.
        "tapps_session_start",
        "tapps_init",
        "tapps_upgrade",
        "tapps_doctor",
        "tapps_server_info",
        "tapps_set_engagement_level",
        "tapps_pipeline",
        "tapps_stats",
    }
)

# Legacy Epic 109 names — aliases for one release (ADR-0016)
TOOL_PROFILE_NLT_CODE_QUALITY: frozenset[str] = TOOL_PROFILE_NLT_BUILD
TOOL_PROFILE_NLT_PLATFORM_ADMIN: frozenset[str] = TOOL_PROFILE_NLT_SETUP

_NLT_TAPPS_TOOL_PRESETS: dict[str, frozenset[str]] = {
    "nlt-build": TOOL_PROFILE_NLT_BUILD,
    "nlt-memory": TOOL_PROFILE_NLT_MEMORY,
    "nlt-setup": TOOL_PROFILE_NLT_SETUP,
    "nlt-code-quality": TOOL_PROFILE_NLT_CODE_QUALITY,
    "nlt-platform-admin": TOOL_PROFILE_NLT_PLATFORM_ADMIN,
}

_FALLBACK_TOOL_LIST: list[str] = sorted(ALL_TOOL_NAMES)

_SECURITY_SCAN_FINDING_LIMIT: int = 50

_VALID_CONFIG_TYPES: frozenset[str] = frozenset(
    {
        "dockerfile",
        "docker_compose",
        "websocket",
        "mqtt",
        "influxdb",
        "mcp",
        "yaml_manifest",
    }
)

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
    elif settings.tool_preset == "quality":
        allowed = set(TAPPS_TOOL_PRESET_QUALITY)
    elif settings.tool_preset == "admin":
        allowed = set(TAPPS_TOOL_PRESET_ADMIN)
    elif settings.tool_preset == "full":
        allowed = set(ALL_TOOL_NAMES)
    elif settings.tool_preset in _NLT_TAPPS_TOOL_PRESETS:
        allowed = set(_NLT_TAPPS_TOOL_PRESETS[settings.tool_preset])
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
        os.environ.get("TAPPS_MCP_CONTEXT7_API_KEY") or os.environ.get("CONTEXT7_API_KEY")
    )
    summary: dict[str, Any] = {
        "primary": "context7" if has_key else "llmstxt",
        "context7_configured": has_key,
    }
    if not has_key:
        summary["hint"] = (
            "Set TAPPS_MCP_CONTEXT7_API_KEY for richer docs via Context7. https://context7.com"
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
        "brain_bridge": _brain_bridge_status_for_server_info(),
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


def _brain_bridge_status_for_server_info() -> dict[str, Any]:
    """Non-blocking BrainBridge snapshot for ``tapps_server_info`` (TAP-517).

    Peeks the cached singleton so the info tool does not force a Postgres
    connection just to answer a status query. When the bridge has not been
    initialized yet, reports ``{"initialized": False}``.
    """
    try:
        from tapps_mcp.server_helpers import _peek_brain_bridge

        bridge = _peek_brain_bridge()
    except Exception as exc:
        return {"initialized": False, "error": str(exc)}
    if bridge is None:
        return {"initialized": False}
    return {"initialized": True, **bridge.status()}


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
    action: str | None = None,
) -> None:
    """Record tool execution metrics to the MetricsHub.

    ``action`` carries the sub-action for umbrella tools (e.g.
    ``tapps_memory(action="save")``) so per-action counts are recoverable
    from ``tool_calls_*.jsonl`` without a second tool-name namespace.
    """
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
        action=action,
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
# Shared tool internals that must resolve against this module's namespace.
#
# ``_server_info_async`` and ``_fire_security_scan_events`` stay here because
# callers and tests bind them (and their collaborators ``_get_brain_bridge`` /
# ``asyncio``) through ``tapps_mcp.server``; moving them would silently defeat
# those patches. The public tool wrappers live in ``server_system_tools``.
# ---------------------------------------------------------------------------


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


_SECURITY_EMISSION_SEVERITIES: frozenset[str] = frozenset({"critical", "high", "medium"})


def _fire_security_scan_events(
    file_path: str,
    bandit_issues: list[Any],
    secret_findings: list[Any],
) -> None:
    """Fire brain KG events for above-floor security findings (fire-and-forget).

    Emits one ``security_finding`` event per bandit/secret finding with severity
    in ``{critical, high, medium}``. Dispatched via ``asyncio.create_task`` —
    never blocks the security scan response. Mirror of ``_fire_quality_gate_events``
    in ``server_scoring_tools.py``.
    """

    async def _emit() -> None:
        try:
            bridge = _get_brain_bridge()
            if bridge is None or not hasattr(bridge, "record_kg_event"):
                return
            for issue in bandit_issues:
                if issue.severity not in _SECURITY_EMISSION_SEVERITIES:
                    continue
                finding_id = f"bandit:{issue.code}"
                await bridge.record_kg_event(
                    event_type="security_finding",
                    entities=[
                        entity_spec("file", file_path),
                        entity_spec("rule", finding_id),
                    ],
                    edges=None,
                    payload_data={
                        "severity": issue.severity,
                        "line": issue.line,
                        "file": issue.file,
                        "file_path": file_path,
                        "subject_key": file_path,
                    },
                )
            for finding in secret_findings:
                if finding.severity not in _SECURITY_EMISSION_SEVERITIES:
                    continue
                finding_id = f"secret:{finding.secret_type}"
                await bridge.record_kg_event(
                    event_type="security_finding",
                    entities=[
                        entity_spec("file", file_path),
                        entity_spec("rule", finding_id),
                    ],
                    edges=None,
                    payload_data={
                        "severity": finding.severity,
                        "line": finding.line_number,
                        "file_path": file_path,
                        "subject_key": file_path,
                        "file": finding.file_path,
                    },
                )
        except Exception:
            pass  # best-effort: never block security scan for telemetry

    # Fire-and-forget telemetry; no reference kept on purpose.
    with contextlib.suppress(Exception):
        asyncio.create_task(_emit())  # noqa: RUF006


# ---------------------------------------------------------------------------
# Register tools from extracted modules & re-export for backward compatibility
# ---------------------------------------------------------------------------


def _register_tool_modules() -> None:
    """Import and register tools from extracted server modules.

    Loads settings, resolves allowed_tools (Epic 79.1), then calls each
    module's ``register(mcp, allowed_tools)``.
    """
    settings = load_settings()
    allowed_tools = _resolve_allowed_tools(settings)

    from tapps_mcp import (
        server_analysis_tools,
        server_checklist_tools,
        server_linear_tools,
        server_lookup_tools,
        server_memory_tools,
        server_metrics_tools,
        server_pipeline_tools,
        server_release_tools,
        server_research_tools,
        server_resources,
        server_scoring_tools,
        server_system_tools,
    )

    server_scoring_tools.register(mcp, allowed_tools)
    server_pipeline_tools.register(mcp, allowed_tools)
    server_metrics_tools.register(mcp, allowed_tools)
    server_memory_tools.register(mcp, allowed_tools)
    server_analysis_tools.register(mcp, allowed_tools)
    server_linear_tools.register(mcp, allowed_tools)
    server_release_tools.register(mcp, allowed_tools)
    server_lookup_tools.register(mcp, allowed_tools)
    server_research_tools.register(mcp, allowed_tools)
    server_system_tools.register(mcp, allowed_tools)
    server_checklist_tools.register(mcp, allowed_tools)
    # Pipeline prompts/resources are build-owned; skip on memory/setup profiles
    # so they do not spam every tapps-mcp process catalog.
    _skip_pipeline_resources = frozenset({"nlt-memory", "nlt-setup", "nlt-platform-admin"})
    server_resources.register(
        mcp,
        include_pipeline=settings.tool_preset not in _skip_pipeline_resources,
    )


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
_lookup = sys.modules["tapps_mcp.server_lookup_tools"]
_research = sys.modules["tapps_mcp.server_research_tools"]
_system = sys.modules["tapps_mcp.server_system_tools"]
_checklist = sys.modules["tapps_mcp.server_checklist_tools"]

tapps_score_file = _scoring.tapps_score_file
tapps_quality_gate = _scoring.tapps_quality_gate
tapps_quick_check = _scoring.tapps_quick_check
tapps_validate_changed = _pipeline.tapps_validate_changed
tapps_session_start = _pipeline.tapps_session_start
tapps_session_end = _pipeline.tapps_session_end
tapps_handoff_save = _pipeline.tapps_handoff_save
tapps_init = _pipeline.tapps_init
tapps_dashboard = _metrics.tapps_dashboard
tapps_stats = _metrics.tapps_stats
tapps_feedback = _metrics.tapps_feedback
tapps_session_notes = _analysis.tapps_session_notes
tapps_impact_analysis = _analysis.tapps_impact_analysis
tapps_call_graph = _analysis.tapps_call_graph
tapps_diff_impact = _analysis.tapps_diff_impact
tapps_report = _analysis.tapps_report
tapps_dead_code = _analysis.tapps_dead_code
tapps_dependency_scan = _analysis.tapps_dependency_scan
tapps_dependency_graph = _analysis.tapps_dependency_graph
tapps_audit_campaign = _analysis.tapps_audit_campaign
_promote_note_to_memory = _analysis._promote_note_to_memory
tapps_lookup_docs = _lookup.tapps_lookup_docs
tapps_research = _research.tapps_research
tapps_server_info = _system.tapps_server_info
tapps_security_scan = _system.tapps_security_scan
tapps_validate_config = _system.tapps_validate_config
tapps_checklist = _checklist.tapps_checklist


# ---------------------------------------------------------------------------
# Server runner
# ---------------------------------------------------------------------------


def run_server(
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """Start the TappsMCP MCP server."""
    bootstrap_level, bootstrap_json = bootstrap_logging_from_env()
    settings = load_settings()
    reconfigure_logging_if_needed(
        settings,
        bootstrap_level=bootstrap_level,
        bootstrap_json=bootstrap_json,
    )

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

        from tapps_core.http.middleware import wrap_streamable_http_app

        mcp_app = mcp.streamable_http_app()

        def _root(_request: Request) -> HTMLResponse:
            return HTMLResponse(
                "<!DOCTYPE html><html><head><title>TappsMCP</title></head><body>"
                "<h1>TappsMCP is running</h1><p>MCP endpoint: <a href='/mcp'>/mcp</a></p>"
                "<p>Version: " + __version__ + "</p></body></html>",
                status_code=200,
            )

        mcp_app.routes.insert(0, Route("/", _root))
        wrapped_app = wrap_streamable_http_app(mcp_app)
        uvicorn.run(wrapped_app, host=host, port=port)
    else:
        msg = f"Unsupported transport: {transport}"
        raise ValueError(msg)

"""Pipeline orchestration and validation tool handlers for TappsMCP.

Functions are defined at module level (importable for tests) and
registered on the ``mcp`` instance via :func:`register`.

This module is a thin orchestrator. Implementation details are
split across:

- :mod:`tapps_mcp.tools.validate_changed` — ``tapps_validate_changed`` and helpers
- :mod:`tapps_mcp.tools.session_start_helpers` — session-start background ops
- :mod:`tapps_mcp.tools.decompose_helpers` — ``tapps_decompose`` and model tier classification

The shared session state (``_session_state``, ``_state_lock``,
``_background_tasks``) lives here so both helper modules can look it up
through ``tapps_mcp.server_pipeline_tools`` without circular imports.

Re-exports below preserve the public contract used by existing tests:
they continue to import symbols from ``tapps_mcp.server_pipeline_tools``
and patch them via ``patch("tapps_mcp.server_pipeline_tools.X")``.
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
from pathlib import Path
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import structlog
from mcp.server.fastmcp import Context
from mcp.types import ToolAnnotations

from tapps_core.config.settings import load_settings
from tapps_mcp.server_helpers import (
    collect_session_hive_status,
    emit_ctx_info,
    error_response,
    initial_session_hive_status,
    success_response,
)

# ---------------------------------------------------------------------------
# Re-exports from split modules (backward compatibility for tests)
# ---------------------------------------------------------------------------
from tapps_mcp.tools.decompose_helpers import (
    TaskUnit,
    _classify_model_tier,
    _classify_risk,
    _decompose_task,
    _split_task_into_phrases,
    _summarize_quick_check,
    tapps_decompose,
)
from tapps_mcp.tools.session_start_helpers import (
    _build_search_first,
    _collect_brain_bridge_health,
    _collect_memory_status,
    _DOCS_COVERED,
    _enrich_memory_profile_status,
    _enrich_memory_status_hints,
    _maybe_auto_gc,
    _maybe_consolidation_scan,
    _maybe_validate_memories,
    _normalise_dep,
    _process_session_capture,
    _schedule_background_maintenance,
)
from tapps_mcp.tools.validate_changed import (
    _AUTO_DETECT_BUDGET_S as _AUTO_DETECT_BUDGET_S,
    _cache_hit_as_file_result as _cache_hit_as_file_result,
    _collect_results as _collect_results,
    _discover_changed_files as _discover_changed_files,
    _emit_file_info as _emit_file_info,
    _maybe_run_wizard as _maybe_run_wizard,
    _maybe_warm_dependency_cache as _maybe_warm_dependency_cache,
    _partition_by_cache as _partition_by_cache,
    _PROGRESS_HEARTBEAT_INTERVAL as _PROGRESS_HEARTBEAT_INTERVAL,
    _ProgressTracker as _ProgressTracker,
    _report_initial_progress as _report_initial_progress,
    _start_progress_reporting as _start_progress_reporting,
    _VALIDATE_CONCURRENCY as _VALIDATE_CONCURRENCY,
    _VALIDATE_OK_MARKER as _VALIDATE_OK_MARKER,
    _VALIDATION_PROGRESS_FILE as _VALIDATION_PROGRESS_FILE,
    _validate_progress_heartbeat as _validate_progress_heartbeat,
    _validate_single_file as _validate_single_file,
    _warm_dependency_cache as _warm_dependency_cache,
    _write_validate_ok_marker as _write_validate_ok_marker,
    tapps_validate_changed as tapps_validate_changed,
)
from tapps_mcp.tools.validate_changed_output import (
    _build_per_file_results as _build_per_file_results,
    _build_structured_validation_output as _build_structured_validation_output,
    _build_validation_summary as _build_validation_summary,
    _compute_impact_analysis as _compute_impact_analysis,
    _handle_no_changed_files as _handle_no_changed_files,
    _resolve_security_depth as _resolve_security_depth,
    _SEVERITY_RANK as _SEVERITY_RANK,
)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

__all__ = [
    # Re-exports for backward compatibility
    "TaskUnit",
    "_AUTO_DETECT_BUDGET_S",
    "_DOCS_COVERED",
    "_PROGRESS_HEARTBEAT_INTERVAL",
    "_ProgressTracker",
    "_SEVERITY_RANK",
    "_VALIDATE_CONCURRENCY",
    "_VALIDATE_OK_MARKER",
    "_VALIDATION_PROGRESS_FILE",
    "_background_tasks",
    "_build_per_file_results",
    "_build_search_first",
    "_build_structured_validation_output",
    "_build_validation_summary",
    "_cache_hit_as_file_result",
    "_classify_model_tier",
    "_classify_risk",
    "_collect_brain_bridge_health",
    "_collect_memory_status",
    "_collect_results",
    "_compute_impact_analysis",
    "_current_docs_provider",
    "_decompose_task",
    "_discover_changed_files",
    "_emit_file_info",
    "_enrich_memory_profile_status",
    "_enrich_memory_status_hints",
    "_handle_no_changed_files",
    "_maybe_auto_gc",
    "_maybe_consolidation_scan",
    "_maybe_run_wizard",
    "_maybe_validate_memories",
    "_maybe_warm_dependency_cache",
    "_normalise_dep",
    "_partition_by_cache",
    "_process_session_capture",
    "_report_initial_progress",
    "_reset_session_consolidation_flag",
    "_reset_session_doc_validation_flag",
    "_reset_session_gc_flag",
    "_reset_session_state",
    "_resolve_security_depth",
    "_schedule_background_maintenance",
    "_session_start_quick",
    "_session_state",
    "_split_task_into_phrases",
    "_start_progress_reporting",
    "_state_lock",
    "_summarize_quick_check",
    "_validate_progress_heartbeat",
    "_validate_single_file",
    "_warm_dependency_cache",
    "_write_validate_ok_marker",
    "load_settings",
    "register",
    "tapps_decompose",
    "tapps_doctor",
    "tapps_init",
    "tapps_pipeline",
    "tapps_session_start",
    "tapps_set_engagement_level",
    "tapps_upgrade",
    "tapps_validate_changed",
]

_logger = structlog.get_logger(__name__)


def _current_docs_provider() -> dict[str, Any]:
    """Return a summary of the active docs-lookup provider (Issue #79).

    Gives agents a way to see at a glance whether ``tapps_lookup_docs``
    will use Context7 (full coverage) or the LlmsTxt fallback (reduced).
    """
    import os as _os

    has_key = bool(
        _os.environ.get("TAPPS_MCP_CONTEXT7_API_KEY") or _os.environ.get("CONTEXT7_API_KEY")
    )
    info: dict[str, Any] = {
        "primary": "context7" if has_key else "llmstxt",
        "context7_configured": has_key,
    }
    if not has_key:
        info["hint"] = (
            "Set TAPPS_MCP_CONTEXT7_API_KEY for richer docs via Context7. https://context7.com"
        )
    return info


# ---------------------------------------------------------------------------
# Shared session state (used by session_start_helpers via host-module lookup)
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _SessionFlags:
    """Track whether auto-GC and consolidation have already run this session."""

    gc_done: bool = False
    consolidation_done: bool = False
    doc_validation_done: bool = False


_session_state = _SessionFlags()
# Guards the async check-and-set in _maybe_validate_memories to prevent
# double-execution when concurrent session_start calls spawn background tasks.
_state_lock = asyncio.Lock()


def _reset_session_gc_flag() -> None:
    """Reset the auto-GC flag (for testing)."""
    _session_state.gc_done = False


def _reset_session_consolidation_flag() -> None:
    """Reset the consolidation scan flag (for testing)."""
    _session_state.consolidation_done = False


def _reset_session_doc_validation_flag() -> None:
    """Reset the doc validation flag (for testing)."""
    _session_state.doc_validation_done = False


def _reset_session_state() -> None:
    """Reset all session state flags (for testing)."""
    _session_state.gc_done = False
    _session_state.consolidation_done = False
    _session_state.doc_validation_done = False


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


# ---------------------------------------------------------------------------
# tapps_session_start
# ---------------------------------------------------------------------------
# Implementation helpers live in ``tapps_mcp.tools.session_start_core``.


def _detect_brain_auth_failure(
    settings: Any,
    memory_status: dict[str, Any] | None,
    elapsed_ms: int,
) -> dict[str, Any] | None:
    """TAP-1082 / TAP-1257: Detect tapps-brain auth-probe failures and return a hard error.

    Returns ``None`` when memory is disabled, when the agent has opted in to
    tolerating auth failures (``memory.tolerate_brain_auth_failure``), or when
    the auth probe did not return a recognised auth/identity failure.

    Recognised failure shapes:
      * HTTP 401 / 403 → ``code='brain_auth_failed'`` (TAP-1082)
      * HTTP 400 with ``X-Project-Id`` in the body → ``code='brain_project_id_missing'``
        (TAP-1257). tapps-brain 3.14.x returns this when the
        ``X-Project-Id`` header is missing on ``/mcp`` requests.
    """
    if not getattr(settings.memory, "enabled", True):
        return None
    if getattr(settings.memory, "tolerate_brain_auth_failure", False):
        return None
    if not isinstance(memory_status, dict):
        return None
    auth_probe = memory_status.get("auth_probe")
    if not isinstance(auth_probe, dict):
        return None
    http_status = auth_probe.get("http_status")
    detail_raw = auth_probe.get("detail") or auth_probe.get("error") or ""
    detail = str(detail_raw)

    if http_status == 400 and "X-Project-Id" in detail:
        message = (
            "tapps-brain rejected the /mcp request with HTTP 400 because the "
            "X-Project-Id header is missing. Memory operations cannot proceed."
        )
        return error_response(
            "tapps_session_start",
            "brain_project_id_missing",
            message,
            extra={
                "http_status": http_status,
                "memory_status": memory_status,
                "elapsed_ms": elapsed_ms,
                "next_steps": [
                    (
                        "Set TAPPS_MCP_MEMORY_BRAIN_PROJECT_ID in your env or "
                        ".mcp.json env block to the registered tapps-brain project slug"
                    ),
                    (
                        "Or set memory.brain_project_id (or memory.project_id, "
                        "auto-derived) in .tapps-mcp.yaml"
                    ),
                    (
                        "If running offline / without tapps-brain, set "
                        "memory.tolerate_brain_auth_failure: true in .tapps-mcp.yaml "
                        "to keep the degraded behavior"
                    ),
                ],
            },
        )

    if http_status not in (401, 403):
        return None

    message = (
        f"tapps-brain auth probe returned HTTP {http_status}: {detail or 'unauthorized'}. "
        "Memory operations cannot proceed."
    )
    return error_response(
        "tapps_session_start",
        "brain_auth_failed",
        message,
        extra={
            "http_status": http_status,
            "memory_status": memory_status,
            "elapsed_ms": elapsed_ms,
            "next_steps": [
                "Set TAPPS_BRAIN_AUTH_TOKEN in your environment or .mcp.json env block",
                (
                    "If running offline / without tapps-brain, set "
                    "memory.tolerate_brain_auth_failure: true in .tapps-mcp.yaml "
                    "to keep the degraded behavior"
                ),
            ],
        },
    )


async def tapps_session_start(
    project_root: str = "",
    quick: bool = False,
) -> dict[str, Any]:
    """REQUIRED as the FIRST call in every session. Returns server info
    (version, checkers, configuration, and project context).

    Args:
        project_root: Unused; reserved for future use. Server uses configured root.
        quick: When True, return minimal response using cached tool versions
            (no subprocess calls, no diagnostics, no memory GC). Target: < 1s.
    """
    from tapps_mcp.server import (
        _record_call,
        _record_execution,
        _with_nudges,
    )
    from tapps_mcp.tools import session_start_core as _ssc

    start = time.perf_counter_ns()
    try:
        from tapps_mcp.tools.checklist import CallTracker

        CallTracker.begin_session()
    except ImportError:
        pass
    _record_call("tapps_session_start")

    if quick:
        return await _session_start_quick(start, _record_execution, _with_nudges)

    settings = load_settings()
    (
        info,
        memory_status,
        hive_status,
        brain_bridge_health,
        timings,
    ) = await _ssc.collect_session_start_phases(settings)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_session_start", start)
    timings["total_ms"] = elapsed_ms

    path_mapping, container_warning = _ssc.detect_path_mapping()
    checklist_sid = _ssc.get_checklist_session_id()

    data = _ssc.build_session_start_data(
        settings,
        info,
        memory_status,
        hive_status,
        brain_bridge_health,
        checklist_sid,
        path_mapping,
        timings,
        _current_docs_provider(),
    )

    if container_warning:
        data["warnings"] = [container_warning]

    # Search-first phase: proactive lookup hints from pyproject.toml (TAP-475)
    search_first = _build_search_first(settings.project_root)
    if search_first is not None:
        data["search_first"] = search_first

    # TAP-1082: Hard-fail on tapps-brain auth probe 401/403 unless explicitly
    # tolerated. Audit (38 sessions, worst case 18 retries) shows agents do
    # not act on degraded:true buried inside memory_status — they retry, or
    # proceed without memory. Promoting the failure to a top-level error
    # with TAPPS_BRAIN_AUTH_TOKEN in next_steps gives the agent something
    # actionable.
    auth_failure_response = _detect_brain_auth_failure(settings, memory_status, elapsed_ms)
    if auth_failure_response is not None:
        return auth_failure_response

    resp = success_response("tapps_session_start", elapsed_ms, data)
    _ssc.attach_session_start_structured_output(resp, info)

    from tapps_mcp.server_helpers import (
        mark_session_initialized,
        write_session_start_marker,
    )

    mark_session_initialized(
        {
            "project_root": info["data"]["configuration"].get("project_root", ""),
            "quality_preset": info["data"]["configuration"].get("quality_preset", "standard"),
            "auto_initialized": False,
        }
    )
    # TAP-975: refresh sidecar so the UserPromptSubmit hook stays silent for
    # the next 30 minutes of prompts.
    write_session_start_marker(settings.project_root)

    return _with_nudges("tapps_session_start", resp, {})


async def _session_start_quick(
    start_ns: int,
    record_execution: Any,
    with_nudges: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Quick session start: cached tool versions, no diagnostics or memory GC.

    Loads tool versions from disk cache (no subprocess calls). Skips
    diagnostics, memory GC, and contradiction checks.
    """
    from tapps_mcp import __version__
    from tapps_mcp.server import _bootstrap_cache_dir, _cache_info_dict
    from tapps_mcp.tools import session_start_core as _ssc
    from tapps_mcp.tools.tool_detection import detect_installed_tools

    settings = load_settings()
    cache_dir, cache_fallback = _bootstrap_cache_dir(settings.project_root)
    installed = detect_installed_tools()

    elapsed_ms = (time.perf_counter_ns() - start_ns) // 1_000_000
    record_execution("tapps_session_start", start_ns)

    hive_status: dict[str, Any] = initial_session_hive_status()
    try:
        hive_status = await collect_session_hive_status(settings)
    except Exception:
        _logger.debug("hive_status_check_failed_quick", exc_info=True)

    checklist_sid_q = _ssc.get_checklist_session_id()

    data: dict[str, Any] = {
        "project_root": str(settings.project_root),
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
        "installed_checkers": [t.model_dump() for t in installed],
        "checker_environment": "mcp_server",
        "checker_environment_note": (
            "Checker availability reflects the MCP server process environment. "
            "Target project may have different tools installed."
        ),
        "docs_provider": _current_docs_provider(),
        "cache": _cache_info_dict(cache_dir, cache_fallback),
        "quick": True,
        "checklist_session_id": checklist_sid_q,
        "hive_status": hive_status,
        "recommended_next": (
            "Quick session started (diagnostics skipped). "
            "Call tapps_session_start() without quick=True for full diagnostics."
        ),
    }

    resp = success_response("tapps_session_start", elapsed_ms, data)
    _ssc.attach_quick_session_structured_output(resp, settings, installed)

    from tapps_mcp.server_helpers import (
        mark_session_initialized,
        write_session_start_marker,
    )

    mark_session_initialized(
        {
            "project_root": str(settings.project_root),
            "quality_preset": settings.quality_preset,
            "auto_initialized": False,
            "project_profile": None,
        }
    )
    # TAP-975: refresh sidecar in quick path too.
    write_session_start_marker(settings.project_root)

    return with_nudges("tapps_session_start", resp, {})


# ---------------------------------------------------------------------------
# tapps_init
# ---------------------------------------------------------------------------


async def tapps_init(
    create_handoff: bool = True,
    create_runlog: bool = True,
    create_agents_md: bool = True,
    create_tech_stack_md: bool = True,
    platform: str = "",
    verify_server: bool = True,
    install_missing_checkers: bool = False,
    warm_cache_from_tech_stack: bool = False,
    warm_expert_rag_from_tech_stack: bool = False,
    overwrite_platform_rules: bool = False,
    overwrite_agents_md: bool = False,
    overwrite_tech_stack_md: bool = False,
    agent_teams: bool = False,
    memory_capture: bool = False,
    memory_auto_capture: bool = False,
    memory_auto_recall: bool = False,
    destructive_guard: bool | None = None,
    linear_enforce_gate: bool | None = None,
    linear_enforce_cache_gate: str | None = None,
    install_git_hooks: bool | None = None,
    linear_sdlc: bool = False,
    linear_issue_prefix: str = "TAP",
    linear_team_id: str = "",
    linear_project_id: str = "",
    minimal: bool = False,
    dry_run: bool = False,
    verify_only: bool = False,
    llm_engagement_level: str | None = None,
    scaffold_experts: bool = False,
    include_karpathy: bool = True,
    mcp_config: bool = False,
    output_mode: str = "auto",
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    """Bootstrap TAPPS pipeline in the current project.

    Side effects: Writes files (AGENTS.md, TECH_STACK.md, platform rules, hooks,
    agents, skills). May create or merge ``.tapps-mcp.yaml`` on first run.
    See package docs for full argument reference.
    """
    from tapps_mcp.pipeline.init import bootstrap_pipeline
    from tapps_mcp.server import _record_call, _record_execution, _with_nudges
    from tapps_mcp.tools import pipeline_init_helpers as _pih

    start = time.perf_counter_ns()
    _record_call("tapps_init")

    cancelled = await _pih.maybe_elicit_init_confirmation(ctx, start, verify_only, dry_run)
    if cancelled is not None:
        return cancelled

    (
        _wizard,
        llm_engagement_level,
        platform,
        agent_teams,
        add_other_mcps_hint,
    ) = await _pih.run_init_wizard_if_needed(
        ctx,
        verify_only=verify_only,
        dry_run=dry_run,
        llm_engagement_level=llm_engagement_level,
        platform=platform,
        agent_teams=agent_teams,
    )

    settings = load_settings()
    dg = destructive_guard
    if dg is None:
        dg = getattr(settings, "destructive_guard", False)
    leg = linear_enforce_gate
    if leg is None:
        # TAP-981: engagement-aware default — true at high/medium, false at low.
        # Honors explicit overrides from .tapps-mcp.yaml or env.
        leg = settings.linear_enforce_gate_resolved()
    lcg = linear_enforce_cache_gate
    if lcg is None:
        # TAP-1224: engagement-aware default — "warn" at high/medium, "off" at low.
        lcg = settings.linear_enforce_cache_gate_resolved()
    igh = install_git_hooks
    if igh is None:
        # TAP-979: opt-in git pre-commit hook.
        igh = getattr(settings, "install_git_hooks", False)

    cfg = _pih.build_init_bootstrap_config(
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
        overwrite_tech_stack_md=overwrite_tech_stack_md,
        agent_teams=agent_teams,
        memory_capture=memory_capture,
        memory_auto_capture=memory_auto_capture,
        memory_auto_recall=memory_auto_recall,
        destructive_guard=dg,
        linear_enforce_gate=leg,
        linear_enforce_cache_gate=lcg,
        install_git_hooks=igh,
        linear_sdlc=linear_sdlc,
        linear_issue_prefix=linear_issue_prefix,
        linear_team_id=linear_team_id,
        linear_project_id=linear_project_id,
        minimal=minimal,
        dry_run=dry_run,
        verify_only=verify_only,
        llm_engagement_level=llm_engagement_level,
        scaffold_experts=scaffold_experts,
        include_karpathy=include_karpathy,
        settings=settings,
    )

    prev_write_mode = _pih.resolve_write_mode_env(output_mode)
    try:
        result = await asyncio.to_thread(
            bootstrap_pipeline,
            settings.project_root,
            config=cfg,
        )
    finally:
        _pih.restore_write_mode_env(prev_write_mode)

    _pih.maybe_write_mcp_config(result, settings, platform, mcp_config, dry_run)
    await _pih.emit_init_progress(ctx, result)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution(
        "tapps_init",
        start,
        status="success" if not result["errors"] else "failed",
    )

    _pih.enrich_init_result_hints(result, add_other_mcps_hint=add_other_mcps_hint)
    resp = success_response("tapps_init", elapsed_ms, result)
    resp["success"] = not result["errors"]
    return _with_nudges("tapps_init", resp)


# ---------------------------------------------------------------------------
# tapps_upgrade
# ---------------------------------------------------------------------------


async def tapps_upgrade(
    platform: str = "",
    force: bool = False,
    dry_run: bool = False,
    output_mode: str = "auto",
    mcp_only: bool = False,
    ctx: Context[Any, Any, Any] | None = None,
) -> dict[str, Any]:
    """Upgrade TappsMCP-generated files after a version update.

    Writes are scoped to tapps-managed files: the four ``tapps-*`` subagents,
    the ``tapps-*`` + ``linear-issue`` skills, and ``tapps-*`` hook scripts.
    Consumer-authored agents/skills/hooks with other names are preserved.
    ``AGENTS.md`` uses section-aware merge; ``.claude/settings.json`` hooks
    are merged by matcher (no entries removed). Creates a timestamped
    backup first under ``.tapps-mcp/backups/``.

    With ``dry_run=True``, returns a per-component breakdown plus a
    top-level ``dry_run_summary`` with:

    - ``verdict``: ``"safe-to-run"`` (only tapps-managed writes) or
      ``"review-recommended"`` (touches user-editable files like
      ``CLAUDE.md`` or ``.claude/settings.json`` merge)
    - ``managed_file_count`` / ``preserved_file_count``
    - ``preserved_files``: exact custom files the upgrade would leave alone
    - ``review_recommended_for``: components requiring diff review
    - ``skipped_components``: artifacts opted out via ``upgrade_skip_files``

    Per-component entries for ``agents``/``skills``/``hooks`` are dicts with
    ``action``, ``managed_files``/``managed_skills``, and
    ``preserved_files``/``preserved_skills`` so consumers can audit exactly
    which paths would change.
    """
    from tapps_mcp.pipeline.upgrade import upgrade_pipeline
    from tapps_mcp.server import _record_call, _record_execution, _with_nudges
    from tapps_mcp.tools import pipeline_init_helpers as _pih

    start = time.perf_counter_ns()
    _record_call("tapps_upgrade")

    settings = load_settings()

    if not dry_run:
        await emit_ctx_info(ctx, "Creating backup...")

    prev_write_mode = _pih.resolve_write_mode_env(output_mode)
    try:
        result = upgrade_pipeline(
            settings.project_root,
            platform=platform,
            force=force,
            dry_run=dry_run,
            mcp_only=mcp_only,
        )
    finally:
        _pih.restore_write_mode_env(prev_write_mode)

    if not dry_run:
        await _pih.emit_upgrade_progress(ctx, result)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution(
        "tapps_upgrade",
        start,
        status="success" if result.get("success") else "failed",
    )

    resp = success_response("tapps_upgrade", elapsed_ms, result)
    return _with_nudges("tapps_upgrade", resp)


# ---------------------------------------------------------------------------
# tapps_set_engagement_level
# ---------------------------------------------------------------------------


def tapps_set_engagement_level(level: str) -> dict[str, Any]:
    """Set the LLM engagement level (high / medium / low) for the project.

    Side effects: Writes ``llm_engagement_level`` to ``.tapps-mcp.yaml``. Run
    ``tapps_init(overwrite_agents_md=True)`` afterward to regenerate AGENTS.md.
    """
    import yaml

    from tapps_core.common.file_operations import WriteMode, detect_write_mode
    from tapps_core.security.path_validator import PathValidator
    from tapps_mcp.server import _record_call, _record_execution, _with_nudges
    from tapps_mcp.tools import engagement_level as _el

    start = time.perf_counter_ns()
    _record_call("tapps_set_engagement_level")

    valid = ("high", "medium", "low")
    if level not in valid:
        _record_execution("tapps_set_engagement_level", start, status="failed")
        return error_response(
            "tapps_set_engagement_level",
            "invalid_level",
            f"Invalid level {level!r}. Use one of: {', '.join(valid)}",
        )

    settings = load_settings()
    root = Path(settings.project_root)
    validator = PathValidator(root)
    config_path = validator.validate_write_path(".tapps-mcp.yaml")

    loaded = _el.read_engagement_yaml(config_path)
    if isinstance(loaded, str):
        _record_execution("tapps_set_engagement_level", start, status="failed")
        return error_response("tapps_set_engagement_level", "config_read_error", loaded)

    data = loaded
    data["llm_engagement_level"] = level

    write_mode = detect_write_mode(root)
    yaml_content = yaml.dump(data, default_flow_style=False, sort_keys=False)

    if write_mode == WriteMode.DIRECT_WRITE:
        err = _el.write_engagement_yaml(config_path, yaml_content)
        if err is not None:
            _record_execution("tapps_set_engagement_level", start, status="failed")
            return error_response("tapps_set_engagement_level", "config_write_error", err)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_set_engagement_level", start)

    next_step = (
        "Run tapps_init with overwrite_agents_md=True (and platform if needed) "
        "to regenerate AGENTS.md and platform rules with the new level."
    )
    msg = f"Engagement level set to {level!r}. {next_step}"
    result_data: dict[str, Any] = {"level": level, "message": msg}

    if write_mode == WriteMode.CONTENT_RETURN:
        result_data["content_return"] = True
        result_data["file_manifest"] = _el.engagement_manifest(yaml_content, level, settings)

    resp = success_response(
        "tapps_set_engagement_level",
        elapsed_ms,
        result_data,
    )
    return _with_nudges("tapps_set_engagement_level", resp)


# ---------------------------------------------------------------------------
# tapps_doctor
# ---------------------------------------------------------------------------


def tapps_doctor(
    project_root: str = "",
    quick: bool = False,
) -> dict[str, Any]:
    """Diagnose TappsMCP configuration and connectivity."""
    from tapps_mcp.distribution.doctor import run_doctor_structured
    from tapps_mcp.server import _record_call, _record_execution, _with_nudges

    start = time.perf_counter_ns()
    _record_call("tapps_doctor")

    settings = load_settings()
    root = project_root or str(settings.project_root)

    result = run_doctor_structured(project_root=root, quick=quick)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_doctor", start)

    resp = success_response("tapps_doctor", elapsed_ms, result)
    return _with_nudges("tapps_doctor", resp)


# ---------------------------------------------------------------------------
# tapps_pipeline
# ---------------------------------------------------------------------------


async def tapps_pipeline(
    file_paths: str = "",
    task_type: str = "feature",
    preset: str = "standard",
    skip_session_start: bool = False,
) -> dict[str, Any]:
    """One-call orchestrator for the full TappsMCP quality pipeline (STORY-101.2)."""
    from tapps_mcp.server import _record_call
    from tapps_mcp.tools import pipeline_orchestrator as _po

    start = time.perf_counter_ns()
    _record_call("tapps_pipeline")

    if not file_paths.strip():
        return error_response(
            "tapps_pipeline",
            "NO_FILE_PATHS",
            "tapps_pipeline requires file_paths — pass comma-separated paths.",
        )

    stages: list[dict[str, Any]] = []
    pipeline_passed = True

    session_stage = await _po.pipeline_session_start_stage(skip_session_start)
    if session_stage is not None:
        stages.append(session_stage)
        if not session_stage["success"]:
            pipeline_passed = False

    qc_stage, qc_passed, short_circuit = await _po.pipeline_quick_check_stage(file_paths, preset)
    stages.append(qc_stage)
    if not qc_passed:
        pipeline_passed = False

    vc_stage, vc_passed = await _po.pipeline_validate_stage(file_paths, preset, short_circuit)
    stages.append(vc_stage)
    if not vc_passed:
        pipeline_passed = False

    cl_stage, cl_passed = await _po.pipeline_checklist_stage(task_type)
    stages.append(cl_stage)
    if not cl_passed:
        pipeline_passed = False

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    data: dict[str, Any] = {
        "pipeline_passed": pipeline_passed,
        "short_circuit": short_circuit,
        "stages": stages,
        "task_type": task_type,
        "file_paths": file_paths,
    }
    return success_response("tapps_pipeline", elapsed_ms, data)


# ---------------------------------------------------------------------------
# MCP tool registration (Epic 79.1: conditional)
# ---------------------------------------------------------------------------


def register(mcp_instance: FastMCP, allowed_tools: frozenset[str]) -> None:
    """Register pipeline/validation tools on *mcp_instance*."""
    if "tapps_validate_changed" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_validate_changed)
    if "tapps_session_start" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(tapps_session_start)
    if "tapps_init" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(tapps_init)
    if "tapps_set_engagement_level" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(
            tapps_set_engagement_level
        )
    if "tapps_upgrade" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT)(tapps_upgrade)
    if "tapps_doctor" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_doctor)
    if "tapps_pipeline" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_pipeline)
    if "tapps_decompose" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_decompose)

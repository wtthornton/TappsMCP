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
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import structlog
from mcp.types import ToolAnnotations

from tapps_core.config.settings import load_settings
from tapps_mcp.common.output_schemas import TappsSessionStartResponse
from tapps_mcp.mcp_register import register_tool
from tapps_mcp.server_helpers import (
    collect_session_hive_status,
    error_response,
    initial_session_hive_status,
    success_response,
)

# ---------------------------------------------------------------------------
# Re-exports from split modules (backward compatibility for tests)
# ---------------------------------------------------------------------------
from tapps_mcp.tools.admin_tools import tapps_doctor as tapps_doctor
from tapps_mcp.tools.admin_tools import tapps_init as tapps_init
from tapps_mcp.tools.admin_tools import (
    tapps_set_engagement_level as tapps_set_engagement_level,
)
from tapps_mcp.tools.admin_tools import tapps_upgrade as tapps_upgrade
from tapps_mcp.tools.decompose_helpers import (
    TaskUnit,
    _classify_model_tier,
    _classify_risk,
    _decompose_task,
    _split_task_into_phrases,
    _summarize_quick_check,
    tapps_decompose,
)
from tapps_mcp.tools.handoff_tools import (
    _append_handoff_subresult_warnings as _append_handoff_subresult_warnings,
)
from tapps_mcp.tools.handoff_tools import tapps_handoff_save as tapps_handoff_save
from tapps_mcp.tools.handoff_tools import tapps_pipeline as tapps_pipeline
from tapps_mcp.tools.handoff_tools import tapps_session_end as tapps_session_end
from tapps_mcp.tools.pipeline_tool_sets import SOURCE_FILE_SUFFIXES
from tapps_mcp.tools.session_start_auth import (
    _classify_brain_auth_token as _classify_brain_auth_token,
)
from tapps_mcp.tools.session_start_auth import (
    _detect_brain_auth_failure as _detect_brain_auth_failure,
)
from tapps_mcp.tools.session_start_helpers import (
    _DOCS_COVERED,
    _build_search_first,
    _cleanup_legacy_learning_dir,
    _collect_brain_bridge_health,
    _collect_memory_status,
    _enrich_memory_profile_status,
    _enrich_memory_status_hints,
    _maybe_auto_gc,
    _maybe_consolidation_scan,
    _maybe_validate_memories,
    _normalise_dep,
    _process_session_capture,
    _schedule_background_maintenance,
    call_memory_index_session_start,
    maybe_schedule_quick_maintenance,
)

# TAP-7018: the retired-registration pointer, and the logic that picks it
# vs. the real tapps_session_start, live in session_start_helpers.py, not
# here, so the already oversized register() below stays a single ``if``.
from tapps_mcp.tools.session_start_helpers import (
    resolve_session_start_impl as resolve_session_start_impl,
)
from tapps_mcp.tools.session_start_helpers import (
    tapps_session_start_pointer as tapps_session_start_pointer,
)
from tapps_mcp.tools.validate_changed import (
    _AUTO_DETECT_BUDGET_S as _AUTO_DETECT_BUDGET_S,
)
from tapps_mcp.tools.validate_changed import (
    _PROGRESS_HEARTBEAT_INTERVAL as _PROGRESS_HEARTBEAT_INTERVAL,
)
from tapps_mcp.tools.validate_changed import (
    _VALIDATE_CONCURRENCY as _VALIDATE_CONCURRENCY,
)
from tapps_mcp.tools.validate_changed import (
    _VALIDATE_OK_MARKER as _VALIDATE_OK_MARKER,
)
from tapps_mcp.tools.validate_changed import (
    _VALIDATION_PROGRESS_FILE as _VALIDATION_PROGRESS_FILE,
)
from tapps_mcp.tools.validate_changed import (
    _cache_hit_as_file_result as _cache_hit_as_file_result,
)
from tapps_mcp.tools.validate_changed import (
    _collect_results as _collect_results,
)
from tapps_mcp.tools.validate_changed import (
    _discover_changed_files as _discover_changed_files,
)
from tapps_mcp.tools.validate_changed import (
    _emit_file_info as _emit_file_info,
)
from tapps_mcp.tools.validate_changed import (
    _maybe_run_wizard as _maybe_run_wizard,
)
from tapps_mcp.tools.validate_changed import (
    _maybe_warm_dependency_cache as _maybe_warm_dependency_cache,
)
from tapps_mcp.tools.validate_changed import (
    _partition_by_cache as _partition_by_cache,
)
from tapps_mcp.tools.validate_changed import (
    _ProgressTracker as _ProgressTracker,
)
from tapps_mcp.tools.validate_changed import (
    _report_initial_progress as _report_initial_progress,
)
from tapps_mcp.tools.validate_changed import (
    _start_progress_reporting as _start_progress_reporting,
)
from tapps_mcp.tools.validate_changed import (
    _validate_progress_heartbeat as _validate_progress_heartbeat,
)
from tapps_mcp.tools.validate_changed import (
    _validate_single_file as _validate_single_file,
)
from tapps_mcp.tools.validate_changed import (
    _warm_dependency_cache as _warm_dependency_cache,
)
from tapps_mcp.tools.validate_changed import (
    _write_validate_ok_marker as _write_validate_ok_marker,
)
from tapps_mcp.tools.validate_changed import (
    tapps_validate_changed as tapps_validate_changed,
)
from tapps_mcp.tools.validate_changed_output import (
    _SEVERITY_RANK as _SEVERITY_RANK,
)
from tapps_mcp.tools.validate_changed_output import (
    _build_per_file_results as _build_per_file_results,
)
from tapps_mcp.tools.validate_changed_output import (
    _build_structured_validation_output as _build_structured_validation_output,
)
from tapps_mcp.tools.validate_changed_output import (
    _build_validation_summary as _build_validation_summary,
)
from tapps_mcp.tools.validate_changed_output import (
    _compute_affected_tests as _compute_affected_tests,
)
from tapps_mcp.tools.validate_changed_output import (
    _compute_impact_analysis as _compute_impact_analysis,
)
from tapps_mcp.tools.validate_changed_output import (
    _handle_no_changed_files as _handle_no_changed_files,
)
from tapps_mcp.tools.validate_changed_output import (
    _resolve_security_depth as _resolve_security_depth,
)
from tapps_mcp.tools.validate_changed_output import (
    attach_affected_tests as attach_affected_tests,
)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

__all__ = [
    "SESSION_START_QUICK_RECOMMENDED_NEXT",
    "_AUTO_DETECT_BUDGET_S",
    "_DOCS_COVERED",
    "_PROGRESS_HEARTBEAT_INTERVAL",
    "_SEVERITY_RANK",
    "_VALIDATE_CONCURRENCY",
    "_VALIDATE_OK_MARKER",
    "_VALIDATION_PROGRESS_FILE",
    # Re-exports for backward compatibility
    "TaskUnit",
    "_ProgressTracker",
    "_background_tasks",
    "_build_per_file_results",
    "_build_search_first",
    "_build_structured_validation_output",
    "_build_validation_summary",
    "_cache_hit_as_file_result",
    "_classify_model_tier",
    "_classify_risk",
    "_cleanup_legacy_learning_dir",
    "_collect_brain_bridge_health",
    "_collect_memory_status",
    "_collect_results",
    "_compute_affected_tests",
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
    "_reset_background_tasks",
    "_reset_session_consolidation_flag",
    "_reset_session_doc_validation_flag",
    "_reset_session_gc_flag",
    "_reset_session_maintenance_flag",
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
    "attach_affected_tests",
    "call_memory_index_session_start",
    "error_response",
    "load_settings",
    "maybe_schedule_quick_maintenance",
    "register",
    "resolve_session_start_impl",
    "tapps_decompose",
    "tapps_doctor",
    "tapps_handoff_save",
    "tapps_init",
    "tapps_pipeline",
    "tapps_session_end",
    "tapps_session_start",
    "tapps_session_start_pointer",
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
    # TAP-6638: guards _schedule_background_maintenance itself (not just the
    # individual ops it calls) so a quick=True call and a quick=False call in
    # the same session schedule the fire-and-forget maintenance task once.
    maintenance_scheduled: bool = False
    # TAP-2005: ISO-8601 timestamp of the most recent session start; consumed
    # by tapps_session_end to scope flywheel_process to this session's events.
    session_start_iso: str = ""


_session_state = _SessionFlags()
# Guards the async check-and-set in _maybe_validate_memories to prevent
# double-execution when concurrent session_start calls spawn background tasks.
_state_lock = asyncio.Lock()


def _reset_state_lock() -> None:
    """Rebind ``_state_lock`` to a fresh lock (for testing).

    ``asyncio.Lock`` binds its waiters to whichever event loop first awaits it.
    Production runs one loop for the process lifetime, so a module-level lock is
    correct there; pytest-asyncio gives every test its own loop. If a test's
    loop is torn down while a task holds the lock -- a cancelled background
    task, a timed-out coroutine -- the lock stays held and its waiters belong to
    a loop that will never run again. Every later ``async with _state_lock``
    then blocks on a future nothing can resolve: the process sits in
    ``EpollSelector.select(timeout=-1)`` until pytest-timeout kills it, and
    whichever test drew that slot in the shuffle is the one that appears to
    hang (TAP-5841). Same reasoning as :func:`_reset_background_tasks`.
    """
    global _state_lock
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


def _reset_session_maintenance_flag() -> None:
    """Reset the background-maintenance-scheduled flag (for testing)."""
    _session_state.maintenance_scheduled = False


def _reset_session_state() -> None:
    """Reset all session state flags (for testing)."""
    _session_state.gc_done = False
    _session_state.consolidation_done = False
    _session_state.doc_validation_done = False
    _session_state.maintenance_scheduled = False
    _session_state.session_start_iso = ""


# Prevent garbage collection of fire-and-forget background tasks.
# Without strong references, asyncio tasks may be collected before completion.
_background_tasks: set[asyncio.Task[Any]] = set()


def _reset_background_tasks() -> None:
    """Discard all tracked background tasks (for testing).

    In production the set drains via done-callbacks; in tests the
    function-scoped event loop cancels any remaining tasks when it closes.
    Clearing the set here prevents stale Task objects from a previous test's
    event loop leaking into the next test's loop — a known source of false
    "task attached to a different loop" warnings and timing-sensitive flakiness
    (TAP-2101).
    """
    _background_tasks.clear()


# TAP-1379: Per-process cache of tapps_session_start responses keyed by the
# MetricsHub _SESSION_ID (process-lifetime UUID) + project root + quick.
# Shared HTTP fleet (ADR-0024) serves many Cursor windows from one process;
# the key MUST include X-Tapps-Project-Root so project A never gets project B's
# cached bootstrap. Same session_id + root + quick + not force => cached hit.
# Audit (2026-05-04) showed agents calling tapps_session_start ~23 times per
# Claude session; a defensive re-call is cheap, but a full re-init burns
# ~270ms on subprocess + Brain probes.
_SESSION_START_CACHE: dict[tuple[str, bool, str], dict[str, Any]] = {}


def _session_start_cache_root() -> str:
    """Resolved project root for the current request (fleet) or process (stdio)."""
    import os

    from tapps_core.http.request_context import http_request_root_override

    # A workspace-free fleet request keys on the shared sentinel rather than
    # the fleet's own CWD, which is nobody's project (TAP-6062).
    request_root, _ = http_request_root_override(None)
    if request_root is not None:
        return str(request_root.resolve())
    env_root = os.environ.get("TAPPS_MCP_PROJECT_ROOT", "").strip()
    if env_root:
        return str(Path(env_root).expanduser().resolve())
    return str(Path.cwd().resolve())


def _session_start_cache_key(quick: bool) -> tuple[str, bool, str]:
    """Build a cache key: process session id + quick flag + project root."""
    from tapps_core.metrics.collector import _SESSION_ID

    return (_SESSION_ID, quick, _session_start_cache_root())


def _reset_session_start_cache() -> None:
    """Clear the tapps_session_start memoization cache (for testing)."""
    _SESSION_START_CACHE.clear()


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

# TAP-1986: defer_loading meta for non-daily-driver pipeline tools.
# tapps_session_start and tapps_validate_changed are daily drivers (eager).
_META_DEFERRED: dict[str, Any] = {"defer_loading": True}


# ---------------------------------------------------------------------------
# tapps_session_start
# ---------------------------------------------------------------------------
# Implementation helpers live in ``tapps_mcp.tools.session_start_core``.
# ``_classify_brain_auth_token`` / ``_detect_brain_auth_failure`` moved to
# ``tools/session_start_auth.py`` (TAP-6881), re-exported above.


def _prepend_next_step(resp: dict[str, Any], step: str) -> None:
    """Prepend a next-step string to ``resp.data.next_steps`` (creating the list).

    Used to inject high-priority warnings (e.g. degraded checker availability)
    after ``_with_nudges`` has populated next_steps from the global ranker.
    """
    data = resp.get("data")
    if not isinstance(data, dict):
        return
    existing = data.get("next_steps")
    if isinstance(existing, list):
        if step in existing:
            existing.remove(step)
        data["next_steps"] = [step, *existing]
    else:
        data["next_steps"] = [step]


async def tapps_session_start(
    project_root: str = "",
    quick: bool = True,
    force: bool = False,
) -> TappsSessionStartResponse:
    """Bootstraps project context: server info, installed checkers, cache
    health, and the checklist session id for the current task.

    Call this as the first MCP tool in every session — agent reasoning,
    library lookups, and quality gates run in degraded mode until this
    completes. The response caches per server process (TAP-1379), so
    repeat calls return instantly with ``cached: true`` and do not churn
    the checklist session id.

    Args:
        project_root: Reserved override (stdio / remote hosts). On the
            shared HTTP fleet, prefer ``X-Tapps-Project-Root``; that header
            scopes the memoization cache and ``load_settings()`` root.
        quick: Default ``True`` (TAP-6434) — the compact bootstrap payload,
            from cached checker versions, without subprocess probes or
            diagnostics. Pass ``quick=False`` for the full diagnostic
            payload (brain health, memory status, install drift, call
            graph, usage gaps); ``tapps_doctor`` covers the same ground.
        force: Bypass the per-process memoization cache and re-run the
            bootstrap. Default ``False``. Use after restarting the
            brain, editing ``.tapps-mcp.yaml``, or installing a new
            checker — otherwise the cached response is what you want.
    """
    from tapps_mcp.server import (
        _record_call,
        _record_execution,
        _with_nudges,
    )
    from tapps_mcp.tools import session_start_core as _ssc
    from tapps_mcp.tools import session_start_enrichment as _sse

    start = time.perf_counter_ns()

    # TAP-1379: short-circuit on repeat calls within the same MCP process.
    # Audit showed ~23 redundant calls per Claude session; the cached path
    # returns instantly with a `cached: true` marker so the agent can tell
    # this was a no-op. Done BEFORE begin_session() so we don't churn the
    # checklist session id on a cached hit.
    if not force:
        cached = _SESSION_START_CACHE.get(_session_start_cache_key(quick))
        if cached is not None:
            _record_call("tapps_session_start")
            elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
            _record_execution("tapps_session_start", start)
            resp = dict(cached)
            data = dict(cached.get("data") or {})
            data["cached"] = True
            data["elapsed_ms"] = elapsed_ms
            resp["data"] = data
            return cast("TappsSessionStartResponse", resp)

    try:
        from tapps_mcp.tools.checklist import CallTracker

        CallTracker.begin_session()
    except ImportError:
        pass
    _record_call("tapps_session_start")

    if quick:
        resp = await _session_start_quick(start, _record_execution, _with_nudges)
        _SESSION_START_CACHE[_session_start_cache_key(True)] = resp
        return cast("TappsSessionStartResponse", resp)

    settings = load_settings()

    # TAP-1928: file-based sentinel short-circuit for sub-agent reuse.
    # Distinct from the in-process _SESSION_START_CACHE (TAP-1379): the sentinel
    # persists across MCP server restarts so sub-agents (fresh processes)
    # skip redundant checker / brain-health / memory-GC phases when the primary
    # agent bootstrapped within the last hour.  force=True bypasses both caches.
    if not force:
        sentinel_age = _ssc.read_session_sentinel(settings.project_root)
        if sentinel_age is not None:
            _record_execution("tapps_session_start", start)
            elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
            data = {
                "cached": True,
                "sentinel_age_s": sentinel_age,
                "elapsed_ms": elapsed_ms,
            }
            resp = success_response("tapps_session_start", elapsed_ms, data)
            resp = _with_nudges("tapps_session_start", resp, {})
            return cast("TappsSessionStartResponse", resp)

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

    # Best-effort enrichment phases (TAP-475/1331/114/3578/3929) --
    # tools/session_start_enrichment.py. _build_search_first is passed in
    # (rather than imported there) because it's patched via
    # patch("tapps_mcp.server_pipeline_tools._build_search_first") in tests.
    _sse.enrich_search_first(data, settings.project_root, _build_search_first)
    _sse.enrich_repo_orientation(data, settings.project_root)
    _sse.enrich_call_graph(data, settings.project_root)

    # TAP-2017 / TAP-6638: Detect and surface compaction rehydration data when
    # the PreCompact hook indexed the prior session in brain. Routed through
    # the shared helper (also used by the quick path) instead of a second
    # inline copy of the same marker-check + best-effort-swallow logic.
    await _ssc.attach_compaction_rehydration(Path(settings.project_root), data)

    _sse.enrich_usage_gaps(data, settings.project_root)
    _sse.enrich_recommended_workflows(data, settings)

    from tapps_mcp.tools.session_start_helpers import attach_cli_fallback

    attach_cli_fallback(data)

    # TAP-1082: Hard-fail on tapps-brain auth probe 401/403 unless explicitly
    # tolerated. Audit (38 sessions, worst case 18 retries) shows agents do
    # not act on degraded:true buried inside memory_status — they retry, or
    # proceed without memory. Promoting the failure to a top-level error
    # with TAPPS_BRAIN_AUTH_TOKEN in next_steps gives the agent something
    # actionable.
    auth_failure_response = _detect_brain_auth_failure(settings, memory_status, elapsed_ms)
    if auth_failure_response is not None:
        return cast("TappsSessionStartResponse", auth_failure_response)

    # TAP-1414: Surface ruff/mypy missing on Python projects as a loud warning.
    degraded_checkers, degraded_warning = _ssc.compute_python_degraded_checkers(
        Path(settings.project_root), data["installed_checkers"]
    )
    if degraded_checkers:
        data["degraded_checkers"] = degraded_checkers

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
    # TAP-2005: record session start time so tapps_session_end can scope
    # flywheel_process to this session's events.
    _session_state.session_start_iso = datetime.now(UTC).isoformat()
    from tapps_mcp.tools.session_end_helpers import persist_session_start_iso

    persist_session_start_iso(Path(settings.project_root), _session_state.session_start_iso)
    # TAP-975: refresh sidecar so the UserPromptSubmit hook stays silent for
    # the next 30 minutes of prompts.
    write_session_start_marker(settings.project_root)
    # TAP-1928: write the file-based sentinel so subsequent sub-agent calls
    # can skip the full bootstrap for up to SENTINEL_TTL_S seconds.
    _ssc.write_session_sentinel(settings.project_root)

    nudge_ctx: dict[str, Any] = {}
    call_graph_block = data.get("call_graph")
    if isinstance(call_graph_block, dict):
        if call_graph_block.get("ready"):
            nudge_ctx["call_graph_ready"] = True
        elif call_graph_block.get("status") == "missing":
            nudge_ctx["call_graph_missing"] = True
        elif call_graph_block.get("stale"):
            nudge_ctx["call_graph_stale"] = True

    diagnostics_block = data.get("diagnostics")
    if isinstance(diagnostics_block, dict):
        install_drift_block = diagnostics_block.get("install_drift")
        if isinstance(install_drift_block, dict) and install_drift_block.get("drift_detected"):
            hint = install_drift_block.get("remediation_hint") or ""
            nudge_ctx["install_drift_detected"] = True
            nudge_ctx["install_drift_hint"] = hint

    resp = _with_nudges("tapps_session_start", resp, nudge_ctx)
    if degraded_warning:
        _prepend_next_step(resp, degraded_warning)
    install_drift_hint = nudge_ctx.get("install_drift_hint")
    if isinstance(install_drift_hint, str) and install_drift_hint:
        _prepend_next_step(resp, f"Install drift: {install_drift_hint}")
    # TAP-1379: memoize the full response so subsequent same-process calls
    # (without force=True) return instantly from cache.
    _SESSION_START_CACHE[_session_start_cache_key(False)] = resp
    return cast("TappsSessionStartResponse", resp)


# TAP-7019: conditional on what the turn actually touches, not a blanket
# "always do this" -- a turn that edits only non-scorable files (docs,
# shell, config) never triggers the middle two calls. Module-level so tests
# can assert on it directly instead of scraping the response dict.
#
# TAP-7019 (round 2): the suffix list is DERIVED from SOURCE_FILE_SUFFIXES,
# never hand-copied -- a prior version hardcoded ".py/.ts/.go/.rs", silently
# dropping 6 of the 10 authoritative suffixes (.pyi/.tsx/.js/.jsx/.mjs/.cjs),
# so e.g. an app.tsx-only turn was told the obligation didn't apply while
# the gate flagged it anyway.
_SCORABLE_SUFFIX_PHRASE = "/".join(SOURCE_FILE_SUFFIXES)
SESSION_START_QUICK_RECOMMENDED_NEXT = (
    "Session started. Next: tapps_lookup_docs before using a library API. "
    f"If you edit a scorable source file ({_SCORABLE_SUFFIX_PHRASE}), run "
    "tapps_quick_check after that edit, then tapps_validate_changed + "
    "tapps_checklist before declaring done. Run tapps_doctor() for diagnostics."
)


async def _session_start_quick(
    start_ns: int,
    record_execution: Any,
    with_nudges: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Quick session start: cached tool versions, no diagnostics or memory GC.

    Loads tool versions from disk cache (no subprocess calls). Skips
    diagnostics, memory GC, and contradiction checks.

    TAP-6434 made this the default payload, so it also takes the two
    lifecycle side effects nothing else performs (see ``session_start_core``).
    It deliberately does NOT write the TAP-1928 sentinel: that file means "a
    full bootstrap ran recently", so writing it here would short-circuit a
    later ``quick=False`` call into a near-empty cached response.
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
        "recommended_next": SESSION_START_QUICK_RECOMMENDED_NEXT,
    }

    await _ssc.attach_compaction_rehydration(Path(settings.project_root), data)
    maybe_schedule_quick_maintenance(settings)

    # TAP-1414: Surface ruff/mypy missing on Python projects as a loud warning.
    degraded_checkers, degraded_warning = _ssc.compute_python_degraded_checkers(
        Path(settings.project_root), installed
    )
    if degraded_checkers:
        data["degraded_checkers"] = degraded_checkers

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
    _session_state.session_start_iso = _ssc.record_session_start_iso(Path(settings.project_root))

    resp = with_nudges("tapps_session_start", resp, {})
    if degraded_warning:
        _prepend_next_step(resp, degraded_warning)
    return resp


# ---------------------------------------------------------------------------
# tapps_init -- moved to tools/admin_tools.py (TAP-6881), re-exported above.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# tapps_upgrade, tapps_set_engagement_level, tapps_doctor -- moved to
# tools/admin_tools.py (TAP-6881), re-exported above.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# tapps_pipeline, tapps_handoff_save, tapps_session_end -- moved to
# tools/handoff_tools.py (TAP-6881), re-exported above.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# MCP tool registration (Epic 79.1: conditional)
# ---------------------------------------------------------------------------


def register(
    mcp_instance: FastMCP,
    allowed_tools: frozenset[str],
    *,
    tool_preset: str | None = None,
) -> None:
    """Register pipeline/validation tools on *mcp_instance*.

    TAP-1986: tapps_session_start and tapps_validate_changed are eager daily
    drivers. All other pipeline tools carry defer_loading=True.

    Args:
        mcp_instance: The FastMCP server to register tools on.
        allowed_tools: Tool names permitted for this server process (Epic 79.1).
        tool_preset: The raw ``settings.tool_preset`` string (e.g.
            ``"nlt-memory"``). When it names a retired ``tapps_session_start``
            registration (TAP-7018) and the real tool is not in
            *allowed_tools*, :func:`tapps_session_start_pointer` is
            registered under the same name instead, so the name still
            resolves to something rather than 404-ing.
    """
    if "tapps_validate_changed" in allowed_tools:
        register_tool(mcp_instance, tapps_validate_changed, annotations=_ANNOTATIONS_READ_ONLY)
    session_start_impl = resolve_session_start_impl(allowed_tools, tool_preset)
    if session_start_impl is not None:
        register_tool(
            mcp_instance,
            session_start_impl,
            annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT,
            name="tapps_session_start",
        )
    if "tapps_session_end" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_session_end,
            annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT,
            meta=_META_DEFERRED,
        )
    if "tapps_handoff_save" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_handoff_save,
            annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT,
            meta=_META_DEFERRED,
        )
    if "tapps_init" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_init,
            annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT,
            meta=_META_DEFERRED,
        )
    if "tapps_set_engagement_level" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_set_engagement_level,
            annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT,
            meta=_META_DEFERRED,
        )
    if "tapps_upgrade" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_upgrade,
            annotations=_ANNOTATIONS_SIDE_EFFECT_IDEMPOTENT,
            meta=_META_DEFERRED,
        )
    if "tapps_doctor" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_doctor,
            annotations=_ANNOTATIONS_READ_ONLY,
            meta=_META_DEFERRED,
        )
    if "tapps_pipeline" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_pipeline,
            annotations=_ANNOTATIONS_READ_ONLY,
            meta=_META_DEFERRED,
        )
    if "tapps_decompose" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_decompose,
            annotations=_ANNOTATIONS_READ_ONLY,
            meta=_META_DEFERRED,
        )
    if "tapps_domain_playbook" in allowed_tools:
        from tapps_mcp.tools.domain_playbook import tapps_domain_playbook

        register_tool(
            mcp_instance,
            tapps_domain_playbook,
            annotations=_ANNOTATIONS_READ_ONLY,
            meta=_META_DEFERRED,
        )

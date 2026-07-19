"""Metrics, dashboard, feedback, and research tool handlers for TappsMCP.

Functions are defined at module level (importable for tests) and
registered on the ``mcp`` instance via :func:`register`.
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Any

from mcp.types import ToolAnnotations

from tapps_mcp.mcp_register import register_tool
from tapps_mcp.server_helpers import (
    error_response,
    success_response,
)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from tapps_core.metrics.collector import MetricsHub

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

_ANNOTATIONS_SIDE_EFFECT = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)

# TAP-1986: all metrics tools are deferred (not daily drivers).
_META_DEFERRED: dict[str, Any] = {"defer_loading": True}


def _sanitize_param(value: str, max_len: int = 100) -> str:
    """Strip control characters and truncate a parameter value."""
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "", value).strip()
    return cleaned[:max_len]


_PERIOD_DAYS: dict[str, int] = {"1d": 1, "7d": 7, "30d": 30}


def _is_docs_stats_tool(tool_name: str) -> bool:
    from tapps_core.metrics.dashboard import is_docs_tool

    return is_docs_tool(tool_name)


def _session_stats(
    hub: MetricsHub,
    tool_name: str | None,
) -> tuple[Any, list[dict[str, Any]]]:
    """Compute stats from in-memory session data."""
    from tapps_core.metrics.execution_metrics import ToolCallMetricsCollector

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
        breakdowns.append(
            {
                "tool_name": tname,
                "call_count": ts.total_calls,
                "success_rate": ts.success_rate,
                "avg_duration_ms": ts.avg_duration_ms,
                "p95_duration_ms": ts.p95_duration_ms,
            }
        )
    return summary, breakdowns


def _period_stats(
    hub: MetricsHub,
    tool_name: str | None,
    period: str,
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


async def tapps_dashboard(
    output_format: str = "json",
    time_range: str = "7d",
    sections: list[str] | None = None,
) -> dict[str, Any]:
    """Renders a multi-section TappsMCP metrics dashboard: tool usage, gate
    pass rates, expert effectiveness, cache hit rates, quality trends,
    and alerts.

    Call this for a periodic health review of the TAPPS pipeline ("how
    is the project trending?", "which tools are slow?") — typically once
    per week or before a release. For at-a-glance per-tool counts use
    ``tapps_stats``; for a triage of one specific failure mode use
    ``tapps_doctor``. The ``"otel"`` output format emits an OpenTelemetry
    trace bundle of the last 100 executions for shipping to a tracing
    backend.

    Args:
        output_format: ``"json"`` (default, machine-readable),
            ``"markdown"`` (human review), ``"html"`` (standalone web
            view with charts), or ``"otel"`` (OpenTelemetry trace
            export of the last 100 executions).
        time_range: Aggregation window: ``"1d"``, ``"7d"`` (default),
            ``"30d"``, or ``"90d"``.
        sections: Sections to include. Default ``None`` returns all
            sections. Options: ``"summary"``, ``"tool_metrics"``,
            ``"docs_metrics"``, ``"session_funnel"``, ``"scoring_trends"``,
            ``"expert_metrics"``, ``"cache_metrics"``,
            ``"quality_distribution"``, ``"alerts"``,
            ``"business_metrics"``, ``"recommendations"``.
    """
    from tapps_mcp.server import _get_metrics_hub, _record_call, _record_execution, _with_nudges

    start = time.perf_counter_ns()
    _record_call("tapps_dashboard")

    hub = _get_metrics_hub()

    if output_format == "otel":
        from tapps_core.metrics.otel_export import export_otel_trace

        recent = hub.execution.get_recent(limit=100)
        otel_data = export_otel_trace(recent)
        elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
        _record_execution("tapps_dashboard", start)
        resp = success_response("tapps_dashboard", elapsed_ms, otel_data)
        return _with_nudges("tapps_dashboard", resp)

    from tapps_core.metrics.dashboard import DashboardGenerator
    from tapps_mcp.server_helpers import _get_memory_store

    memory_store = None
    try:
        memory_store = _get_memory_store()
    except Exception as exc:
        import structlog as _structlog

        _structlog.get_logger(__name__).debug("memory_store_init_failed", error=str(exc))

    dashboard = hub.get_dashboard_generator(memory_store=memory_store)
    since = DashboardGenerator._parse_time_range(time_range)

    if output_format == "json":
        data = dashboard.generate_json_dashboard(sections=sections, since=since)
        data["time_range"] = time_range
        data["time_range_applied"] = True
    elif output_format == "markdown":
        content = dashboard.generate_markdown_dashboard(sections=sections, since=since)
        data = {
            "format": "markdown",
            "time_range": time_range,
            "time_range_applied": True,
            "content": content,
        }
    elif output_format == "html":
        content = dashboard.generate_html_dashboard(sections=sections, since=since)
        path = dashboard.save_dashboard(fmt="html", sections=sections)
        data = {
            "format": "html",
            "time_range": time_range,
            "time_range_applied": True,
            "content": content,
            "saved_to": str(path),
        }
    else:
        data = dashboard.generate_json_dashboard(sections=sections, since=since)
        data["time_range"] = time_range
        data["time_range_applied"] = True

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_dashboard", start)
    resp = success_response("tapps_dashboard", elapsed_ms, data)
    return _with_nudges("tapps_dashboard", resp)


def tapps_stats(
    tool_name: str | None = None,
    period: str = "session",
) -> dict[str, Any]:
    """Returns per-tool usage statistics: call counts, success rates,
    p50/p95 durations, cache hit rates, and gate pass rates, optionally
    filtered to one tool.

    Call this when investigating "what did I run this session?" or
    triaging a slow workflow ("which tool ate the wall-clock?"). For a
    full dashboard with trends and recommendations use
    ``tapps_dashboard``; for a one-shot config / connectivity check use
    ``tapps_doctor``.

    Args:
        tool_name: Restrict stats to one tool name (e.g.
            ``"tapps_quick_check"``). Default ``None`` returns the
            full per-tool breakdown.
        period: Aggregation window: ``"session"`` (current MCP process),
            ``"1d"``, ``"7d"``, ``"30d"``, or ``"all"``.
    """
    from tapps_mcp.server import _get_metrics_hub, _record_call, _record_execution, _with_nudges

    start = time.perf_counter_ns()
    _record_call("tapps_stats")

    hub = _get_metrics_hub()

    if period == "session":
        summary, tool_breakdowns = _session_stats(hub, tool_name)
    else:
        summary, tool_breakdowns = _period_stats(hub, tool_name, period)

    recommendations = _generate_stats_recommendations(summary, tool_breakdowns)

    payload: dict[str, Any] = {
        "period": period,
        "total_calls": summary.total_calls,
        "success_rate": summary.success_rate,
        "avg_duration_ms": summary.avg_duration_ms,
        "p95_duration_ms": summary.p95_duration_ms,
        "gate_pass_rate": summary.gate_pass_rate,
        "avg_score": summary.avg_score,
        "tools": tool_breakdowns,
        "recommendations": recommendations,
    }
    docs_tools = [t for t in tool_breakdowns if _is_docs_stats_tool(t.get("tool_name", ""))]
    if docs_tools:
        payload["docs_tools"] = docs_tools
        payload["docs_tool_calls"] = sum(int(t.get("call_count", 0)) for t in docs_tools)

    # ADR-0029 / TAP-4561: unified per-cache hit/miss counters.
    from tapps_core.cache import collect_cache_stats

    payload["caches"] = collect_cache_stats()

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_stats", start)

    resp = success_response(
        "tapps_stats",
        elapsed_ms,
        payload,
    )
    return _with_nudges("tapps_stats", resp)


_GATE_FAIL_THRESHOLD = 0.5
_SLOW_VALIDATE_MS = 60000


def _generate_stats_recommendations(
    summary: object,
    tool_breakdowns: list[dict[str, Any]],
) -> list[str]:
    """Generate actionable recommendations from usage patterns."""
    recommendations: list[str] = []
    tools_by_name: dict[str, dict[str, Any]] = {t["tool_name"]: t for t in tool_breakdowns}

    score_calls = tools_by_name.get("tapps_score_file", {}).get("call_count", 0)
    security_calls = tools_by_name.get("tapps_security_scan", {}).get("call_count", 0)

    if score_calls > 0 and security_calls < score_calls * 0.2:
        recommendations.append("Consider enabling auto-security in tapps_quick_check")

    gate_rate = getattr(summary, "gate_pass_rate", None)
    if gate_rate is not None and gate_rate < _GATE_FAIL_THRESHOLD:
        recommendations.append(
            "Quality gate failing frequently - consider running "
            "tapps_quick_check more often during development"
        )

    if "tapps_checklist" not in tools_by_name:
        recommendations.append("Always run tapps_checklist as your final verification step")

    vc = tools_by_name.get("tapps_validate_changed", {})
    if vc.get("avg_duration_ms", 0) > _SLOW_VALIDATE_MS:
        recommendations.append("Consider using tapps_quick_check per-file for faster feedback")

    return recommendations


# Known tool names for validation.
_VALID_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "tapps_checklist",
        "tapps_dashboard",
        "tapps_dead_code",
        "tapps_dependency_graph",
        "tapps_dependency_scan",
        "tapps_doctor",
        "tapps_feedback",
        "tapps_impact_analysis",
        "tapps_init",
        "tapps_lookup_docs",
        "tapps_memory",
        "tapps_quality_gate",
        "tapps_quick_check",
        "tapps_report",
        "tapps_score_file",
        "tapps_security_scan",
        "tapps_server_info",
        "tapps_session_notes",
        "tapps_session_start",
        "tapps_set_engagement_level",
        "tapps_stats",
        "tapps_upgrade",
        "tapps_validate_changed",
        "tapps_validate_config",
    }
)

# Scoring tools whose feedback triggers adaptive weight adjustment.
_SCORING_TOOLS: frozenset[str] = frozenset(
    {
        "tapps_score_file",
        "tapps_quality_gate",
        "tapps_quick_check",
    }
)

# TAP-1798: tools whose feedback updates the domain routing weight store.
# Currently the docs-lookup tool is the only expert surface — the rest of
# the catalogue routes via different mechanisms.
_EXPERT_TOOLS: frozenset[str] = frozenset({"tapps_lookup_docs"})

_WEIGHT_DELTA = 0.02


def tapps_feedback(
    tool_name: str,
    helpful: bool,
    context: str | None = None,
    domain: str | None = None,
) -> dict[str, Any]:
    """Records a thumbs-up/thumbs-down signal for the last response from a
    named tool; the signal nudges TappsMCP's adaptive scoring weights
    and (for expert tools) the per-domain weight store.

    Call this immediately after observing an unhelpful tool response
    that you want the system to learn from — false positives from
    ``tapps_security_scan``, an irrelevant ``tapps_lookup_docs`` doc
    excerpt, a noisy ``tapps_dead_code`` finding. Provide ``context``
    so future triage understands the failure mode. For expert tools
    (currently ``tapps_lookup_docs``), pass ``domain`` to additionally
    adjust the DomainWeightStore.

    Args:
        tool_name: Tool to provide feedback on. Must be one of the
            registered tool names (``tapps_*``).
        helpful: ``True`` for thumbs-up, ``False`` for thumbs-down.
        context: One-sentence rationale (e.g., ``"flagged a test
            fixture as a real secret"``). Optional but strongly
            recommended — feedback without context cannot be acted on.
        domain: Domain identifier for expert-tool feedback (e.g.,
            ``"security"``, ``"acme-billing"``). When set alongside
            an expert tool name, updates that domain's weight via
            ``_adjust_domain_weights`` (TAP-1798); the response
            ``domain_weight_adjusted`` field reflects whether the
            nudge took effect.
    """
    from tapps_mcp.server import _get_metrics_hub, _record_call, _record_execution, _with_nudges

    start = time.perf_counter_ns()
    _record_call("tapps_feedback")

    # Validate tool_name
    if tool_name not in _VALID_TOOL_NAMES:
        return error_response(
            "tapps_feedback",
            "invalid_tool_name",
            f"Unknown tool '{tool_name}'. Valid tools: " + ", ".join(sorted(_VALID_TOOL_NAMES)),
        )

    # Sanitize context and domain
    sanitized_context = _sanitize_param(context or "", max_len=500)
    sanitized_domain = _sanitize_param(domain or "", max_len=100) if domain else None

    from tapps_core.metrics.feedback import FeedbackTracker

    hub = _get_metrics_hub()
    tracker = FeedbackTracker(hub.metrics_dir)

    # Deduplication check
    duplicate_skipped = tracker.is_duplicate(tool_name, helpful, sanitized_context)

    if not duplicate_skipped:
        tracker.record(
            tool_name=tool_name,
            helpful=helpful,
            context=sanitized_context,
            session_id=hub.session_id,
        )

    # Adaptive weight adjustment for scoring tools
    weight_adjusted = False
    if not duplicate_skipped and tool_name in _SCORING_TOOLS:
        weight_adjusted = _adjust_scoring_weights(helpful)

    # TAP-1798: actually invoke domain weight adjustment for expert tools.
    # Previously the docstring advertised this but no call site existed —
    # the response surfaced `domain` without ever moving DomainWeightStore.
    domain_weight_adjusted = False
    domain_weight_type: str | None = None
    if not duplicate_skipped and sanitized_domain and tool_name in _EXPERT_TOOLS:
        domain_weight_adjusted, domain_weight_type = _adjust_domain_weights(
            sanitized_domain, helpful
        )

    stats = tracker.get_statistics(tool_name=tool_name)
    overall_stats = tracker.get_statistics()

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_feedback", start)

    result_data: dict[str, Any] = {
        "recorded": not duplicate_skipped,
        "tool_name": tool_name,
        "helpful": helpful,
        "duplicate_skipped": duplicate_skipped,
        "weight_adjusted": weight_adjusted,
        "domain_weight_adjusted": domain_weight_adjusted,
        "tool_stats": stats,
        "overall_stats": overall_stats,
    }

    if sanitized_domain:
        result_data["domain"] = sanitized_domain
    if domain_weight_type is not None:
        result_data["domain_weight_type"] = domain_weight_type

    resp = success_response("tapps_feedback", elapsed_ms, result_data)
    return _with_nudges("tapps_feedback", resp)


def _adjust_scoring_weights(helpful: bool) -> bool:
    """Nudge adaptive scoring weights based on feedback.

    Returns True if weights were successfully adjusted.
    """
    try:
        from tapps_core.config.settings import load_settings

        settings = load_settings()
        weights = settings.scoring_weights
        weight_dict = {
            "complexity": weights.complexity,
            "security": weights.security,
            "maintainability": weights.maintainability,
            "test_coverage": weights.test_coverage,
            "performance": weights.performance,
            "structure": weights.structure,
            "devex": weights.devex,
        }

        delta = _WEIGHT_DELTA if helpful else -_WEIGHT_DELTA
        adjusted = {k: max(0.01, v + delta) for k, v in weight_dict.items()}

        # Normalize to sum to 1.0
        total = sum(adjusted.values())
        if total > 0:
            adjusted = {k: round(v / total, 6) for k, v in adjusted.items()}

        # Update the cached settings scoring weights
        for k, v in adjusted.items():
            setattr(settings.scoring_weights, k, v)

        return True
    except Exception:
        import structlog as _structlog

        _structlog.get_logger(__name__).debug("weight_adjustment_failed", exc_info=True)
        return False


def _adjust_domain_weights(domain: str, helpful: bool) -> tuple[bool, str | None]:
    """Update domain routing weights based on feedback (Epic 57).

    Determines if the domain is technical or business, then updates
    the appropriate weight in DomainWeightStore.

    Args:
        domain: The domain identifier to update.
        helpful: Whether the feedback was positive.

    Returns:
        A tuple of (success, domain_type) where domain_type is
        "technical", "business", or None if adjustment failed.
    """
    try:
        from tapps_core.adaptive.persistence import DomainWeightStore
        from tapps_core.config.settings import load_settings

        settings = load_settings()
        store = DomainWeightStore(settings.project_root)

        store.update_from_feedback(
            domain,
            helpful=helpful,
            domain_type="technical",
            learning_rate=0.1,
        )

        import structlog as _structlog

        _structlog.get_logger(__name__).debug(
            "domain_weight_adjusted",
            domain=domain,
            helpful=helpful,
        )

        return True, "technical"

    except Exception:
        import structlog as _structlog

        _structlog.get_logger(__name__).debug(
            "domain_weight_adjustment_failed", domain=domain, exc_info=True
        )
        return False, None


def tapps_usage(
    output_format: str = "json",
    rolling_window_days: int = 7,
) -> dict[str, Any]:
    """Returns a per-session gap report: what the agent did vs what the
    TAPPS pipeline recommends.

    Composes three telemetry substrates already present in this repo:
    in-process ``CallTracker`` (current session), ``loop-metrics.jsonl``
    (per-Stop-event metrics from the Stop hook), and
    ``.completion-gate-violations.jsonl`` (warn-mode violations).

    Use this when investigating "what did I miss?" — the response carries
    a ``gaps`` list (e.g. ``edits_without_validation``) and a
    ``recommendations`` list of specific next calls. Hooked into
    ``tapps_checklist`` so end-of-task checks surface gaps inline.

    Args:
        output_format: ``"json"`` (default, machine-readable) or
            ``"markdown"`` (human-readable summary in ``data.markdown``).
        rolling_window_days: Trailing window for ``loop-metrics.jsonl``
            aggregation. Default 7.
    """
    from pathlib import Path as _Path

    from tapps_core.config.settings import load_settings
    from tapps_mcp.server import _record_call, _record_execution, _with_nudges
    from tapps_mcp.tools.usage import compute_gaps, render_markdown

    start = time.perf_counter_ns()
    _record_call("tapps_usage")

    settings = load_settings()
    project_root = _Path(settings.project_root).expanduser().resolve()

    report = compute_gaps(project_root, rolling_window_days=rolling_window_days)
    if output_format == "markdown":
        report["markdown"] = render_markdown(report)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_usage", start)

    resp = success_response("tapps_usage", elapsed_ms, report)
    return _with_nudges("tapps_usage", resp)


def register(mcp_instance: FastMCP, allowed_tools: frozenset[str]) -> None:
    """Register metrics/feedback tools on *mcp_instance*.

    TAP-1986: metrics tools are deferred (not daily drivers). tapps_usage
    is not deferred — it's part of the end-of-task pipeline alongside
    tapps_checklist.
    """
    if "tapps_dashboard" in allowed_tools:
        register_tool(
            mcp_instance, tapps_dashboard, annotations=_ANNOTATIONS_READ_ONLY, meta=_META_DEFERRED
        )
    if "tapps_stats" in allowed_tools:
        register_tool(
            mcp_instance, tapps_stats, annotations=_ANNOTATIONS_READ_ONLY, meta=_META_DEFERRED
        )
    if "tapps_feedback" in allowed_tools:
        register_tool(
            mcp_instance, tapps_feedback, annotations=_ANNOTATIONS_SIDE_EFFECT, meta=_META_DEFERRED
        )
    if "tapps_usage" in allowed_tools:
        register_tool(mcp_instance, tapps_usage, annotations=_ANNOTATIONS_READ_ONLY)

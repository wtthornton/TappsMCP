"""Metrics, dashboard, feedback, and research tool handlers for TappsMCP.

Functions are defined at module level (importable for tests) and
registered on the ``mcp`` instance via :func:`register`.
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Any

from mcp.types import ToolAnnotations

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

def _sanitize_param(value: str, max_len: int = 100) -> str:
    """Strip control characters and truncate a parameter value."""
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "", value).strip()
    return cleaned[:max_len]


_PERIOD_DAYS: dict[str, int] = {"1d": 1, "7d": 7, "30d": 30}


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
    except Exception:
        pass

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
    """Return usage statistics for TappsMCP tools.

    Shows call counts, success rates, average durations, cache hit rates,
    and gate pass rates.

    Args:
        tool_name: Filter stats to a specific tool (optional).
        period: Stats period - "session", "1d", "7d", "30d", "all".
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

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_stats", start)

    resp = success_response(
        "tapps_stats",
        elapsed_ms,
        {
            "period": period,
            "total_calls": summary.total_calls,
            "success_rate": summary.success_rate,
            "avg_duration_ms": summary.avg_duration_ms,
            "p95_duration_ms": summary.p95_duration_ms,
            "gate_pass_rate": summary.gate_pass_rate,
            "avg_score": summary.avg_score,
            "tools": tool_breakdowns,
            "recommendations": recommendations,
        },
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
    tools_by_name: dict[str, dict[str, Any]] = {
        t["tool_name"]: t for t in tool_breakdowns
    }

    score_calls = tools_by_name.get("tapps_score_file", {}).get("call_count", 0)
    security_calls = tools_by_name.get("tapps_security_scan", {}).get("call_count", 0)

    if score_calls > 0 and security_calls < score_calls * 0.2:
        recommendations.append(
            "Consider enabling auto-security in tapps_quick_check"
        )

    gate_rate = getattr(summary, "gate_pass_rate", None)
    if gate_rate is not None and gate_rate < _GATE_FAIL_THRESHOLD:
        recommendations.append(
            "Quality gate failing frequently - consider running "
            "tapps_quick_check more often during development"
        )

    if "tapps_checklist" not in tools_by_name:
        recommendations.append(
            "Always run tapps_checklist as your final verification step"
        )

    vc = tools_by_name.get("tapps_validate_changed", {})
    if vc.get("avg_duration_ms", 0) > _SLOW_VALIDATE_MS:
        recommendations.append(
            "Consider using tapps_quick_check per-file for faster feedback"
        )

    return recommendations


# Known tool names for validation.
_VALID_TOOL_NAMES: frozenset[str] = frozenset({
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
})

# Scoring tools whose feedback triggers adaptive weight adjustment.
_SCORING_TOOLS: frozenset[str] = frozenset({
    "tapps_score_file",
    "tapps_quality_gate",
    "tapps_quick_check",
})

_WEIGHT_DELTA = 0.02


def tapps_feedback(
    tool_name: str,
    helpful: bool,
    context: str | None = None,
    domain: str | None = None,
) -> dict[str, Any]:
    """Report whether a tool's output was helpful.

    This feedback improves TappsMCP's adaptive scoring and expert weights
    over time. For expert tools, also updates domain routing weights.

    Args:
        tool_name: Which tool to provide feedback on.
        helpful: Was the output helpful?
        context: Additional context about why it was or wasn't helpful.
        domain: Domain for expert feedback (e.g., "security", "acme-billing").
            When provided with expert tools, updates domain routing weights.
    """
    from tapps_mcp.server import _get_metrics_hub, _record_call, _record_execution, _with_nudges

    start = time.perf_counter_ns()
    _record_call("tapps_feedback")

    # Validate tool_name
    if tool_name not in _VALID_TOOL_NAMES:
        return error_response(
            "tapps_feedback",
            "invalid_tool_name",
            f"Unknown tool '{tool_name}'. Valid tools: "
            + ", ".join(sorted(_VALID_TOOL_NAMES)),
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
        "tool_stats": stats,
        "overall_stats": overall_stats,
    }

    if sanitized_domain:
        result_data["domain"] = sanitized_domain

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

        _structlog.get_logger(__name__).debug(
            "weight_adjustment_failed", exc_info=True
        )
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


async def tapps_research(
    question: str,
    domain: str = "",
    library: str = "",
    topic: str = "",
    file_context: str = "",
) -> dict[str, Any]:
    """**DEPRECATED** — Expert system removed (EPIC-94).

    Use tapps_lookup_docs for documentation, or AgentForge for expert consultation.
    """
    return error_response(
        "tapps_research",
        "TOOL_DEPRECATED",
        "tapps_research has been removed (EPIC-94). "
        "Use tapps_lookup_docs for documentation lookup, "
        "or AgentForge for expert consultation.",
        extra={
            "deprecated_since": "EPIC-94",
            "alternatives": [
                {"tool": "tapps_lookup_docs", "use_for": "library documentation lookup"},
                {"tool": "AgentForge", "use_for": "expert consultation"},
            ],
        },
    )


async def tapps_consult_expert(
    question: str,
    domain: str = "",
) -> dict[str, Any]:
    """**DEPRECATED** — Expert system removed (EPIC-94).

    The RAG-based expert consultation system has been removed.
    Use tapps_lookup_docs for documentation, or AgentForge for expert consultation.
    """
    return error_response(
        "tapps_consult_expert",
        "TOOL_DEPRECATED",
        "tapps_consult_expert has been removed (EPIC-94). "
        "The RAG-based expert system no longer exists. "
        "Use tapps_lookup_docs for documentation lookup, "
        "or AgentForge for expert consultation.",
        extra={
            "deprecated_since": "EPIC-94",
            "alternatives": [
                {"tool": "tapps_lookup_docs", "use_for": "library documentation lookup"},
                {"tool": "AgentForge", "use_for": "expert consultation"},
            ],
        },
    )


def register(mcp_instance: FastMCP, allowed_tools: frozenset[str]) -> None:
    """Register metrics/feedback tools on *mcp_instance*."""
    if "tapps_dashboard" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_dashboard)
    if "tapps_stats" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_stats)
    if "tapps_feedback" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT)(tapps_feedback)
    if "tapps_research" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY_OPEN)(tapps_research)
    if "tapps_consult_expert" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY_OPEN)(tapps_consult_expert)

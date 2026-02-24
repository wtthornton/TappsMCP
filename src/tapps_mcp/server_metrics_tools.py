"""Metrics, dashboard, feedback, and research tool handlers for TappsMCP.

Functions are defined at module level (importable for tests) and
registered on the ``mcp`` instance via :func:`register`.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from mcp.types import ToolAnnotations

from tapps_mcp.config.settings import load_settings
from tapps_mcp.server_helpers import success_response

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from tapps_mcp.metrics.collector import MetricsHub

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

_MIN_CONFIDENCE_FOR_DOCS = 0.5


_PERIOD_DAYS: dict[str, int] = {"1d": 1, "7d": 7, "30d": 30}


def _session_stats(
    hub: MetricsHub,
    tool_name: str | None,
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
        data["time_range"] = time_range
    elif output_format == "markdown":
        content = dashboard.generate_markdown_dashboard(sections=sections)
        data = {"format": "markdown", "time_range": time_range, "content": content}
    elif output_format == "html":
        content = dashboard.generate_html_dashboard(sections=sections)
        path = dashboard.save_dashboard(fmt="html", sections=sections)
        data = {
            "format": "html",
            "time_range": time_range,
            "content": content,
            "saved_to": str(path),
        }
    else:
        data = dashboard.generate_json_dashboard(sections=sections)
        data["time_range"] = time_range

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
        },
    )
    return _with_nudges("tapps_stats", resp)


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
    from tapps_mcp.server import _get_metrics_hub, _record_call, _record_execution, _with_nudges

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

    resp = success_response(
        "tapps_feedback",
        elapsed_ms,
        {
            "recorded": True,
            "tool_name": tool_name,
            "helpful": helpful,
            "tool_stats": stats,
            "overall_stats": overall_stats,
        },
    )
    return _with_nudges("tapps_feedback", resp)


async def tapps_research(
    question: str,
    domain: str = "",
    library: str = "",
    topic: str = "",
) -> dict[str, Any]:
    """Combined expert consultation + documentation lookup in one call.

    Consults the domain expert first, then automatically supplements with
    Context7 documentation when expert RAG has no results or confidence is
    low.  Saves a round-trip compared to calling tapps_consult_expert and
    tapps_lookup_docs separately.

    Args:
        question: The technical question to research (natural language).
        domain: Optional domain override for expert routing.
        library: Optional library name for docs lookup (auto-inferred when empty).
        topic: Optional topic for docs lookup (auto-inferred when empty).
    """
    from tapps_mcp.server import _record_call, _record_execution, _with_nudges

    start = time.perf_counter_ns()
    _record_call("tapps_research")

    from tapps_mcp.experts.engine import consult_expert

    result = consult_expert(
        question=question,
        domain=domain or None,
    )

    needs_docs = result.chunks_used == 0 or result.confidence < _MIN_CONFIDENCE_FOR_DOCS

    docs_content: str | None = None
    docs_source: str | None = None
    docs_library: str | None = None
    docs_topic: str | None = None
    docs_error: str | None = None

    if needs_docs:
        lookup_library = library or result.suggested_library or "python"
        lookup_topic = topic or result.suggested_topic or "overview"

        try:
            from tapps_mcp.knowledge.cache import KBCache
            from tapps_mcp.knowledge.lookup import LookupEngine

            settings = load_settings()
            cache = KBCache(settings.project_root / ".tapps-mcp-cache")
            engine = LookupEngine(cache, api_key=settings.context7_api_key)
            try:
                lr = await engine.lookup(
                    library=lookup_library,
                    topic=lookup_topic,
                    mode="code",
                )
            finally:
                await engine.close()

            if lr.success and lr.content:
                max_chars = settings.expert_fallback_max_chars
                docs_content = lr.content[:max_chars]
                docs_source = lr.source
                docs_library = lookup_library
                docs_topic = lookup_topic
            else:
                docs_error = "Docs lookup returned no content."
        except Exception as exc:
            docs_error = str(exc)

    answer = result.answer
    if docs_content:
        answer = (
            f"{answer}\n\n---\n\n"
            f"### Documentation reference (auto-attached)\n\n"
            f"Library: `{docs_library}` | Topic: `{docs_topic}` | Source: {docs_source}\n\n"
            f"{docs_content}"
        )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    _record_execution("tapps_research", start)

    resp = success_response(
        "tapps_research",
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
            "docs_supplemented": docs_content is not None,
            "docs_library": docs_library,
            "docs_topic": docs_topic,
            "docs_error": docs_error,
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
        from tapps_mcp.common.output_schemas import ResearchOutput

        structured = ResearchOutput(
            domain=result.domain,
            expert_name=result.expert_name,
            answer=answer,
            confidence=round(result.confidence, 4),
            sources=result.sources,
            docs_supplemented=docs_content is not None,
            docs_library=docs_library,
            docs_topic=docs_topic,
        )
        resp["structuredContent"] = structured.to_structured_content()
    except Exception:
        import structlog as _structlog

        _structlog.get_logger(__name__).debug(
            "structured_output_failed: tapps_research", exc_info=True
        )

    return _with_nudges("tapps_research", resp)


def register(mcp_instance: FastMCP) -> None:
    """Register metrics/feedback/research tools on *mcp_instance*."""
    mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_dashboard)
    mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_stats)
    mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT)(tapps_feedback)
    mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY_OPEN)(tapps_research)

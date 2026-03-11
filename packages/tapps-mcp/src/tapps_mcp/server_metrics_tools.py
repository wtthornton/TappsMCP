"""Metrics, dashboard, feedback, and research tool handlers for TappsMCP.

Functions are defined at module level (importable for tests) and
registered on the ``mcp`` instance via :func:`register`.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import TYPE_CHECKING, Any

from mcp.types import ToolAnnotations

from tapps_core.config.settings import load_settings
from tapps_mcp.server_helpers import error_response, success_response

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

    if "tapps_research" not in tools_by_name:
        recommendations.append(
            "Use tapps_research for domain-specific questions before implementation"
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
    "tapps_consult_expert",
    "tapps_dashboard",
    "tapps_dead_code",
    "tapps_dependency_graph",
    "tapps_dependency_scan",
    "tapps_doctor",
    "tapps_feedback",
    "tapps_impact_analysis",
    "tapps_init",
    "tapps_list_experts",
    "tapps_lookup_docs",
    "tapps_project_profile",
    "tapps_quality_gate",
    "tapps_quick_check",
    "tapps_report",
    "tapps_research",
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

# Expert tools whose feedback triggers domain weight adjustment (Epic 57).
_EXPERT_TOOLS: frozenset[str] = frozenset({
    "tapps_consult_expert",
    "tapps_research",
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

    # Domain weight adjustment for expert tools (Epic 57)
    domain_weight_adjusted = False
    domain_type: str | None = None
    if not duplicate_skipped and sanitized_domain and tool_name in _EXPERT_TOOLS:
        domain_weight_adjusted, domain_type = _adjust_domain_weights(
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
        "tool_stats": stats,
        "overall_stats": overall_stats,
    }

    # Include domain feedback info when applicable (Epic 57)
    if sanitized_domain:
        result_data["domain"] = sanitized_domain
        result_data["domain_weight_adjusted"] = domain_weight_adjusted
        if domain_type:
            result_data["domain_type"] = domain_type

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
        from typing import Literal

        from tapps_core.adaptive.persistence import DomainWeightStore
        from tapps_core.config.settings import load_settings
        from tapps_core.experts.registry import ExpertRegistry

        settings = load_settings()
        store = DomainWeightStore(settings.project_root)

        # Determine if domain is technical or business
        business_domains = ExpertRegistry.get_business_domains()
        technical_domains = ExpertRegistry.TECHNICAL_DOMAINS

        domain_type: Literal["technical", "business"]
        if domain in business_domains:
            domain_type = "business"
        elif domain in technical_domains:
            domain_type = "technical"
        else:
            # Unknown domain - assume business (custom/new)
            domain_type = "business"

        # Update the weight
        store.update_from_feedback(
            domain,
            helpful=helpful,
            domain_type=domain_type,
            learning_rate=0.1,
        )

        import structlog as _structlog

        _structlog.get_logger(__name__).debug(
            "domain_weight_adjusted",
            domain=domain,
            domain_type=domain_type,
            helpful=helpful,
        )

        return True, domain_type

    except Exception:
        import structlog as _structlog

        _structlog.get_logger(__name__).debug(
            "domain_weight_adjustment_failed", domain=domain, exc_info=True
        )
        return False, None


# ---------------------------------------------------------------------------
# tapps_research helpers
# ---------------------------------------------------------------------------


def _infer_library_for_research(
    library: str,
    file_context: str,
    suggested_library: str | None,
) -> str:
    """Infer the library name for doc lookup.

    Tries: file_context imports -> tech stack -> suggested_library -> "python".
    """
    if not library and file_context:
        try:
            from tapps_mcp.knowledge.import_analyzer import extract_external_imports
            from tapps_mcp.server import _validate_file_path

            resolved_ctx = _validate_file_path(file_context)
            settings = load_settings()
            external = extract_external_imports(resolved_ctx, settings.project_root)
            if external:
                return external[0]
        except Exception:
            pass

    if not library and not suggested_library:
        try:
            from tapps_mcp.server_helpers import get_session_context

            session_ctx = get_session_context()
            profile = session_ctx.get("project_profile") or {}
            tech_stack = profile.get("tech_stack", {})
            libs: list[str] = tech_stack.get(
                "context7_priority", []
            ) or tech_stack.get("libraries", [])
            if libs:
                return libs[0]
        except Exception:
            pass
        return "python"

    return library


async def _fetch_docs_for_research(
    lookup_library: str,
    lookup_topic: str,
) -> tuple[str | None, str | None, str | None, str | None, str | None]:
    """Fetch documentation, returning (content, source, library, topic, error)."""
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
            return lr.content[:max_chars], lr.source, lookup_library, lookup_topic, None
        return None, None, None, None, "Docs lookup returned no content."
    except Exception as exc:
        return None, None, None, None, str(exc)


def _append_docs_to_answer(
    answer: str,
    docs_content: str | None,
    docs_library: str | None,
    docs_topic: str | None,
    docs_source: str | None,
) -> str:
    """Append documentation reference to the expert answer."""
    if not docs_content:
        return answer
    return (
        f"{answer}\n\n---\n\n"
        f"### Documentation reference (auto-attached)\n\n"
        f"Library: `{docs_library}` | Topic: `{docs_topic}` "
        f"| Source: {docs_source}\n\n"
        f"{docs_content}"
    )


def _inject_research_memory(question: str, answer: str) -> tuple[str, int]:
    """Inject relevant memories into the answer. Returns (augmented_answer, count)."""
    try:
        from tapps_core.memory.injection import append_memory_to_answer, inject_memories
        from tapps_mcp.server_helpers import _get_memory_store

        settings = load_settings()
        store = _get_memory_store()
        mem_result = inject_memories(question, store, settings.llm_engagement_level)
        return append_memory_to_answer(answer, mem_result), mem_result.get("memory_injected", 0)
    except Exception:
        import structlog as _sl

        _sl.get_logger(__name__).debug(
            "memory_injection_failed: tapps_research", exc_info=True
        )
        return answer, 0


def _attach_research_structured_output(
    resp: dict[str, Any],
    result: Any,
    answer: str,
    docs_content: str | None,
    docs_library: str | None,
    docs_topic: str | None,
    file_context: str,
) -> None:
    """Attach structured output to research response in-place."""
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
            file_context=file_context or None,
        )
        resp["structuredContent"] = structured.to_structured_content()
    except Exception:
        import structlog as _structlog

        _structlog.get_logger(__name__).debug(
            "structured_output_failed: tapps_research", exc_info=True
        )


async def tapps_research(
    question: str,
    domain: str = "",
    library: str = "",
    topic: str = "",
    file_context: str = "",
) -> dict[str, Any]:
    """Combined expert consultation + documentation lookup in one call.

    Consults the domain expert first, then automatically supplements with
    Context7 documentation.  Docs are always fetched to provide the most
    complete answer.  Saves a round-trip compared to calling
    tapps_consult_expert and tapps_lookup_docs separately.  This is the
    recommended tool for expert guidance.

    Available domains (omit domain to auto-detect from question):
      security, performance-optimization, testing-strategies,
      code-quality-analysis, software-architecture, development-workflow,
      data-privacy-compliance, accessibility, user-experience,
      documentation-knowledge-management, ai-frameworks, agent-learning,
      observability-monitoring, api-design-integration, cloud-infrastructure,
      database-data-management
      plus any user-defined business domains

    Args:
        question: The technical question to research (natural language).
        domain: Optional domain override for expert routing.
        library: Optional library name for docs lookup (auto-inferred when empty).
        topic: Optional topic for docs lookup (auto-inferred when empty).
        file_context: Optional file path for inferring library from imports.
    """
    from tapps_mcp.server import _record_call, _record_execution, _with_nudges

    start = time.perf_counter_ns()
    _record_call("tapps_research")

    question = _sanitize_param(question, max_len=5000)
    file_context = _sanitize_param(file_context, max_len=500)
    if not question:
        return error_response(
            "tapps_research", "invalid_question", "Question is required."
        )
    library = _sanitize_param(library)
    topic = _sanitize_param(topic)

    try:
        from tapps_mcp.experts.engine import consult_expert

        result = await asyncio.to_thread(
            consult_expert, question=question, domain=domain or None,
        )

        library = _infer_library_for_research(library, file_context, result.suggested_library)
        lookup_library = library or result.suggested_library or "python"
        lookup_topic = topic or result.suggested_topic or "overview"

        docs_content, docs_source, docs_library, docs_topic, docs_error = (
            await _fetch_docs_for_research(lookup_library, lookup_topic)
        )

        answer = _append_docs_to_answer(
            result.answer, docs_content, docs_library, docs_topic, docs_source,
        )
        answer, memory_injected = _inject_research_memory(question, answer)

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
                "memory_injected": memory_injected,
            },
        )

        _attach_research_structured_output(
            resp, result, answer, docs_content, docs_library, docs_topic, file_context,
        )
        return _with_nudges("tapps_research", resp)

    except Exception:
        import structlog as _structlog

        _structlog.get_logger(__name__).warning(
            "tapps_research_error", question=question[:80], exc_info=True
        )
        return error_response(
            "tapps_research",
            "research_failed",
            "Research failed. Try a different question or domain.",
        )


def register(mcp_instance: FastMCP, allowed_tools: frozenset[str]) -> None:
    """Register metrics/feedback/research tools on *mcp_instance* (Epic 79.1: conditional)."""
    if "tapps_dashboard" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_dashboard)
    if "tapps_stats" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_stats)
    if "tapps_feedback" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_SIDE_EFFECT)(tapps_feedback)
    if "tapps_research" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY_OPEN)(tapps_research)

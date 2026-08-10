"""Web research and cross-cutting research front door for TappsMCP.

Functions are defined at module level (importable for tests) and
registered on the ``mcp`` instance via :func:`register`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog
from mcp.types import ToolAnnotations

from tapps_core.config.settings import load_settings
from tapps_mcp.mcp_register import register_tool
from tapps_mcp.server_helpers import (
    _get_brain_bridge,
    error_response,
    success_response,
)
from tapps_mcp.server_lookup_tools import (
    _VALID_LOOKUP_MODES,
    _build_lookup_data,
    _lookup_error_code,
    _maybe_record_lookup_telemetry,
    _sanitize_lookup_param,
)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from tapps_mcp.tools.research import ResearchRoute

logger = structlog.get_logger(__name__)

_ANNOTATIONS_READ_ONLY_OPEN = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=True,
)

_META_DEFERRED: dict[str, Any] = {"defer_loading": True}

_MIN_RESEARCH_RESULTS = 1
_MAX_RESEARCH_RESULTS = 20


@dataclass(frozen=True)
class _ResearchArgs:
    """Sanitized, validated ``tapps_research`` arguments."""

    query: str
    library: str
    topic: str
    mode: str
    url: str
    route: str
    source: str
    freshness: str
    max_results: int


def _sanitize_research_args(
    *,
    query: str,
    library: str,
    topic: str,
    mode: str,
    url: str,
    source: str,
    freshness: str,
    max_results: int,
    route: str,
) -> _ResearchArgs | dict[str, Any]:
    """Sanitize and validate raw tool arguments.

    Returns a :class:`_ResearchArgs` on success, or an ``error_response`` dict
    when any enum-valued argument is out of contract.
    """
    from tapps_mcp.tools.research import VALID_FRESHNESS, VALID_ROUTES, VALID_SOURCES

    route_clean = (route or "auto").strip().lower() or "auto"
    source_clean = (source or "auto").strip().lower() or "auto"
    freshness_clean = (freshness or "volatile").strip().lower() or "volatile"

    def _invalid(message: str) -> dict[str, Any]:
        return error_response("tapps_research", "invalid_args", message)

    if route_clean not in VALID_ROUTES:
        return _invalid(
            f"Invalid route '{route}'. Must be one of: {', '.join(sorted(VALID_ROUTES))}"
        )
    if source_clean not in VALID_SOURCES:
        return _invalid(
            f"Invalid source '{source}'. Must be one of: {', '.join(sorted(VALID_SOURCES))}"
        )
    if freshness_clean not in VALID_FRESHNESS:
        return _invalid(
            f"Invalid freshness '{freshness}'. Must be one of: {', '.join(sorted(VALID_FRESHNESS))}"
        )
    if not isinstance(max_results, int) or isinstance(max_results, bool):
        return _invalid("max_results must be an integer between 1 and 20.")
    if max_results < _MIN_RESEARCH_RESULTS or max_results > _MAX_RESEARCH_RESULTS:
        return _invalid("max_results must be an integer between 1 and 20.")

    return _ResearchArgs(
        query=_sanitize_lookup_param(query, max_len=500),
        library=_sanitize_lookup_param(library),
        topic=_sanitize_lookup_param(topic) or "overview",
        mode=mode,
        url=_sanitize_lookup_param(url, max_len=2000),
        route=route_clean,
        source=source_clean,
        freshness=freshness_clean,
        max_results=max_results,
    )


async def _research_docs_route(args: _ResearchArgs, start: int) -> dict[str, Any]:
    """Serve the docs route through the shared lookup engine."""
    from tapps_mcp.server import _record_execution, _with_nudges
    from tapps_mcp.tools.research import telemetry_source_for_docs

    if not args.library:
        return error_response(
            "tapps_research",
            "missing_params",
            "Docs route requires library= (or pass route='web' for open-ended research).",
        )
    if args.mode not in _VALID_LOOKUP_MODES:
        return error_response(
            "tapps_research",
            "invalid_mode",
            f"Invalid mode '{args.mode}'. Must be one of: {', '.join(sorted(_VALID_LOOKUP_MODES))}",
        )

    from tapps_mcp.server_helpers import _get_lookup_engine

    engine = _get_lookup_engine()
    try:
        result = await engine.lookup(args.library, args.topic, mode=args.mode)
    except Exception:
        logger.warning(
            "research_docs_lookup_error",
            library=args.library,
            topic=args.topic,
            exc_info=True,
        )
        return error_response(
            "tapps_research",
            "lookup_failed",
            f"Documentation lookup failed for '{args.library}' / '{args.topic}'.",
        )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    data = _build_lookup_data(result)
    data["route"] = "docs"
    data["source"] = telemetry_source_for_docs(cache_hit=bool(result.cache_hit))
    data["query"] = args.query
    response = success_response("tapps_research", elapsed_ms, data)
    response["success"] = result.success
    err_code = _lookup_error_code(result.error)
    if result.error:
        response["error"] = {"code": err_code, "message": result.error}
    if result.warning:
        response["warning"] = result.warning
    _record_execution(
        "tapps_research",
        start,
        status="success" if result.success else "failed",
        error_code=err_code,
    )
    _maybe_record_lookup_telemetry(result, library=args.library, topic=args.topic)
    return _with_nudges("tapps_research", response)


def _resolve_fetch_url(args: _ResearchArgs, chosen: ResearchRoute) -> str | dict[str, Any]:
    """Resolve the URL for the fetch route, or return an error_response dict."""
    from tapps_mcp.tools.research import looks_like_url

    if chosen != "fetch":
        return ""
    if args.url:
        return args.url
    if looks_like_url(args.query):
        return args.query
    return error_response(
        "tapps_research",
        "missing_params",
        "Fetch route requires url= (absolute http(s) URL).",
    )


def _effective_freshness(args: _ResearchArgs, chosen: ResearchRoute, raw_freshness: str) -> str:
    """Fetch defaults to evergreen when the URL was inferred from the query."""
    inferred_url = chosen == "fetch" and args.route == "auto" and not args.url
    if inferred_url and raw_freshness == "volatile":
        return "evergreen"
    return args.freshness


async def _call_brain_research(
    bridge: Any, args: _ResearchArgs, *, chosen: ResearchRoute, fetch_url: str, freshness: str
) -> dict[str, Any]:
    """Invoke the brain research tool, normalizing non-dict payloads."""
    if chosen == "fetch":
        payload = await bridge.research_fetch(fetch_url, freshness=freshness)
    else:
        payload = await bridge.web_research(
            args.query,
            source=args.source,
            freshness=freshness,
            max_results=args.max_results,
        )
    if not isinstance(payload, dict):
        return {"success": False, "error": "invalid_response", "detail": str(payload)}
    return payload


async def _research_brain_route(
    args: _ResearchArgs, chosen: ResearchRoute, start: int, raw_freshness: str
) -> dict[str, Any]:
    """Serve the web/fetch routes through BrainBridge, degrading explicitly."""
    from tapps_core.brain_bridge import (
        BrainBridgeUnavailable,
        BrainMcpError,
        ToolNotInProfileError,
    )
    from tapps_mcp.server import _record_execution, _with_nudges
    from tapps_mcp.tools.research import bridge_degraded_response, wrap_brain_research_payload
    from tapps_mcp.tools.research_memory import (
        maybe_recall_research_answer,
        maybe_save_research_answer,
    )

    fetch_url_or_err = _resolve_fetch_url(args, chosen)
    if isinstance(fetch_url_or_err, dict):
        return fetch_url_or_err
    fetch_url = fetch_url_or_err

    if chosen == "web" and not args.query:
        return error_response(
            "tapps_research",
            "missing_params",
            "Web route requires a non-empty query.",
        )

    def _degrade(detail: str, reason: str | None = None) -> dict[str, Any]:
        elapsed = (time.perf_counter_ns() - start) // 1_000_000
        kwargs: dict[str, Any] = {"route": chosen, "detail": detail, "elapsed_ms": elapsed}
        if reason is not None:
            kwargs["reason"] = reason
        resp = bridge_degraded_response(**kwargs)
        _record_execution(
            "tapps_research",
            start,
            status="failed",
            error_code=reason or resp["data"]["error"],
        )
        return _with_nudges("tapps_research", resp)

    bridge = _get_brain_bridge()
    if bridge is None:
        return _degrade(
            "BrainBridge is not configured (set memory.brain_http_url).",
            "brain_bridge_unconfigured",
        )

    freshness = _effective_freshness(args, chosen, raw_freshness)
    memory_cfg = load_settings().memory

    recalled = await maybe_recall_research_answer(
        bridge,
        route=chosen,
        query=args.query,
        url=fetch_url,
        freshness=freshness,
        memory_enabled=memory_cfg.enabled,
        auto_save_quality=memory_cfg.auto_save_quality,
        volatile_ttl_hours=memory_cfg.research_volatile_ttl_hours,
        evergreen_ttl_days=memory_cfg.research_evergreen_ttl_days,
        elapsed_ms=(time.perf_counter_ns() - start) // 1_000_000,
    )
    if recalled is not None:
        _record_execution("tapps_research", start, status="success", error_code=None)
        return _with_nudges("tapps_research", recalled)

    try:
        brain_payload = await _call_brain_research(
            bridge, args, chosen=chosen, fetch_url=fetch_url, freshness=freshness
        )
    except (BrainBridgeUnavailable, ToolNotInProfileError, BrainMcpError) as exc:
        reason = (
            "brain_tool_unavailable"
            if isinstance(exc, ToolNotInProfileError)
            else "brain_bridge_call_failed"
        )
        return _degrade(str(exc) or type(exc).__name__, reason)
    except Exception as exc:
        logger.warning("research_brain_call_error", route=chosen, exc_info=True)
        return _degrade(str(exc) or type(exc).__name__)

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    response = wrap_brain_research_payload(brain_payload, route=chosen, elapsed_ms=elapsed_ms)
    if response.get("success"):
        response_data = response.get("data")
        await maybe_save_research_answer(
            bridge,
            brain_payload,
            route=chosen,
            query=args.query,
            url=fetch_url,
            freshness=freshness,
            memory_enabled=memory_cfg.enabled,
            auto_save_quality=memory_cfg.auto_save_quality,
            response_data=response_data if isinstance(response_data, dict) else None,
        )
    _record_execution(
        "tapps_research",
        start,
        status="success" if response.get("success") else "failed",
        error_code=(
            None
            if response.get("success")
            else str(brain_payload.get("error") or "research_failed")
        ),
    )
    return _with_nudges("tapps_research", response)


async def tapps_research(
    query: str,
    library: str = "",
    topic: str = "overview",
    mode: str = "code",
    url: str = "",
    source: str = "auto",
    freshness: str = "volatile",
    max_results: int = 5,
    route: str = "auto",
) -> dict[str, Any]:
    """Unified research front door (ADR-0030 / TAP-5365).

    Routes library/API documentation questions to ``lookup_docs`` and
    open-ended / latest / URL questions to tapps-brain ``web_research`` or
    ``research_fetch`` via BrainBridge. Provider credentials stay brain-side;
    brain-down returns a structured degraded error (never silent empty success).

    Args:
        query: Free-text research question (required for web; also used for
            auto-routing heuristics).
        library: When set (or ``route="docs"``), forces the docs path.
        topic: Docs subtopic when routing to ``lookup_docs``.
        mode: ``"code"`` or ``"info"`` for the docs path.
        url: When set (or ``route="fetch"``), scrapes a single URL via brain
            ``research_fetch``.
        source: Brain provider hint: ``auto`` | ``exa`` | ``tavily`` | ``firecrawl``.
        freshness: ``volatile`` (default for search) or ``evergreen``.
        max_results: 1-20 results for ``web_research``.
        route: ``auto`` | ``docs`` | ``web`` | ``fetch``.
    """
    from tapps_mcp.server import _record_call
    from tapps_mcp.tools.research import classify_research_route

    start = time.perf_counter_ns()
    _record_call("tapps_research")

    args = _sanitize_research_args(
        query=query,
        library=library,
        topic=topic,
        mode=mode,
        url=url,
        source=source,
        freshness=freshness,
        max_results=max_results,
        route=route,
    )
    if isinstance(args, dict):
        return args

    chosen = classify_research_route(
        args.query, library=args.library, url=args.url, route=args.route
    )
    if chosen == "docs":
        return await _research_docs_route(args, start)
    return await _research_brain_route(args, chosen, start, freshness)


def register(mcp_instance: FastMCP, allowed_tools: frozenset[str]) -> None:
    """Register research tools on the shared *mcp_instance* (Epic 79.1: conditional)."""
    if "tapps_research" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_research,
            annotations=_ANNOTATIONS_READ_ONLY_OPEN,
            meta=_META_DEFERRED,
        )

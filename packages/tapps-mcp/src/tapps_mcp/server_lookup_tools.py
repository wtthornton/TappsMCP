"""Documentation lookup tool handlers for TappsMCP.

Functions are defined at module level (importable for tests) and
registered on the ``mcp`` instance via :func:`register`.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any

import structlog
from mcp.types import ToolAnnotations

from tapps_mcp.mcp_register import register_tool
from tapps_mcp.server_helpers import (
    error_response,
    success_response,
)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from tapps_core.knowledge.models import LookupResult

logger = structlog.get_logger(__name__)

_ANNOTATIONS_READ_ONLY_OPEN = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=True,
)

_VALID_LOOKUP_MODES: frozenset[str] = frozenset({"code", "info"})


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


async def _fallback_to_brain(
    library: str, topic: str, mode: str
) -> LookupResult | None:
    """Retry a failed lookup via tapps-brain when a brain route is reachable.

    TAP-6443: ``docs_via_brain`` is an opt-in config toggle for *routing every
    lookup* through the brain; it says nothing about whether brain is
    *reachable* as a fallback for a repo whose Context7 key is missing. A
    fallback gated on that same toggle fixes nothing for the 93% of repos
    that never turned it on. So this fires on the ``api_key_missing``
    classification itself, independent of the toggle, and simply returns
    ``None`` (no fallback content) when no bridge is configured or brain
    does not yet expose ``docs_lookup``.
    """
    from tapps_core.brain_bridge import BrainBridgeUnavailable
    from tapps_core.knowledge.brain_docs import lookup_via_brain
    from tapps_mcp.server_helpers import _get_brain_bridge

    bridge = _get_brain_bridge()
    if bridge is None:
        return None
    try:
        return await lookup_via_brain(bridge, library, topic, mode=mode)
    except BrainBridgeUnavailable:
        logger.debug("lookup_brain_fallback_failed", library=library, topic=topic, exc_info=True)
        return None


def _no_route_error_message(project_root: Any) -> str:
    """TAP-6443: name the exact setting and the repo it was resolved from."""
    return (
        "No documentation route available: Context7 API key is missing and no "
        "tapps-brain fallback is reachable. Set TAPPS_MCP_CONTEXT7_API_KEY "
        f"(or context7_api_key in .tapps-mcp.yaml) for project_root={project_root}."
    )


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
    if result.matched_library_id is not None:
        data["matched_library_id"] = result.matched_library_id
    if result.resolution_confidence is not None:
        data["resolution_confidence"] = result.resolution_confidence
    if result.likely_local_module:
        data["likely_local_module"] = True
    if result.fuzzy_score is not None:
        data["fuzzy_score"] = result.fuzzy_score
    # Issue #79: surface a hint when Context7 is not configured and we're
    # serving from the LlmsTxt fallback — users often don't realize they're
    # running in degraded mode.
    source_str = str(result.source or "").lower()
    has_key = bool(
        os.environ.get("TAPPS_MCP_CONTEXT7_API_KEY") or os.environ.get("CONTEXT7_API_KEY")
    )
    if not has_key and ("llmstxt" in source_str or source_str == "fallback"):
        data["context7_hint"] = (
            "Set TAPPS_MCP_CONTEXT7_API_KEY for richer docs via Context7 "
            "(currently using LlmsTxt fallback)."
        )
    return data


def _maybe_record_lookup_telemetry(result: LookupResult, *, library: str, topic: str) -> None:
    """Record coverage telemetry for trustworthy lookups only (TAP-5423)."""
    if not result.success:
        return
    if result.likely_local_module and result.resolution_confidence == "low":
        return
    try:
        from tapps_core.config.settings import load_settings
        from tapps_mcp.tools.lookup_telemetry import record_lookup_event

        settings = load_settings()
        record_lookup_event(
            settings.project_root,
            library=library,
            topic=topic,
            source="mcp",
            resolved_library=result.library if result.library != library else None,
        )
    except Exception:
        logger.debug("lookup_telemetry_record_failed", exc_info=True)


async def tapps_lookup_docs(
    library: str,
    topic: str = "overview",
    mode: str = "code",
) -> dict[str, Any]:
    """Fetches current documentation and code examples for an external
    library or framework.

    Call this before writing code that uses an external library API to
    avoid hallucinated signatures. Skip it for the Python standard
    library and for libraries you already looked up successfully in this
    session. Repeat calls are cache-hits at near-zero cost; do not call
    more than five times for the same library in a single task.

    When ``docs_via_brain`` is enabled (``TAPPS_MCP_DOCS_VIA_BRAIN=1`` or
    ``docs_via_brain: true`` in ``.tapps-mcp.yaml``), lookups delegate to
    tapps-brain ``docs_lookup`` (shared fleet cache, ADR-0014). Otherwise
    docs are served from per-project ``.tapps-mcp-cache/`` via Context7
    with a circuit-breaker fallback to the bundled llms.txt provider.

    Args:
        library: Official library name with proper punctuation
            (``"Next.js"`` not ``"nextjs"``; ``"FastAPI"`` not ``"fa"``).
            Fuzzy-matched against the Context7 index. Good:
            ``"httpx"``, ``"pydantic"``, ``"Django REST framework"``.
            Bad: cryptic aliases like ``"pyd"`` miss the index match.
        topic: Specific subtopic (default ``"overview"``). Good:
            ``"async client"``, ``"validators"``, ``"middleware"``,
            ``"fixtures"``. Bad: ``"help"`` or ``"how to use"`` —
            too generic, returns shallow overview content.
        mode: ``"code"`` for API references and code examples (default).
            ``"info"`` for conceptual or configuration guides. Any
            other value returns ``error.code=invalid_mode``.
    """
    from tapps_mcp.server import _record_call, _record_execution, _with_nudges

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

    err_code = _lookup_error_code(result.error)
    if err_code == "api_key_missing":
        fallback = await _fallback_to_brain(library, topic, mode)
        if fallback is not None and fallback.success:
            result = fallback
        elif result.error:
            from tapps_core.config.settings import load_settings

            result.error = _no_route_error_message(load_settings().project_root)

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

    _maybe_record_lookup_telemetry(result, library=library, topic=topic)

    return _with_nudges("tapps_lookup_docs", response)


def register(mcp_instance: FastMCP, allowed_tools: frozenset[str]) -> None:
    """Register lookup tools on the shared *mcp_instance* (Epic 79.1: conditional)."""
    if "tapps_lookup_docs" in allowed_tools:
        register_tool(mcp_instance, tapps_lookup_docs, annotations=_ANNOTATIONS_READ_ONLY_OPEN)

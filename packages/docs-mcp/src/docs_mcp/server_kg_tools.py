"""DocsMCP knowledge-graph query tool — docs_kg_query (TAP-1950).

A single meta-tool with a ``mode`` switch wrapping the existing BrainBridge KG
reads (``get_neighbors`` / ``explain_connection``), keeping the docs-mcp
``tools/list`` surface lean. Read-only; degrades cleanly when no brain
transport is configured.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

_logger = structlog.get_logger(__name__)

from docs_mcp.server import _ANNOTATIONS_READ_ONLY, _META_DEFERRED, _record_call
from docs_mcp.server_helpers import _get_brain_bridge, error_response, success_response


async def docs_kg_query(
    mode: str = "neighbors",
    entity_ids: list[str] | None = None,
    subject_id: str = "",
    object_id: str = "",
    hops: int = 1,
    max_hops: int = 2,
    predicate_filter: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    """Query the brain knowledge graph: mode='neighbors' (entity_ids, hops 1-2) or mode='explain' (subject_id->object_id, max_hops 1-3)."""
    _record_call("docs_kg_query")
    start = time.perf_counter_ns()

    if mode not in ("neighbors", "explain"):
        return error_response(
            "docs_kg_query",
            "INVALID_MODE",
            f"unknown mode {mode!r}; use 'neighbors' or 'explain'",
        )

    bridge = _get_brain_bridge()
    if bridge is None:
        elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
        return success_response(
            "docs_kg_query",
            elapsed_ms,
            {"mode": mode, "available": False, "degraded": True},
        )

    if mode == "neighbors":
        ids = entity_ids or []
        if not ids:
            return error_response(
                "docs_kg_query", "INVALID_ARGS", "mode='neighbors' requires entity_ids"
            )
        result = await _safe_call(
            bridge.get_neighbors,
            ids,
            hops=max(1, min(hops, 2)),
            limit=limit,
            predicate_filter=predicate_filter,
        )
    else:  # explain
        if not subject_id or not object_id:
            return error_response(
                "docs_kg_query",
                "INVALID_ARGS",
                "mode='explain' requires subject_id and object_id",
            )
        result = await _safe_call(
            bridge.explain_connection,
            subject_id,
            object_id,
            max_hops=max(1, min(max_hops, 3)),
        )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    if result is None:
        return success_response(
            "docs_kg_query",
            elapsed_ms,
            {"mode": mode, "available": False, "degraded": True},
        )
    return success_response("docs_kg_query", elapsed_ms, {"mode": mode, "result": result})


async def _safe_call(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a bridge read, returning None on failure (circuit open, etc.)."""
    try:
        return await fn(*args, **kwargs)
    except Exception:
        _logger.debug("kg_query_failed", exc_info=True)
        return None


def register(mcp_instance: "FastMCP", allowed_tools: frozenset[str]) -> None:  # noqa: UP037
    """Register docs_kg_query on the shared mcp instance when enabled."""
    if "docs_kg_query" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY, meta=_META_DEFERRED)(docs_kg_query)

"""Memory tool handlers for TappsMCP.

Functions are defined at module level (importable for tests) and
registered on the ``mcp`` instance via :func:`register`.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from tapps_mcp.server_helpers import (
    _get_memory_store,
    ensure_session_initialized,
    error_response,
    success_response,
)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from tapps_core.memory.store import MemoryStore

from mcp.types import ToolAnnotations

_ANNOTATIONS_MEMORY = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)

_ANNOTATIONS_MEMORY_READ = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

_VALID_ACTIONS = {"save", "get", "list", "delete", "search", "reinforce", "gc"}


async def tapps_memory(
    action: str,
    key: str = "",
    value: str = "",
    tier: str = "pattern",
    source: str = "agent",
    source_agent: str = "unknown",
    scope: str = "project",
    tags: str = "",
    branch: str = "",
    query: str = "",
    confidence: float = -1.0,
) -> dict[str, Any]:
    """Persist and retrieve project memories across sessions.

    Side effects: save/delete/reinforce/gc write to SQLite at .tapps-mcp/memory/.
    get/list/search are read-only.

    Memories are typed by tier (architectural, pattern, context), carry
    confidence scores and metadata, and persist in SQLite. Use this tool
    to save decisions, patterns, and context that should survive across
    sessions and be available to all MCP-connected agents.

    Args:
        action: One of "save", "get", "list", "delete", "search", "reinforce", "gc".
        key: Memory key (required for save/get/delete/reinforce). Lowercase slug.
        value: Memory content (required for save). Max 4096 chars.
        tier: "architectural", "pattern", or "context" (default: "pattern").
        source: "human", "agent", "inferred", or "system" (default: "agent").
        source_agent: Agent identifier (default: "unknown").
        scope: "project", "branch", or "session" (default: "project").
        tags: Comma-separated tags for categorization (optional).
        branch: Git branch name (required when scope="branch").
        query: Search query (for search action).
        confidence: Override default confidence 0.0-1.0 (optional, -1 for default).

    Actions:
        save: Store a new memory or update an existing one.
        get: Retrieve a memory by key.
        list: List all memories with optional filters.
        delete: Remove a memory by key.
        search: Full-text search across memories.
        reinforce: Boost confidence and reset decay clock for a memory (requires key).
        gc: Run garbage collection to archive stale/contradicted memories.
    """
    await ensure_session_initialized()
    _record_call("tapps_memory")

    t0 = time.perf_counter()

    if action not in _VALID_ACTIONS:
        return error_response(
            "tapps_memory",
            "invalid_action",
            f"Invalid action '{action}'. Must be one of: {', '.join(sorted(_VALID_ACTIONS))}",
        )

    try:
        store = _get_memory_store()
    except Exception as exc:
        return error_response(
            "tapps_memory",
            "store_init_failed",
            f"Failed to initialize memory store: {exc}",
        )

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    try:
        result_data = _dispatch_memory_action(
            store, action, key=key, value=value, tier=tier,
            source=source, source_agent=source_agent, scope=scope,
            tag_list=tag_list, branch=branch, query=query,
            confidence=confidence,
        )
    except Exception as exc:
        return error_response(
            "tapps_memory",
            "action_failed",
            f"Memory {action} failed: {exc}",
        )

    elapsed = int((time.perf_counter() - t0) * 1000)
    return success_response("tapps_memory", elapsed, result_data)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def _dispatch_memory_action(
    store: MemoryStore,
    action: str,
    *,
    key: str,
    value: str,
    tier: str,
    source: str,
    source_agent: str,
    scope: str,
    tag_list: list[str],
    branch: str,
    query: str,
    confidence: float,
) -> dict[str, Any]:
    """Route *action* to the appropriate handler."""
    handlers: dict[str, Any] = {
        "save": lambda: _handle_save(
            store, key, value, tier, source, source_agent,
            scope, tag_list, branch, confidence,
        ),
        "get": lambda: _handle_get(store, key, scope, branch),
        "list": lambda: _handle_list(store, tier, scope, tag_list),
        "delete": lambda: _handle_delete(store, key),
        "reinforce": lambda: _handle_reinforce(store, key),
        "gc": lambda: _handle_gc(store),
        "search": lambda: _handle_search(store, query, tag_list, tier, scope),
    }
    return handlers[action]()


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------


def _handle_save(
    store: MemoryStore,
    key: str,
    value: str,
    tier: str,
    source: str,
    source_agent: str,
    scope: str,
    tags: list[str],
    branch: str,
    confidence: float,
) -> dict[str, Any]:
    """Handle the save action."""
    if not key:
        return {"error": "missing_key", "message": "Key is required for save."}
    if not value:
        return {"error": "missing_value", "message": "Value is required for save."}

    result = store.save(
        key=key,
        value=value,
        tier=tier,
        source=source,
        source_agent=source_agent,
        scope=scope,
        tags=tags,
        branch=branch or None,
        confidence=confidence,
    )

    # store.save returns MemoryEntry on success, dict on error
    if isinstance(result, dict):
        return result

    return {
        "action": "save",
        "entry": result.model_dump(),
        "store_metadata": _store_metadata(store),
    }


def _handle_get(
    store: MemoryStore, key: str, scope: str, branch: str
) -> dict[str, Any]:
    """Handle the get action."""
    if not key:
        return {"error": "missing_key", "message": "Key is required for get."}

    entry = store.get(
        key, scope=scope or None, branch=branch or None
    )

    if entry is None:
        return {
            "action": "get",
            "found": False,
            "key": key,
            "store_metadata": _store_metadata(store),
        }

    return {
        "action": "get",
        "found": True,
        "entry": entry.model_dump(),
        "store_metadata": _store_metadata(store),
    }


def _handle_list(
    store: MemoryStore,
    tier: str,
    scope: str,
    tags: list[str],
) -> dict[str, Any]:
    """Handle the list action."""
    entries = store.list_all(
        tier=tier if tier != "pattern" else None,
        scope=scope if scope != "project" else None,
        tags=tags or None,
    )

    return {
        "action": "list",
        "entries": [e.model_dump() for e in entries],
        "count": len(entries),
        "store_metadata": _store_metadata(store),
    }


def _handle_delete(store: MemoryStore, key: str) -> dict[str, Any]:
    """Handle the delete action."""
    if not key:
        return {"error": "missing_key", "message": "Key is required for delete."}

    deleted = store.delete(key)
    return {
        "action": "delete",
        "deleted": deleted,
        "key": key,
        "store_metadata": _store_metadata(store),
    }


def _handle_search(
    store: MemoryStore,
    query: str,
    tags: list[str],
    tier: str,
    scope: str,
) -> dict[str, Any]:
    """Handle the search action."""
    if not query and not tags:
        return {
            "error": "missing_query",
            "message": "Query or tags required for search.",
        }

    results = store.search(
        query=query,
        tags=tags or None,
        tier=tier if tier != "pattern" else None,
        scope=scope if scope != "project" else None,
    )

    return {
        "action": "search",
        "results": [e.model_dump() for e in results],
        "count": len(results),
        "query": query,
        "store_metadata": _store_metadata(store),
    }


def _handle_reinforce(store: MemoryStore, key: str) -> dict[str, Any]:
    """Handle the reinforce action."""
    if not key:
        return {"error": "missing_key", "message": "Key is required for reinforce."}

    entry = store.get(key)
    if entry is None:
        return {
            "action": "reinforce",
            "found": False,
            "key": key,
            "store_metadata": _store_metadata(store),
        }

    old_confidence = entry.confidence

    from tapps_core.memory.decay import DecayConfig
    from tapps_core.memory.reinforcement import reinforce

    config = DecayConfig()
    updates = reinforce(entry, config)
    updated_entry = store.update_fields(key, **updates)

    return {
        "action": "reinforce",
        "found": True,
        "old_confidence": old_confidence,
        "new_confidence": updates["confidence"],
        "reinforce_count": updates["reinforce_count"],
        "entry": updated_entry.model_dump() if updated_entry else entry.model_dump(),
        "store_metadata": _store_metadata(store),
    }


def _handle_gc(store: MemoryStore) -> dict[str, Any]:
    """Handle the gc (garbage collection) action."""
    from tapps_core.memory.decay import DecayConfig
    from tapps_core.memory.gc import MemoryGarbageCollector

    config = DecayConfig()
    gc = MemoryGarbageCollector(config)

    snap = store.snapshot()
    candidates = gc.identify_candidates(snap.entries)

    archived_keys: list[str] = []
    for candidate in candidates:
        deleted = store.delete(candidate.key)
        if deleted:
            archived_keys.append(candidate.key)

    remaining = store.count()

    return {
        "action": "gc",
        "archived_count": len(archived_keys),
        "archived_keys": archived_keys,
        "remaining_count": remaining,
        "store_metadata": _store_metadata(store),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _store_metadata(store: MemoryStore) -> dict[str, Any]:
    """Build store metadata for response."""
    snap = store.snapshot()
    return {
        "total_count": snap.total_count,
        "tier_counts": snap.tier_counts,
    }


def _record_call(tool_name: str) -> None:
    """Record a tool call in the session checklist tracker."""
    try:
        from tapps_mcp.tools.checklist import CallTracker

        CallTracker.record(tool_name)
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(mcp_instance: FastMCP) -> None:
    """Register memory tools on the shared *mcp_instance*."""
    mcp_instance.tool(annotations=_ANNOTATIONS_MEMORY)(tapps_memory)

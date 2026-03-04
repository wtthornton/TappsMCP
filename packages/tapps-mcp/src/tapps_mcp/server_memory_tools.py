"""Memory tool handlers for TappsMCP.

Functions are defined at module level (importable for tests) and
registered on the ``mcp`` instance via :func:`register`.
"""

from __future__ import annotations

import dataclasses
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tapps_mcp.server_helpers import (
    _get_memory_store,
    ensure_session_initialized,
    error_response,
    success_response,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from mcp.server.fastmcp import FastMCP

    from tapps_core.memory.models import MemoryEntry
    from tapps_core.memory.store import MemoryStore

from mcp.types import ToolAnnotations

_ANNOTATIONS_MEMORY = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)

_VALID_ACTIONS = {
    "save", "get", "list", "delete", "search",
    "reinforce", "gc", "contradictions", "reseed",
    "import", "export",
}

# Curated response limits
_SEARCH_DEFAULT_LIMIT = 10
_LIST_DEFAULT_LIMIT = 50
_FULL_VALUE_THRESHOLD = 5
_SUMMARY_MAX_LEN = 80


# ---------------------------------------------------------------------------
# Typed parameter bag — eliminates **kwargs: Any in dispatch
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class _Params:
    """Immutable bag of parsed tool parameters passed to action handlers."""

    key: str
    value: str
    tier: str
    source: str
    source_agent: str
    scope: str
    tag_list: list[str]
    branch: str
    query: str
    confidence: float
    ranked: bool
    limit: int
    include_summary: bool
    file_path: str
    overwrite: bool


# ---------------------------------------------------------------------------
# Public MCP tool
# ---------------------------------------------------------------------------


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
    ranked: bool = True,
    limit: int = 0,
    include_summary: bool = True,
    file_path: str = "",
    overwrite: bool = False,
) -> dict[str, Any]:
    """Persist and retrieve project memories across sessions.

    Side effects: save/delete/reinforce/gc write to SQLite at .tapps-mcp/memory/.
    get/list/search are read-only.

    Memories are typed by tier (architectural, pattern, context), carry
    confidence scores and metadata, and persist in SQLite. Use this tool
    to save decisions, patterns, and context that should survive across
    sessions and be available to all MCP-connected agents.

    Args:
        action: One of "save", "get", "list", "delete", "search", "reinforce", "gc",
            "contradictions", "reseed", "import", "export".
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
        ranked: When True (default), search returns BM25-ranked results with scores.
        limit: Max results for search/list (0 = use defaults: 10 for search, 50 for list).
        include_summary: When True (default), list/search include one-line summaries.
        file_path: File path for import/export actions.
        overwrite: When True, import overwrites existing keys (default: False).

    Actions:
        save: Store a new memory or update an existing one.
        get: Retrieve a memory by key.
        list: List all memories with optional filters.
        delete: Remove a memory by key.
        search: Full-text search across memories.
        reinforce: Boost confidence and reset decay clock for a memory (requires key).
        gc: Run garbage collection to archive stale/contradicted memories.
        contradictions: Detect memories that contradict observable project state.
        reseed: Re-seed memory from project profile (only updates auto-seeded entries).
        import: Import memories from a JSON file (requires file_path).
        export: Export memories to a JSON file (optional file_path, tier, scope filters).
    """
    await ensure_session_initialized()
    _record_call("tapps_memory")

    t0 = time.perf_counter()

    if action not in _VALID_ACTIONS:
        return error_response(
            "tapps_memory",
            "invalid_action",
            f"Invalid action '{action}'. "
            f"Must be one of: {', '.join(sorted(_VALID_ACTIONS))}",
        )

    try:
        store = _get_memory_store()
    except Exception as exc:
        return error_response(
            "tapps_memory", "store_init_failed",
            f"Failed to initialize memory store: {exc}",
        )

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    params = _Params(
        key=key, value=value, tier=tier, source=source,
        source_agent=source_agent, scope=scope, tag_list=tag_list,
        branch=branch, query=query, confidence=confidence,
        ranked=ranked, limit=limit, include_summary=include_summary,
        file_path=file_path, overwrite=overwrite,
    )

    try:
        result_data = _DISPATCH[action](store, params)
    except Exception as exc:
        return error_response(
            "tapps_memory", "action_failed",
            f"Memory {action} failed: {exc}",
        )

    elapsed = int((time.perf_counter() - t0) * 1000)
    return success_response("tapps_memory", elapsed, result_data)


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------


def _handle_save(store: MemoryStore, p: _Params) -> dict[str, Any]:
    """Handle the save action."""
    if not p.key:
        return {"error": "missing_key", "message": "Key is required for save."}
    if not p.value:
        return {"error": "missing_value", "message": "Value is required for save."}

    result = store.save(
        key=p.key, value=p.value, tier=p.tier, source=p.source,
        source_agent=p.source_agent, scope=p.scope, tags=p.tag_list,
        branch=p.branch or None, confidence=p.confidence,
    )

    if isinstance(result, dict):
        return result

    return {
        "action": "save",
        "entry": result.model_dump(),
        "store_metadata": _store_metadata(store),
    }


def _handle_get(store: MemoryStore, p: _Params) -> dict[str, Any]:
    """Handle the get action."""
    if not p.key:
        return {"error": "missing_key", "message": "Key is required for get."}

    entry = store.get(p.key, scope=p.scope or None, branch=p.branch or None)

    if entry is None:
        return {
            "action": "get",
            "found": False,
            "key": p.key,
            "store_metadata": _store_metadata(store),
        }

    return {
        "action": "get",
        "found": True,
        "entry": entry.model_dump(),
        "store_metadata": _store_metadata(store),
    }


def _handle_list(store: MemoryStore, p: _Params) -> dict[str, Any]:
    """Handle the list action with curated, outcome-oriented responses."""
    entries = store.list_all(
        tier=p.tier if p.tier != "pattern" else None,
        scope=p.scope if p.scope != "project" else None,
        tags=p.tag_list or None,
    )

    effective_limit = p.limit if p.limit > 0 else _LIST_DEFAULT_LIMIT
    total_count = len(entries)
    truncated = entries[:effective_limit]

    result_entries = _build_entry_list(truncated, p.include_summary)

    return {
        "action": "list",
        "entries": result_entries,
        "total_count": total_count,
        "returned_count": len(result_entries),
        "store_metadata": _store_metadata(store),
    }


def _handle_delete(store: MemoryStore, p: _Params) -> dict[str, Any]:
    """Handle the delete action."""
    if not p.key:
        return {"error": "missing_key", "message": "Key is required for delete."}

    deleted = store.delete(p.key)
    return {
        "action": "delete",
        "deleted": deleted,
        "key": p.key,
        "store_metadata": _store_metadata(store),
    }


def _handle_search(store: MemoryStore, p: _Params) -> dict[str, Any]:
    """Handle the search action with optional ranked BM25 scoring."""
    if not p.query and not p.tag_list:
        return {
            "error": "missing_query",
            "message": "Query or tags required for search.",
        }

    effective_limit = p.limit if p.limit > 0 else _SEARCH_DEFAULT_LIMIT

    if p.ranked and p.query:
        return _ranked_search(store, p.query, effective_limit, p.include_summary)

    # Unranked (legacy FTS5-only) search
    results = store.search(
        query=p.query,
        tags=p.tag_list or None,
        tier=p.tier if p.tier != "pattern" else None,
        scope=p.scope if p.scope != "project" else None,
    )

    truncated = results[:effective_limit]
    result_entries = _build_entry_list(truncated, p.include_summary)

    return {
        "action": "search",
        "ranked": False,
        "results": result_entries,
        "total_count": len(results),
        "returned_count": len(result_entries),
        "query": p.query,
        "store_metadata": _store_metadata(store),
    }


def _handle_reinforce(store: MemoryStore, p: _Params) -> dict[str, Any]:
    """Handle the reinforce action."""
    if not p.key:
        return {"error": "missing_key", "message": "Key is required for reinforce."}

    entry = store.get(p.key)
    if entry is None:
        return {
            "action": "reinforce",
            "found": False,
            "key": p.key,
            "store_metadata": _store_metadata(store),
        }

    old_confidence = entry.confidence

    from tapps_core.memory.decay import DecayConfig
    from tapps_core.memory.reinforcement import reinforce

    config = DecayConfig()
    updates = reinforce(entry, config)
    updated_entry = store.update_fields(p.key, **updates)

    return {
        "action": "reinforce",
        "found": True,
        "old_confidence": old_confidence,
        "new_confidence": updates["confidence"],
        "reinforce_count": updates["reinforce_count"],
        "entry": updated_entry.model_dump() if updated_entry else entry.model_dump(),
        "store_metadata": _store_metadata(store),
    }


def _handle_gc(store: MemoryStore, _p: _Params) -> dict[str, Any]:
    """Handle the gc (garbage collection) action."""
    from tapps_core.memory.decay import DecayConfig
    from tapps_core.memory.gc import MemoryGarbageCollector

    config = DecayConfig()
    gc_runner = MemoryGarbageCollector(config)

    snap = store.snapshot()
    candidates = gc_runner.identify_candidates(snap.entries)

    archived_keys: list[str] = []
    for candidate in candidates:
        deleted = store.delete(candidate.key)
        if deleted:
            archived_keys.append(candidate.key)

    return {
        "action": "gc",
        "archived_count": len(archived_keys),
        "archived_keys": archived_keys,
        "remaining_count": store.count(),
        "store_metadata": _store_metadata(store),
    }


def _handle_contradictions(store: MemoryStore, _p: _Params) -> dict[str, Any]:
    """Detect memories contradicting observable project state."""
    from tapps_core.config.settings import load_settings
    from tapps_core.memory.contradictions import ContradictionDetector
    from tapps_mcp.project.profiler import detect_project_profile

    settings = load_settings()
    profile = detect_project_profile(settings.project_root)
    detector = ContradictionDetector(settings.project_root)

    all_entries = store.list_all()
    contradictions = detector.detect_contradictions(all_entries, profile)

    for c in contradictions:
        store.update_fields(c.memory_key, contradicted=True)

    return {
        "action": "contradictions",
        "contradictions": [c.model_dump() for c in contradictions],
        "count": len(contradictions),
        "checked_count": len(all_entries),
        "store_metadata": _store_metadata(store),
    }


def _handle_reseed(store: MemoryStore, _p: _Params) -> dict[str, Any]:
    """Re-seed memory from project profile (auto-seeded entries only)."""
    from tapps_core.config.settings import load_settings
    from tapps_core.memory.seeding import reseed_from_profile
    from tapps_mcp.project.profiler import detect_project_profile

    settings = load_settings()
    profile = detect_project_profile(settings.project_root)
    result = reseed_from_profile(store, profile)

    return {
        "action": "reseed",
        **result,
        "store_metadata": _store_metadata(store),
    }


def _handle_import(store: MemoryStore, p: _Params) -> dict[str, Any]:
    """Import memories from a JSON file."""
    if not p.file_path:
        return {
            "error": "missing_file_path",
            "message": "file_path is required for import.",
        }

    from tapps_core.config.settings import load_settings
    from tapps_core.memory.io import import_memories
    from tapps_core.security.path_validator import PathValidator

    settings = load_settings()
    validator = PathValidator(settings.project_root)

    result = import_memories(
        store, Path(p.file_path), validator, overwrite=p.overwrite,
    )

    return {"action": "import", **result, "store_metadata": _store_metadata(store)}


def _handle_export(store: MemoryStore, p: _Params) -> dict[str, Any]:
    """Export memories to a JSON file."""
    from tapps_core.config.settings import load_settings
    from tapps_core.memory.io import export_memories
    from tapps_core.security.path_validator import PathValidator

    settings = load_settings()
    validator = PathValidator(settings.project_root)

    output = (
        Path(p.file_path) if p.file_path
        else settings.project_root / "memory-export.json"
    )

    result = export_memories(
        store, output, validator,
        tier=p.tier if p.tier != "pattern" else None,
        scope=p.scope if p.scope != "project" else None,
        min_confidence=p.confidence if p.confidence >= 0 else None,
    )

    return {"action": "export", **result, "store_metadata": _store_metadata(store)}


# ---------------------------------------------------------------------------
# Dispatch table — maps action names to handler functions
# ---------------------------------------------------------------------------

_DISPATCH: dict[str, Callable[[MemoryStore, _Params], dict[str, Any]]] = {
    "save": _handle_save,
    "get": _handle_get,
    "list": _handle_list,
    "delete": _handle_delete,
    "search": _handle_search,
    "reinforce": _handle_reinforce,
    "gc": _handle_gc,
    "contradictions": _handle_contradictions,
    "reseed": _handle_reseed,
    "import": _handle_import,
    "export": _handle_export,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ranked_search(
    store: MemoryStore,
    query: str,
    limit: int,
    include_summary: bool,
) -> dict[str, Any]:
    """Execute ranked BM25 search via MemoryRetriever."""
    from tapps_core.memory.retrieval import MemoryRetriever

    retriever = MemoryRetriever()
    scored = retriever.search(query, store, limit=limit)

    result_entries: list[dict[str, Any]] = []
    for i, sm in enumerate(scored):
        entry_data = (
            _summarize_entry(sm.entry)
            if include_summary and i >= _FULL_VALUE_THRESHOLD
            else sm.entry.model_dump()
        )
        result_entries.append({
            "entry": entry_data,
            "score": sm.score,
            "effective_confidence": sm.effective_confidence,
            "stale": sm.stale,
        })

    return {
        "action": "search",
        "ranked": True,
        "results": result_entries,
        "total_count": len(scored),
        "returned_count": len(result_entries),
        "query": query,
        "store_metadata": _store_metadata(store),
    }


def _store_metadata(store: MemoryStore) -> dict[str, Any]:
    """Build store metadata for response."""
    snap = store.snapshot()
    return {
        "total_count": snap.total_count,
        "tier_counts": snap.tier_counts,
    }


def _summarize_entry(entry: MemoryEntry) -> dict[str, Any]:
    """Build a summary-only dict for an entry (key, tier, summary, tags)."""
    value_str = entry.value if isinstance(entry.value, str) else str(entry.value)
    summary = (
        value_str[:_SUMMARY_MAX_LEN] + "..."
        if len(value_str) > _SUMMARY_MAX_LEN
        else value_str
    )
    return {
        "key": entry.key,
        "tier": entry.tier if isinstance(entry.tier, str) else entry.tier.value,
        "summary": summary,
        "tags": entry.tags,
        "confidence": entry.confidence,
    }


def _build_entry_list(
    entries: list[MemoryEntry],
    include_summary: bool,
) -> list[dict[str, Any]]:
    """Build entry list with optional summary truncation past threshold."""
    return [
        _summarize_entry(e) if include_summary and i >= _FULL_VALUE_THRESHOLD
        else e.model_dump()
        for i, e in enumerate(entries)
    ]


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

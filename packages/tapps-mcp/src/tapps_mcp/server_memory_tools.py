"""Memory tool handlers for TappsMCP.

Functions are defined at module level (importable for tests) and
registered on the ``mcp`` instance via :func:`register`.
"""

from __future__ import annotations

import dataclasses
import json
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

_VALUE_PREVIEW_LEN = 200

_VALID_ACTIONS = {
    "save",
    "save_bulk",
    "get",
    "list",
    "delete",
    "search",
    "reinforce",
    "gc",
    "contradictions",
    "reseed",
    "import",
    "export",
    "consolidate",
    "unconsolidate",
    "federate_register",
    "federate_publish",
    "federate_subscribe",
    "federate_sync",
    "federate_search",
    "federate_status",
    "index_session",
    "validate",
    "maintain",
}

# Async actions require special dispatch (doc lookups are async)
_ASYNC_ACTIONS = {"validate"}

_BULK_SAVE_MAX_ENTRIES = 50

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
    entries: str
    # Consolidation parameters (Epic 58, Story 58.4)
    entry_ids: list[str]
    dry_run: bool
    # Retrieval deduplication (Epic 58, Story 58.5)
    include_sources: bool
    # Federation parameters (Epic 64)
    project_id: str = ""
    sources: list[str] = dataclasses.field(default_factory=list)
    min_confidence: float = 0.5
    include_hub: bool = True
    # Validation parameters (Epic 62)
    stale_only: bool = False
    max_entries: int = 10
    # Export format parameters (Epic 65.2)
    export_format: str = "json"
    include_frontmatter: bool = True
    export_group_by: str = "tier"
    # Session index (Epic 65.10)
    include_session_index: bool = False
    session_id: str = ""
    chunks: str = ""


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
    entries: str = "",
    entry_ids: str = "",
    dry_run: bool = False,
    include_sources: bool = False,
    project_id: str = "",
    sources: str = "",
    min_confidence: float = 0.5,
    include_hub: bool = True,
    stale_only: bool = False,
    max_entries: int = 10,
    format: str = "json",  # noqa: A002
    include_frontmatter: bool = True,
    group_by: str = "tier",
    include_session_index: bool = False,
    session_id: str = "",
    chunks: str = "",
) -> dict[str, Any]:
    """Persist and retrieve project memories across sessions.

    Side effects: save/delete/reinforce/gc/consolidate write to SQLite at
    .tapps-mcp/memory/. get/list/search are read-only.

    Memories are typed by tier (architectural, pattern, context), carry
    confidence scores and metadata, and persist in SQLite. Use this tool
    to save decisions, patterns, and context that should survive across
    sessions and be available to all MCP-connected agents.

    Args:
        action: One of "save", "save_bulk", "get", "list", "delete", "search",
            "reinforce", "gc", "contradictions", "reseed", "import", "export",
            "consolidate", "unconsolidate".
        key: Memory key (required for save/get/delete/reinforce). Lowercase slug.
        value: Memory content (required for save). Max 4096 chars.
        tier: "architectural", "pattern", or "context" (default: "pattern").
        source: "human", "agent", "inferred", or "system" (default: "agent").
        source_agent: Agent identifier (default: "unknown").
        scope: "project", "branch", or "session" (default: "project").
        tags: Comma-separated tags for categorization (optional).
        branch: Git branch name (required when scope="branch").
        query: Search query (for search and consolidate actions).
        confidence: Override default confidence 0.0-1.0 (optional, -1 for default).
        ranked: When True (default), search returns BM25-ranked results with scores.
        limit: Max results for search/list (0 = use defaults: 10 for search, 50 for list).
        include_summary: When True (default), list/search include one-line summaries.
        file_path: File path for import/export actions.
        overwrite: When True, import overwrites existing keys (default: False).
        entries: JSON array of objects for save_bulk action. Each object must have
            "key" and "value", and may optionally include "tier", "tags", "scope".
            Maximum 50 entries per call.
        entry_ids: Comma-separated entry keys for consolidate action. If provided,
            consolidates these specific entries. If not provided, uses query to find
            similar entries.
        dry_run: When True, preview consolidation without making changes (default: False).
        include_sources: When True, search/list includes source entries of consolidated
            memories (default: False). By default, entries that were consolidated into
            other entries are filtered out to avoid duplicates. (Epic 58, Story 58.5)

    Actions:
        save: Store a new memory or update an existing one.
        save_bulk: Save multiple memories in one call (requires entries parameter).
        get: Retrieve a memory by key.
        list: List all memories with optional filters.
        delete: Remove a memory by key.
        search: Full-text search across memories.
        reinforce: Boost confidence and reset decay clock for a memory (requires key).
        gc: Run garbage collection to archive stale/contradicted memories.
        contradictions: Detect memories that contradict observable project state.
        reseed: Re-seed memory from project profile (only updates auto-seeded entries).
        import: Import memories from a JSON file (requires file_path).
        export: Export memories to JSON or Markdown (format: json|markdown, optional
            file_path, tier, scope filters, include_frontmatter, group_by).
        consolidate: Merge related entries into a consolidated entry with provenance.
            Use entry_ids for explicit keys or query to find similar entries.
            Use dry_run=True to preview. (Epic 58, Story 58.4)
        unconsolidate: Undo a consolidation. Restores source entries and removes the
            consolidated entry. Requires key of the consolidated entry. (Epic 58, Story 58.6)
        federate_register: Register this project in the federation hub for cross-project sharing.
            Optional project_id (auto-detected) and tags. (Epic 64)
        federate_publish: Publish shared-scope memories to the federation hub.
            Optional key list to publish specific entries. (Epic 64)
        federate_subscribe: Subscribe to memories from other projects.
            Requires sources (comma-separated project IDs). Optional tags, min_confidence. (Epic 64)
        federate_sync: Pull subscribed memories from the hub into local store. (Epic 64)
        federate_search: Search across local and federated memories. Uses query param. (Epic 64)
        federate_status: Show federation hub status and registered projects. (Epic 64)
        validate: Validate memories against authoritative documentation via Context7. (Epic 62)
            Params: key (single), query (search), stale_only, dry_run, max_entries.
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
    entry_id_list = [e.strip() for e in entry_ids.split(",") if e.strip()] if entry_ids else []
    source_list = [s.strip() for s in sources.split(",") if s.strip()] if sources else []

    params = _Params(
        key=key,
        value=value,
        tier=tier,
        source=source,
        source_agent=source_agent,
        scope=scope,
        tag_list=tag_list,
        branch=branch,
        query=query,
        confidence=confidence,
        ranked=ranked,
        limit=limit,
        include_summary=include_summary,
        file_path=file_path,
        overwrite=overwrite,
        entries=entries,
        entry_ids=entry_id_list,
        dry_run=dry_run,
        include_sources=include_sources,
        project_id=project_id,
        sources=source_list,
        min_confidence=min_confidence,
        include_hub=include_hub,
        stale_only=stale_only,
        max_entries=max_entries,
        export_format=format,
        include_frontmatter=include_frontmatter,
        export_group_by=group_by,
        include_session_index=include_session_index,
        session_id=session_id,
        chunks=chunks,
    )

    try:
        if action in _ASYNC_ACTIONS:
            result_data = await _ASYNC_DISPATCH[action](store, params)
        else:
            result_data = _DISPATCH[action](store, params)
    except Exception as exc:
        return error_response(
            "tapps_memory",
            "action_failed",
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
        key=p.key,
        value=p.value,
        tier=p.tier,
        source=p.source,
        source_agent=p.source_agent,
        scope=p.scope,
        tags=p.tag_list,
        branch=p.branch or None,
        confidence=p.confidence,
    )

    if isinstance(result, dict):
        return result

    return {
        "action": "save",
        "entry": result.model_dump(),
        "store_metadata": _store_metadata(store),
    }


def _handle_save_bulk(store: MemoryStore, p: _Params) -> dict[str, Any]:
    """Handle the save_bulk action — save multiple entries in one call."""
    if not p.entries:
        return {
            "error": "missing_entries",
            "message": "entries parameter is required for save_bulk.",
        }

    try:
        parsed = json.loads(p.entries)
    except (json.JSONDecodeError, TypeError) as exc:
        return {
            "error": "invalid_json",
            "message": f"Failed to parse entries as JSON: {exc}",
        }

    if not isinstance(parsed, list):
        return {"error": "invalid_format", "message": "entries must be a JSON array."}

    if len(parsed) > _BULK_SAVE_MAX_ENTRIES:
        return {
            "error": "too_many_entries",
            "message": (f"Maximum {_BULK_SAVE_MAX_ENTRIES} entries per call, got {len(parsed)}."),
        }

    saved = 0
    skipped = 0
    errors: list[dict[str, str]] = []

    for i, entry in enumerate(parsed):
        if not isinstance(entry, dict):
            errors.append({"index": str(i), "error": "Entry must be an object."})
            skipped += 1
            continue

        e_key = entry.get("key", "")
        e_value = entry.get("value", "")
        if not e_key:
            errors.append({"index": str(i), "error": "Missing required field 'key'."})
            skipped += 1
            continue
        if not e_value:
            errors.append(
                {
                    "index": str(i),
                    "key": e_key,
                    "error": "Missing required field 'value'.",
                }
            )
            skipped += 1
            continue

        e_tier = entry.get("tier", p.tier)
        e_scope = entry.get("scope", p.scope)
        e_tags_raw = entry.get("tags", "")
        e_tags = (
            [t.strip() for t in e_tags_raw.split(",") if t.strip()]
            if isinstance(e_tags_raw, str) and e_tags_raw
            else (e_tags_raw if isinstance(e_tags_raw, list) else [])
        )

        try:
            result = store.save(
                key=e_key,
                value=e_value,
                tier=e_tier,
                source=p.source,
                source_agent=p.source_agent,
                scope=e_scope,
                tags=e_tags,
                branch=p.branch or None,
                confidence=p.confidence,
            )
            if isinstance(result, dict) and "error" in result:
                errors.append({"key": e_key, "error": result.get("message", str(result))})
                skipped += 1
            else:
                saved += 1
        except Exception as exc:
            errors.append({"key": e_key, "error": str(exc)})
            skipped += 1

    return {
        "action": "save_bulk",
        "saved": saved,
        "skipped": skipped,
        "errors": errors,
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

    result: dict[str, Any] = {
        "action": "get",
        "found": True,
        "entry": entry.model_dump(),
        "store_metadata": _store_metadata(store),
    }

    # Provenance: include source entries for consolidated entries (Epic 58.6)
    provenance = _get_provenance(store, entry)
    if provenance:
        result["provenance"] = provenance

    return result


def _handle_list(store: MemoryStore, p: _Params) -> dict[str, Any]:
    """Handle the list action with curated, outcome-oriented responses."""
    entries = store.list_all(
        tier=p.tier if p.tier != "pattern" else None,
        scope=p.scope if p.scope != "project" else None,
        tags=p.tag_list or None,
    )

    # Filter source entries of consolidated memories (Epic 58.5)
    if not p.include_sources:
        entries = _filter_consolidated_sources(entries)

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
        return _ranked_search(
            store,
            p.query,
            effective_limit,
            p.include_summary,
            p.include_sources,
            p.include_session_index,
        )

    # Unranked (legacy FTS5-only) search
    results = store.search(
        query=p.query,
        tags=p.tag_list or None,
        tier=p.tier if p.tier != "pattern" else None,
        scope=p.scope if p.scope != "project" else None,
    )

    # Filter source entries of consolidated memories (Epic 58.5)
    if not p.include_sources:
        results = _filter_consolidated_sources(results)

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
        store,
        Path(p.file_path),
        validator,
        overwrite=p.overwrite,
    )

    return {"action": "import", **result, "store_metadata": _store_metadata(store)}


def _handle_export(store: MemoryStore, p: _Params) -> dict[str, Any]:
    """Export memories to JSON or Markdown (Epic 65.2)."""
    from tapps_core.config.settings import load_settings
    from tapps_core.memory.io import export_memories
    from tapps_core.security.path_validator import PathValidator

    fmt = (p.export_format or "json").lower()
    if fmt not in ("json", "markdown"):
        return {
            "error": "invalid_format",
            "message": f'format must be "json" or "markdown", got {p.export_format!r}.',
        }

    group_by_val = (p.export_group_by or "tier").lower()
    if group_by_val not in ("tier", "tag", "none"):
        group_by_val = "tier"

    settings = load_settings()
    validator = PathValidator(settings.project_root)

    default_name = "memory-export.md" if fmt == "markdown" else "memory-export.json"
    output = Path(p.file_path) if p.file_path else settings.project_root / default_name

    result = export_memories(
        store,
        output,
        validator,
        tier=p.tier if p.tier != "pattern" else None,
        scope=p.scope if p.scope != "project" else None,
        min_confidence=p.confidence if p.confidence >= 0 else None,
        export_format=fmt,
        include_frontmatter=p.include_frontmatter,
        group_by=group_by_val,
    )

    return {"action": "export", **result, "store_metadata": _store_metadata(store)}


def _handle_consolidate(store: MemoryStore, p: _Params) -> dict[str, Any]:
    """Handle the consolidate action (Epic 58, Story 58.4).

    Consolidates related memory entries into a single entry with provenance.
    Supports explicit entry_ids or query-based discovery of similar entries.
    """
    from tapps_core.memory.consolidation import (
        consolidate,
        detect_consolidation_reason,
    )
    from tapps_core.memory.similarity import find_consolidation_groups

    # Determine entries to consolidate
    if p.entry_ids:
        # Explicit entry IDs provided
        entries_to_consolidate = _get_entries_by_ids(store, p.entry_ids)
        if isinstance(entries_to_consolidate, dict):
            return entries_to_consolidate  # Error response
        discovery_method = "explicit"
    elif p.query:
        # Query-based discovery
        entries_to_consolidate = _find_entries_by_query(store, p.query, p.limit)
        if isinstance(entries_to_consolidate, dict):
            return entries_to_consolidate  # Error response
        discovery_method = "query"
    else:
        # Auto-discover consolidation groups
        all_entries = store.list_all()
        active_entries = [
            e
            for e in all_entries
            if not getattr(e, "is_consolidated", False) and not e.contradicted
        ]

        if len(active_entries) < 2:  # noqa: PLR2004
            return {
                "action": "consolidate",
                "consolidated": False,
                "reason": "not_enough_entries",
                "message": "Need at least 2 active entries to consolidate.",
                "store_metadata": _store_metadata(store),
            }

        # Find the first consolidation group
        groups = find_consolidation_groups(active_entries, min_group_size=2)
        if not groups:
            return {
                "action": "consolidate",
                "consolidated": False,
                "reason": "no_similar_entries",
                "message": "No similar entries found to consolidate.",
                "store_metadata": _store_metadata(store),
            }

        # Use the first group
        entry_by_key = {e.key: e for e in active_entries}
        entries_to_consolidate = [entry_by_key[k] for k in groups[0] if k in entry_by_key]
        discovery_method = "auto"

    if len(entries_to_consolidate) < 2:  # noqa: PLR2004
        return {
            "action": "consolidate",
            "consolidated": False,
            "reason": "not_enough_entries",
            "message": "Need at least 2 entries to consolidate.",
            "store_metadata": _store_metadata(store),
        }

    # Detect consolidation reason
    reason = detect_consolidation_reason(
        entries_to_consolidate[0],
        entries_to_consolidate[1:],
    )

    # Dry run - preview without making changes
    if p.dry_run:
        return {
            "action": "consolidate",
            "dry_run": True,
            "would_consolidate": True,
            "source_entries": [
                {"key": e.key, "tier": e.tier.value if hasattr(e.tier, "value") else str(e.tier)}
                for e in entries_to_consolidate
            ],
            "source_count": len(entries_to_consolidate),
            "consolidation_reason": reason.value,
            "discovery_method": discovery_method,
            "preview_key": f"consolidated-preview-{len(entries_to_consolidate)}",
            "store_metadata": _store_metadata(store),
        }

    # Perform consolidation
    try:
        consolidated = consolidate(entries_to_consolidate, reason=reason)
    except ValueError as exc:
        return {
            "action": "consolidate",
            "consolidated": False,
            "reason": "consolidation_failed",
            "message": str(exc),
            "store_metadata": _store_metadata(store),
        }

    # Save consolidated entry
    source_keys = [e.key for e in entries_to_consolidate]
    c = consolidated  # Shorter alias for line length
    tier_val = c.tier.value if hasattr(c.tier, "value") else str(c.tier)
    source_val = c.source.value if hasattr(c.source, "value") else str(c.source)
    scope_val = c.scope.value if hasattr(c.scope, "value") else str(c.scope)
    store.save(
        key=c.key,
        value=c.value,
        tier=tier_val,
        source=source_val,
        source_agent=c.source_agent,
        scope=scope_val,
        tags=c.tags,
        confidence=c.confidence,
        skip_consolidation=True,  # Avoid infinite recursion
    )

    # Mark source entries as consolidated (not deleted - retained for provenance)
    for key in source_keys:
        if key != consolidated.key:
            store.update_fields(
                key,
                contradicted=True,
                contradiction_reason=f"consolidated into {consolidated.key}",
            )

    return {
        "action": "consolidate",
        "consolidated": True,
        "consolidated_key": consolidated.key,
        "source_keys": source_keys,
        "source_count": len(source_keys),
        "consolidation_reason": reason.value,
        "discovery_method": discovery_method,
        "confidence": round(consolidated.confidence, 3),
        "store_metadata": _store_metadata(store),
    }


def _handle_unconsolidate(store: MemoryStore, p: _Params) -> dict[str, Any]:
    """Handle the unconsolidate action (Epic 58, Story 58.6).

    Restores source entries that were consolidated into the given entry,
    then removes the consolidated entry itself.
    """
    if not p.key:
        return {"error": "missing_key", "message": "Key is required for unconsolidate."}

    # Verify the target entry exists
    target = store.get(p.key)
    if target is None:
        return {
            "action": "unconsolidate",
            "undone": False,
            "reason": "entry_not_found",
            "message": f"Entry '{p.key}' not found.",
            "store_metadata": _store_metadata(store),
        }

    # Find source entries by scanning for contradiction_reason referencing this key
    marker = f"consolidated into {p.key}"
    all_entries = store.list_all()
    source_entries = [
        e
        for e in all_entries
        if e.contradicted and e.contradiction_reason and marker in e.contradiction_reason
    ]

    if not source_entries:
        return {
            "action": "unconsolidate",
            "undone": False,
            "reason": "not_a_consolidated_entry",
            "message": (
                f"No source entries found for '{p.key}'. "
                "This may not be a consolidated entry, or sources were deleted."
            ),
            "store_metadata": _store_metadata(store),
        }

    # Restore source entries (clear contradicted flag)
    restored_keys: list[str] = []
    for entry in source_entries:
        updated = store.update_fields(
            entry.key,
            contradicted=False,
            contradiction_reason=None,
        )
        if updated is not None:
            restored_keys.append(entry.key)

    # Delete the consolidated entry
    deleted = store.delete(p.key)

    return {
        "action": "unconsolidate",
        "undone": True,
        "consolidated_key": p.key,
        "consolidated_entry_deleted": deleted,
        "restored_keys": restored_keys,
        "restored_count": len(restored_keys),
        "store_metadata": _store_metadata(store),
    }


def _get_entries_by_ids(
    store: MemoryStore,
    entry_ids: list[str],
) -> list[MemoryEntry] | dict[str, Any]:
    """Get entries by explicit IDs, returning error dict if any not found."""
    entries: list[MemoryEntry] = []
    not_found: list[str] = []

    for key in entry_ids:
        entry = store.get(key)
        if entry is None:
            not_found.append(key)
        else:
            entries.append(entry)

    if not_found:
        return {
            "action": "consolidate",
            "consolidated": False,
            "reason": "entries_not_found",
            "message": f"Entries not found: {', '.join(not_found)}",
            "not_found": not_found,
            "store_metadata": _store_metadata(store),
        }

    return entries


def _find_entries_by_query(
    store: MemoryStore,
    query: str,
    limit: int,
) -> list[MemoryEntry] | dict[str, Any]:
    """Find entries by query for consolidation."""
    from tapps_core.config.settings import load_settings
    from tapps_core.memory.reranker import get_reranker
    from tapps_core.memory.retrieval import MemoryRetriever
    from tapps_core.memory.similarity import find_consolidation_groups

    settings = load_settings()
    rr = settings.memory.reranker
    reranker = (
        get_reranker(
            enabled=rr.enabled,
            provider=rr.provider,
            top_k=rr.top_k,
            api_key=rr.api_key,
        )
        if rr.enabled
        else None
    )
    retriever = MemoryRetriever(
        semantic_enabled=settings.memory.semantic_search.enabled,
        hybrid_config=settings.memory.hybrid,
        reranker=reranker,
        reranker_enabled=rr.enabled,
    )
    effective_limit = limit if limit > 0 else _SEARCH_DEFAULT_LIMIT

    # Search for related entries
    scored = retriever.search(query, store, limit=effective_limit)

    if len(scored) < 2:  # noqa: PLR2004
        return {
            "action": "consolidate",
            "consolidated": False,
            "reason": "not_enough_results",
            "message": f"Query returned {len(scored)} results, need at least 2.",
            "query": query,
            "store_metadata": _store_metadata(store),
        }

    # Get actual entries
    entries = [sm.entry for sm in scored]

    # Find consolidation groups within the search results
    groups = find_consolidation_groups(entries, min_group_size=2)
    if not groups:
        # If no groups found, use all search results
        return entries

    # Return entries from the first (largest) group
    entry_by_key = {e.key: e for e in entries}
    return [entry_by_key[k] for k in groups[0] if k in entry_by_key]


# ---------------------------------------------------------------------------
# Federation action handlers (Epic 64)
# ---------------------------------------------------------------------------


def _handle_index_session(store: MemoryStore, p: _Params) -> dict[str, Any]:
    """Handle index_session action (Epic 65.10). Store session chunks for search."""
    from tapps_core.config.settings import load_settings
    from tapps_core.memory.session_index import index_session as do_index_session

    if not p.session_id or not p.session_id.strip():
        return {"error": "missing_session_id", "message": "session_id is required."}
    if not p.chunks:
        return {"error": "missing_chunks", "message": "chunks is required (JSON array of strings)."}
    try:
        parsed = json.loads(p.chunks)
    except (json.JSONDecodeError, TypeError) as exc:
        return {"error": "invalid_chunks", "message": f"chunks must be JSON array of strings: {exc}"}
    if not isinstance(parsed, list):
        return {"error": "invalid_chunks", "message": "chunks must be a JSON array."}
    chunks_list = [str(c) for c in parsed if c]
    if not chunks_list:
        return {"action": "index_session", "chunks_stored": 0, "session_id": p.session_id}

    settings = load_settings()
    if not settings.memory.session_index.enabled:
        return {
            "error": "session_index_disabled",
            "message": "Session indexing is disabled. Set memory.session_index.enabled: true in .tapps-mcp.yaml.",
        }

    si = settings.memory.session_index
    count = do_index_session(
        store.project_root,
        p.session_id,
        chunks_list,
        max_chunks=si.max_chunks_per_session,
        max_chars_per_chunk=si.max_chars_per_chunk,
    )
    return {
        "action": "index_session",
        "session_id": p.session_id,
        "chunks_stored": count,
        "chunks_input": len(chunks_list),
        "store_metadata": _store_metadata(store),
    }


def _handle_federate_register(store: MemoryStore, params: _Params) -> dict[str, Any]:
    """Register this project in the federation hub."""
    from tapps_core.config.settings import load_settings
    from tapps_core.memory.federation import register_project

    settings = load_settings()
    pid = params.project_id or settings.project_root.name.lower().replace(" ", "-")
    tags = params.tag_list or []

    config = register_project(
        project_id=pid,
        project_root=str(settings.project_root),
        tags=tags,
    )

    return {
        "action": "federate_register",
        "project_id": pid,
        "registered_projects": len(config.projects),
        "tags": tags,
    }


def _handle_federate_publish(store: MemoryStore, params: _Params) -> dict[str, Any]:
    """Publish shared-scope memories to the federation hub."""
    from tapps_core.config.settings import load_settings
    from tapps_core.memory.federation import FederatedStore, sync_to_hub

    settings = load_settings()
    pid = params.project_id or settings.project_root.name.lower().replace(" ", "-")
    keys = [params.key] if params.key else None

    federated = FederatedStore()
    try:
        result = sync_to_hub(
            store=store,
            federated_store=federated,
            project_id=pid,
            project_root=str(settings.project_root),
            keys=keys,
        )
    finally:
        federated.close()

    return {
        "action": "federate_publish",
        "project_id": pid,
        **result,
    }


def _handle_federate_subscribe(store: MemoryStore, params: _Params) -> dict[str, Any]:
    """Subscribe to memories from other projects."""
    from tapps_core.config.settings import load_settings
    from tapps_core.memory.federation import add_subscription

    settings = load_settings()
    pid = params.project_id or settings.project_root.name.lower().replace(" ", "-")

    if not params.sources:
        return {"error": "missing_sources", "message": "sources parameter required for subscribe."}

    config = add_subscription(
        subscriber=pid,
        sources=params.sources,
        tag_filter=params.tag_list or None,
        min_confidence=params.min_confidence,
    )

    return {
        "action": "federate_subscribe",
        "subscriber": pid,
        "sources": params.sources,
        "tag_filter": params.tag_list,
        "subscriptions": len(config.subscriptions),
    }


def _handle_federate_sync(store: MemoryStore, params: _Params) -> dict[str, Any]:
    """Pull subscribed memories from the federation hub."""
    from tapps_core.config.settings import load_settings
    from tapps_core.memory.federation import FederatedStore, sync_from_hub

    settings = load_settings()
    pid = params.project_id or settings.project_root.name.lower().replace(" ", "-")

    federated = FederatedStore()
    try:
        result = sync_from_hub(
            store=store,
            federated_store=federated,
            project_id=pid,
        )
    finally:
        federated.close()

    return {
        "action": "federate_sync",
        "project_id": pid,
        **result,
    }


def _handle_federate_search(store: MemoryStore, params: _Params) -> dict[str, Any]:
    """Search across local and federated memories."""
    from tapps_core.config.settings import load_settings
    from tapps_core.memory.federation import FederatedStore, federated_search

    if not params.query:
        return {
            "error": "missing_query",
            "message": "query parameter required for federate_search.",
        }

    settings = load_settings()
    pid = params.project_id or settings.project_root.name.lower().replace(" ", "-")
    result_limit = params.limit if params.limit > 0 else 20

    federated = FederatedStore()
    try:
        results = federated_search(
            query=params.query,
            local_store=store,
            federated_store=federated,
            project_id=pid,
            include_local=True,
            include_hub=params.include_hub,
            max_results=result_limit,
        )
    finally:
        federated.close()

    return {
        "action": "federate_search",
        "query": params.query,
        "result_count": len(results),
        "results": [
            {
                "key": r.key,
                "value": (
                    r.value[:_VALUE_PREVIEW_LEN]
                    + ("..." if len(r.value) > _VALUE_PREVIEW_LEN else "")
                ),
                "source": r.source,
                "project_id": r.project_id,
                "confidence": round(r.confidence, 3),
                "tier": r.tier,
                "tags": r.tags,
                "relevance_score": round(r.relevance_score, 3),
            }
            for r in results
        ],
    }


def _handle_federate_status(store: MemoryStore, params: _Params) -> dict[str, Any]:
    """Show federation hub status."""
    from tapps_core.memory.federation import FederatedStore, load_federation_config

    config = load_federation_config()
    federated = FederatedStore()
    try:
        stats = federated.get_stats()
    finally:
        federated.close()

    return {
        "action": "federate_status",
        "registered_projects": [
            {
                "project_id": p.project_id,
                "project_root": p.project_root,
                "tags": p.tags,
                "registered_at": p.registered_at,
            }
            for p in config.projects
        ],
        "subscriptions": [
            {
                "subscriber": s.subscriber,
                "sources": s.sources,
                "tag_filter": s.tag_filter,
                "min_confidence": s.min_confidence,
            }
            for s in config.subscriptions
        ],
        "hub_stats": stats,
    }


def _handle_maintain(store: MemoryStore, _p: _Params) -> dict[str, Any]:
    """Run memory maintenance: GC + consolidation + deduplication (Epic 65.15)."""
    gc_archived = 0
    consolidated = 0
    deduplicated = 0

    # Run GC (same approach as _handle_gc)
    try:
        from tapps_core.memory.decay import DecayConfig
        from tapps_core.memory.gc import MemoryGarbageCollector

        config = DecayConfig()
        gc_runner = MemoryGarbageCollector(config)
        snap = store.snapshot()
        candidates = gc_runner.identify_candidates(snap.entries)
        for candidate in candidates:
            if store.delete(candidate.key):
                gc_archived += 1
    except Exception:
        pass

    # Run consolidation scan
    try:
        from tapps_core.memory.auto_consolidation import run_periodic_consolidation_scan

        consol_result = run_periodic_consolidation_scan(store)
        consolidated = getattr(consol_result, "groups_formed", 0) if consol_result else 0
    except Exception:
        pass

    # Deduplication: find exact duplicate values and merge
    try:
        snapshot = store.snapshot()
        seen_values: dict[str, str] = {}  # value hash -> first key
        for entry in snapshot.entries:
            val_hash = entry.value.strip().lower()
            if val_hash in seen_values and seen_values[val_hash] != entry.key:
                store.delete(entry.key)
                deduplicated += 1
            else:
                seen_values[val_hash] = entry.key
    except Exception:
        pass

    return {
        "action": "maintain",
        "gc_archived": gc_archived,
        "consolidated": consolidated,
        "deduplicated": deduplicated,
        "store_metadata": _store_metadata(store),
    }


# ---------------------------------------------------------------------------
# Dispatch table — maps action names to handler functions
# ---------------------------------------------------------------------------

_DISPATCH: dict[str, Callable[[MemoryStore, _Params], dict[str, Any]]] = {
    "save": _handle_save,
    "save_bulk": _handle_save_bulk,
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
    "consolidate": _handle_consolidate,
    "unconsolidate": _handle_unconsolidate,
    "federate_register": _handle_federate_register,
    "federate_publish": _handle_federate_publish,
    "federate_subscribe": _handle_federate_subscribe,
    "federate_sync": _handle_federate_sync,
    "federate_search": _handle_federate_search,
    "federate_status": _handle_federate_status,
    "index_session": _handle_index_session,
    "maintain": _handle_maintain,
}


# ---------------------------------------------------------------------------
# Async action handlers (Epic 62 — doc validation requires async lookups)
# ---------------------------------------------------------------------------


async def _handle_validate(store: MemoryStore, params: _Params) -> dict[str, Any]:
    """Validate memory entries against authoritative documentation."""
    from tapps_core.knowledge.lookup import LookupEngine
    from tapps_core.memory.doc_validation import MemoryDocValidator

    from tapps_core.config.settings import load_settings

    settings = load_settings()
    lookup = LookupEngine(settings=settings)
    validator = MemoryDocValidator(lookup)

    # Determine which entries to validate
    if params.key:
        entry = store.get(params.key)
        if entry is None:
            return {"action": "validate", "error": f"Key '{params.key}' not found"}
        report = await validator.validate_batch([entry])
    elif params.query:
        entries = store.search(params.query)[: params.max_entries]
        report = await validator.validate_batch(entries)
    elif params.stale_only:
        all_entries = list(store.list_all().values())
        report = await validator.validate_stale(
            all_entries,
            confidence_threshold=params.min_confidence,
            max_entries=params.max_entries,
        )
    else:
        # Validate all (up to max_entries)
        all_entries = list(store.list_all().values())[: params.max_entries]
        report = await validator.validate_batch(all_entries)

    # Apply results if not dry_run
    apply_result = await validator.apply_results(
        report,
        store,
        dry_run=params.dry_run,
    )

    # Format response
    entry_summaries = []
    for ev in report.entries:
        summary: dict[str, Any] = {
            "key": ev.entry_key,
            "status": ev.overall_status.value,
            "reason": ev.reason,
        }
        if ev.claims:
            summary["claims"] = len(ev.claims)
            summary["libraries"] = [c.library for c in ev.claims]
        if ev.alignments:
            best = max(ev.alignments, key=lambda a: a.similarity_score)
            summary["best_similarity"] = best.similarity_score
            if best.matched_snippet:
                summary["matched_snippet"] = best.matched_snippet[:120]
        if ev.confidence_adjustment != 0.0:
            summary["confidence_delta"] = ev.confidence_adjustment
        entry_summaries.append(summary)

    return {
        "action": "validate",
        "report": {
            "validated": report.validated,
            "flagged": report.flagged,
            "inconclusive": report.inconclusive,
            "skipped": report.skipped,
        },
        "entries": entry_summaries,
        "applied": not params.dry_run,
        "apply_summary": {
            "boosted": apply_result.boosted,
            "penalised": apply_result.penalised,
            "unchanged": apply_result.unchanged,
            "tags_added": apply_result.tags_added,
        },
        "timing_ms": report.elapsed_ms,
    }


_ASYNC_DISPATCH: dict[str, Any] = {
    "validate": _handle_validate,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ranked_search(
    store: MemoryStore,
    query: str,
    limit: int,
    include_summary: bool,
    include_sources: bool = False,
    include_session_index: bool = False,
) -> dict[str, Any]:
    """Execute ranked BM25 search via MemoryRetriever (hybrid + reranker when enabled).

    When include_session_index and memory.session_index.enabled, merges session
    index hits with memory results (Epic 65.10).
    """
    from tapps_core.config.settings import load_settings
    from tapps_core.memory.reranker import get_reranker
    from tapps_core.memory.retrieval import MemoryRetriever

    settings = load_settings()
    rr = settings.memory.reranker
    reranker = (
        get_reranker(
            enabled=rr.enabled,
            provider=rr.provider,
            top_k=rr.top_k,
            api_key=rr.api_key,
        )
        if rr.enabled
        else None
    )
    retriever = MemoryRetriever(
        semantic_enabled=settings.memory.semantic_search.enabled,
        hybrid_config=settings.memory.hybrid,
        reranker=reranker,
        reranker_enabled=rr.enabled,
    )
    scored = retriever.search(query, store, limit=limit, include_sources=include_sources)

    result_entries: list[dict[str, Any]] = []
    for i, sm in enumerate(scored):
        entry_data = (
            _summarize_entry(sm.entry)
            if include_summary and i >= _FULL_VALUE_THRESHOLD
            else sm.entry.model_dump()
        )
        result_entries.append(
            {
                "entry": entry_data,
                "score": sm.score,
                "effective_confidence": sm.effective_confidence,
                "stale": sm.stale,
                "source": "memory",
            }
        )

    # Epic 65.10: optionally include session index hits
    if include_session_index and settings.memory.session_index.enabled:
        from tapps_core.memory.session_index import search_session_index

        sess_limit = min(limit, 5)
        sess_hits = search_session_index(store.project_root, query, limit=sess_limit)
        for i, hit in enumerate(sess_hits):
            score = 0.7 - (i * 0.05)
            result_entries.append(
                {
                    "session_chunk": {
                        "session_id": hit["session_id"],
                        "chunk_index": hit["chunk_index"],
                        "content": hit["content"][:200] + ("..." if len(hit["content"]) > 200 else ""),
                        "created_at": hit["created_at"],
                    },
                    "score": max(0.4, score),
                    "effective_confidence": 0.5,
                    "stale": False,
                    "source": "session_index",
                }
            )
        result_entries.sort(key=lambda x: x["score"], reverse=True)
        result_entries = result_entries[:limit]

    return {
        "action": "search",
        "ranked": True,
        "results": result_entries,
        "total_count": len(result_entries),
        "returned_count": len(result_entries),
        "query": query,
        "store_metadata": _store_metadata(store),
    }


# Marker text for consolidated source entries
_CONSOLIDATED_MARKER = "consolidated into"


def _filter_consolidated_sources(entries: list[MemoryEntry]) -> list[MemoryEntry]:
    """Filter out source entries of consolidated memories (Epic 58.5).

    Removes entries that were consolidated into other entries.
    These are identified by contradiction_reason containing "consolidated into".

    Args:
        entries: List of memory entries.

    Returns:
        Filtered list without consolidated source entries.
    """
    return [e for e in entries if not _is_consolidated_source(e)]


def _is_consolidated_source(entry: MemoryEntry) -> bool:
    """Check if an entry is a source of a consolidated entry."""
    if not entry.contradicted:
        return False
    reason = entry.contradiction_reason or ""
    return _CONSOLIDATED_MARKER in reason.lower()


def _get_provenance(store: MemoryStore, entry: MemoryEntry) -> dict[str, Any] | None:
    """Build provenance info for a consolidated entry (Epic 58, Story 58.6).

    Scans entries whose contradiction_reason references this entry's key.
    Returns None if the entry is not a consolidated entry.
    """
    marker = f"consolidated into {entry.key}"
    all_entries = store.list_all()
    source_entries = [
        e
        for e in all_entries
        if e.contradicted and e.contradiction_reason and marker in e.contradiction_reason
    ]

    if not source_entries:
        return None

    return {
        "is_consolidated": True,
        "source_count": len(source_entries),
        "source_keys": [e.key for e in source_entries],
        "sources": [
            {
                "key": e.key,
                "value": e.value,
                "tier": e.tier.value if hasattr(e.tier, "value") else str(e.tier),
            }
            for e in source_entries
        ],
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
        value_str[:_SUMMARY_MAX_LEN] + "..." if len(value_str) > _SUMMARY_MAX_LEN else value_str
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
        _summarize_entry(e) if include_summary and i >= _FULL_VALUE_THRESHOLD else e.model_dump()
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

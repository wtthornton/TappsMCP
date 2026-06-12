"""CLI/MCP enrichment for session-handoff brain mirror entries (TAP-3794)."""

from __future__ import annotations

import json
from typing import Any

from tapps_mcp.tools.handoff_schema import (
    SESSION_HANDOFF_MEMORY_KEY,
    handoff_sections_from_doc,
    parse_handoff_markdown,
)

_EMBEDDING_KEYS = frozenset(
    {
        "embedding",
        "embedding_vector",
        "vector",
        "value_embedding",
    }
)

_MEMORY_GROUP_NOTE = (
    "memory_group is null (default ungrouped entry). Pass memory_group on brain "
    "memory_save to scope entries (e.g. insights for validate_changed recall)."
)


def enrich_memory_get_entry(key: str, entry: dict[str, Any]) -> dict[str, Any]:
    """Strip embedding vectors and attach handoff section pointers when applicable."""
    out: dict[str, Any] = {k: v for k, v in entry.items() if k not in _EMBEDDING_KEYS}
    if key != SESSION_HANDOFF_MEMORY_KEY:
        return out

    value = str(entry.get("value", ""))
    if value.strip():
        doc = parse_handoff_markdown(value)
        out["handoff_sections"] = handoff_sections_from_doc(doc)

    details_raw = entry.get("details_json")
    if isinstance(details_raw, str) and details_raw.strip():
        try:
            parsed = json.loads(details_raw)
            if isinstance(parsed, dict):
                out["handoff_metadata"] = parsed
        except json.JSONDecodeError:
            pass
    elif isinstance(details_raw, dict):
        out["handoff_metadata"] = details_raw

    return out


def enrich_memory_save_result(result: dict[str, Any]) -> dict[str, Any]:
    """Clarify null memory_group in CLI/MCP save JSON output."""
    out = dict(result)
    if out.get("memory_group") is None and "memory_group_note" not in out:
        out["memory_group_note"] = _MEMORY_GROUP_NOTE
    return out


def enrich_memory_get_action_result(key: str, result: dict[str, Any]) -> dict[str, Any]:
    """Apply get enrichment to tapps_memory action=get payloads."""
    if not result.get("found"):
        return result
    entry = result.get("entry")
    if not isinstance(entry, dict):
        return result
    out = dict(result)
    out["entry"] = enrich_memory_get_entry(key, entry)
    return out


def enrich_memory_save_action_result(result: dict[str, Any]) -> dict[str, Any]:
    """Apply save enrichment to tapps_memory action=save payloads."""
    out = dict(result)
    entry = out.get("entry")
    if isinstance(entry, dict):
        out["entry"] = enrich_memory_save_result(entry)
    return out


__all__ = [
    "enrich_memory_get_action_result",
    "enrich_memory_get_entry",
    "enrich_memory_save_action_result",
    "enrich_memory_save_result",
]

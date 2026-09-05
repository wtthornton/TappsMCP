"""Compact-projection support for ``tapps_memory`` get/search (TAP-6616).

Split out of ``server_memory_tools.py`` (a 4k+ line module already over the
maintainability-index gate) so this feature's tests and the megafile's
ratchet score don't have to share a file.
"""

from __future__ import annotations

from typing import Any

# TAP-6616: caller-requested projection for get/search — a coarser cap than
# the existing 80-char list/search summary because this is the ONLY field
# surviving a compact response (no separate full value), so it needs to
# stay useful on its own.
_MEMORY_COMPACT_SUMMARY_MAX_LEN = 280


def _compact_memory_entry_dict(entry: dict[str, Any]) -> dict[str, Any]:
    """Reduce an entry dict to the compact-projection field set.

    Drops ``value`` (the field that dominates payload size) in favour of a
    capped ``summary`` — the same shape ``requested_projection`` /
    ``projection`` reporting in snapshot_get models for Linear.
    """
    value = entry.get("value", "")
    value_str = value if isinstance(value, str) else str(value)
    summary = (
        value_str[:_MEMORY_COMPACT_SUMMARY_MAX_LEN] + "..."
        if len(value_str) > _MEMORY_COMPACT_SUMMARY_MAX_LEN
        else value_str
    )
    return {
        "key": entry.get("key"),
        "tier": entry.get("tier"),
        "confidence": entry.get("confidence"),
        "tags": entry.get("tags"),
        "summary": summary,
    }


def apply_memory_projection(action: str, projection: str, result_data: Any) -> Any:
    """Apply a caller-requested ``projection`` to a get/search result.

    Unconditionally callable from the ``tapps_memory`` dispatcher on every
    action/result shape — all the branching lives here so the call site
    stays a single unconditional line. Default (``"full"``, or anything
    other than ``"compact"``), a non-``get``/``search`` action, or a
    non-dict ``result_data`` (error payloads) is a no-op — zero behaviour
    change for existing callers. ``"compact"`` replaces each entry dict with
    :func:`_compact_memory_entry_dict`, whether it appears at
    ``result_data["entry"]`` (get) or nested under ``results[i]["entry"]``
    (ranked search) / ``results[i]`` directly (unranked search).
    """
    if projection != "compact" or action not in {"get", "search"} or not isinstance(
        result_data, dict
    ):
        return result_data

    if action == "get":
        entry = result_data.get("entry")
        if not isinstance(entry, dict):
            return result_data
        out = dict(result_data)
        out["entry"] = _compact_memory_entry_dict(entry)
        out["projection"] = "compact"
        return out

    if action == "search":
        results = result_data.get("results")
        if not isinstance(results, list):
            return result_data
        compacted: list[Any] = []
        for item in results:
            if isinstance(item, dict) and isinstance(item.get("entry"), dict):
                compacted.append({**item, "entry": _compact_memory_entry_dict(item["entry"])})
            elif isinstance(item, dict):
                compacted.append(_compact_memory_entry_dict(item))
            else:
                compacted.append(item)
        out = dict(result_data)
        out["results"] = compacted
        out["projection"] = "compact"
        return out

    return result_data


__all__ = ["apply_memory_projection"]

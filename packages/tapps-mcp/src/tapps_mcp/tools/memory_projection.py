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
#
# Cap derivation (docs/MEMORY_REFERENCE.md): the guarantee is that compact is
# <=30% of full for any entry >=1KB. At exactly 1024 bytes serialized, the
# fixed envelope (key/tier/confidence/tags with no value) is ~89 bytes, so
# the summary budget is 307 - 89 ~= 200 chars before the guarantee breaks —
# 280 leaves no margin (measured 36% of full at the 1024B boundary, i.e. a
# 64% reduction against the promised 70%+). 200 chars clears the boundary
# with margin (~28% of full, 71%+ reduction) and holds at 1100/1500/10240B.
_MEMORY_COMPACT_SUMMARY_MAX_LEN = 200

# TAP-6616 refutation: a caller-supplied value outside this set (including a
# case variant of a known value) must never silently fall back to "full"
# without saying so — see `apply_memory_projection`.
_VALID_PROJECTIONS = {"full", "compact"}


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
    stays a single unconditional line. A non-``get``/``search`` action, or a
    non-dict ``result_data`` (error payloads), is a no-op — zero behaviour
    change for existing callers.

    ``projection`` is normalized case-insensitively, so ``"Compact"`` behaves
    exactly like ``"compact"``. ``"full"`` (default) is a no-op. Any other
    value — including typos like ``"brief"`` — is honest about the
    downgrade instead of silently serving full: the response gets
    ``requested_projection`` (verbatim caller input), ``projection="full"``,
    and ``projection_downgraded=True``, on top of the otherwise-unchanged
    full payload (TAP-6616 refutation).

    ``"compact"`` replaces each entry dict with
    :func:`_compact_memory_entry_dict`, whether it appears at
    ``result_data["entry"]`` (get) or nested under ``results[i]["entry"]``
    (ranked search) / ``results[i]`` directly (unranked search).
    """
    if action not in {"get", "search"} or not isinstance(result_data, dict):
        return result_data

    normalized = projection.strip().lower()
    if normalized not in _VALID_PROJECTIONS:
        out = dict(result_data)
        out["projection"] = "full"
        out["requested_projection"] = projection
        out["projection_downgraded"] = True
        return out

    if normalized != "compact":
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

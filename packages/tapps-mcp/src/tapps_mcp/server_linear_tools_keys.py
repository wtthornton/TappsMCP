"""Cache-key primitives, state buckets, and payload shaping for Linear tools.

Split under TAP-5606 from ``server_linear_tools.py``. This module is the leaf
of the Linear-tools import graph — it holds pure functions and constants with
no filesystem or settings dependency, so it can be imported by both
:mod:`tapps_mcp.server_linear_tools_cache` and
:mod:`tapps_mcp.server_linear_tools_handlers` without risk of a cycle.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# State values that indicate an open workflow (short TTL).
_OPEN_STATE_BUCKETS: frozenset[str] = frozenset({"backlog", "unstarted", "started", "triage"})
# State values that indicate a closed workflow (long TTL).
_CLOSED_STATE_BUCKETS: frozenset[str] = frozenset({"completed", "canceled"})

_FETCH_HINT = (
    "Cache miss. Call mcp__plugin_linear_linear__list_issues with the same "
    "team/project/state filters, then pass the result to "
    "tapps_linear_snapshot_put(issues_json=...) to populate the cache."
)

# Cache-bucket aliases Linear's plugin does not understand (TAP-5356).
_CACHE_BUCKET_ALIASES: frozenset[str] = frozenset({"open", "closed"})


def _fetch_hint_for_state(state: str | None) -> str:
    """Return a miss hint that does not tell agents to pass bucket aliases to Linear."""
    state_lc = (state or "").strip().lower()
    if state_lc in _CACHE_BUCKET_ALIASES:
        return (
            f'Cache miss. "{state_lc}" is a tapps-mcp cache bucket, not a Linear state. '
            "Call mcp__plugin_linear_linear__list_issues with team/project only "
            "(omit state), includeArchived=false; filter issues in memory by "
            f'statusType; then tapps_linear_snapshot_put(..., state="{state_lc}", '
            "issues_json=...) to populate the cache."
        )
    return _FETCH_HINT


def _is_cache_bucket_alias(state: str | None) -> bool:
    return (state or "").strip().lower() in _CACHE_BUCKET_ALIASES


def _list_issues_pass_payload(state: str) -> tuple[dict[str, Any], list[str]]:
    """Build gate-pass data + next_steps for ``tapps_linear_list_issues`` (TAP-5356)."""
    if _is_cache_bucket_alias(state):
        alias = (state or "").strip().lower()
        data: dict[str, Any] = {
            "ok": True,
            "message": (
                f'Gate passed — "{alias}" is a tapps-mcp cache bucket, not a '
                "Linear state. Call mcp__plugin_linear_linear__list_issues "
                "with team/project only (omit state), includeArchived=false; "
                "filter in memory; then tapps_linear_snapshot_put with the "
                f'same state="{alias}".'
            ),
            "alias_warning": (
                f'"{alias}" is a cache bucket alias — do not pass it as '
                "state to the Linear plugin list_issues call."
            ),
        }
        steps = [
            "Call mcp__plugin_linear_linear__list_issues(team, project, "
            "includeArchived=false) — omit state.",
            f'Then call tapps_linear_snapshot_put(..., state="{alias}") to cache.',
        ]
        return data, steps
    data = {
        "ok": True,
        "message": (
            "Gate passed — call mcp__plugin_linear_linear__list_issues "
            "with the same team, project, state, label, and limit params."
        ),
    }
    steps = [
        "Call mcp__plugin_linear_linear__list_issues(team, project, state, ...) now.",
        "Then call tapps_linear_snapshot_put to cache the result.",
    ]
    return data, steps


# Fields returned in compact projection — covers triage/backlog reads without
# pulling in description, comments, attachments, history, or audit fields.
# Include status/statusType so agents following AGENTS.md field names work;
# state is kept for GraphQL-shaped payloads.
_COMPACT_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "identifier",
        "title",
        "state",
        "status",
        "statusType",
        "priority",
        "estimate",
        "assignee",
        "parent",
    }
)


def _compact_issue(issue: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *issue* with only the triage-relevant fields retained.

    Drops heavy fields (description, comments, attachments, history, etc.) so
    that a 50-issue backlog serialises to well under the 25 k-token Read cap.
    Normalizes ``state.type`` → ``statusType`` when the latter is absent so
    compact consumers see a stable shape.
    """
    out = {k: v for k, v in issue.items() if k in _COMPACT_FIELDS}
    if "statusType" not in out:
        state = out.get("state")
        if isinstance(state, dict) and state.get("type"):
            out["statusType"] = state["type"]
        elif isinstance(out.get("status"), dict) and out["status"].get("type"):
            out["statusType"] = out["status"]["type"]
    return out


# Canonical token for the whole open-issue slice (TAP-4588). Any open-bucket
# alias — ""/None, the tapps-mcp TTL alias "open", and every _OPEN_STATE_BUCKETS
# member — collapses to this ONE token so the payload key converges regardless
# of which alias the caller used. Mirrors the sentinel-collapse contract
# (TAP-1374) at the payload layer.
_CANONICAL_OPEN_STATE = "open"


def _canonical_state(state: str | None) -> str:
    """Canonicalize a Linear ``state`` for cache-key construction (TAP-4588).

    Collapses every open-bucket alias — ``""``/``None``, the tapps-mcp TTL alias
    ``"open"``, and each :data:`_OPEN_STATE_BUCKETS` member — to the single token
    :data:`_CANONICAL_OPEN_STATE` so a ``get`` for the open slice hits a write
    made under any of those aliases. Closed buckets
    (``completed``/``canceled``) and any other named state are returned
    lower-cased and unchanged, keeping them isolated from the open bucket and
    from each other.
    """
    state_lc = (state or "").strip().lower()
    if state_lc in {"", _CANONICAL_OPEN_STATE} or state_lc in _OPEN_STATE_BUCKETS:
        return _CANONICAL_OPEN_STATE
    return state_lc


def _filter_hash(**kwargs: Any) -> str:
    """Stable hash of filter kwargs for cache-key construction.

    ``limit`` is deliberately NOT part of the hash (TAP-4588): limit is
    enforced at read time via the superset fallback in
    :func:`tapps_linear_snapshot_get`, so a stored ``limit=150`` snapshot can
    serve a ``limit=50`` read from the same key. Callers pass only the fields
    that define the *slice identity* (``state``, ``label``).
    """
    normalized = {k: v for k, v in sorted(kwargs.items()) if v not in {None, ""}}
    payload = json.dumps(normalized, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _cache_key(team: str, project: str, state: str | None, filter_hash: str) -> str:
    """Build the cache-file stem from slice identifiers.

    ``state`` must already be canonicalized via :func:`_canonical_state` by the
    caller (:func:`_resolve_cache_key`) so the filename segment matches the
    hashed ``state`` field.
    """
    parts = [
        team.replace("/", "_") or "_",
        project.replace("/", "_") or "_",
        (state or "any").replace("/", "_"),
        filter_hash,
    ]
    return "__".join(parts)


def _extract_status_type(issue: dict[str, Any]) -> str:
    """Extract a lower-cased ``statusType`` from an issue dict for classification.

    Handles the ``statusType``, ``status.type``, and ``state``
    (dict-with-``type``/``name`` or bare string) shapes that Linear
    snapshots (and compact/GraphQL projections of them) can carry.
    """
    raw_status = issue.get("status") or {}
    status_type = issue.get("statusType") or (
        raw_status.get("type", "") if isinstance(raw_status, dict) else ""
    )
    if not status_type:
        state = issue.get("state")
        if isinstance(state, dict):
            status_type = state.get("type") or state.get("name") or ""
        elif isinstance(state, str):
            status_type = state
    return status_type.lower() if status_type else ""


def _ttl_for_state(state: str | None, ttl_open: int, ttl_closed: int) -> int:
    """Choose TTL bucket based on the requested Linear ``state``."""
    if state and state.lower() in _CLOSED_STATE_BUCKETS:
        return ttl_closed
    # Default to the open-bucket TTL (also covers state=None / unknown).
    return ttl_open


def _resolve_cache_key(team: str, project: str, state: str, label: str, limit: int) -> str:
    """Build the canonical cache key used by both _get and _put.

    State is canonicalized (TAP-4588) so every open-bucket alias resolves to
    one key, and ``limit`` is excluded from the key entirely — it is enforced
    at read time by the superset fallback in :func:`tapps_linear_snapshot_get`.
    ``limit`` is still accepted for signature compatibility with the bash hooks
    and the sentinel gateway, but does not affect the key.
    """
    canon = _canonical_state(state)
    fhash = _filter_hash(state=canon, label=label)
    return _cache_key(team, project, canon, fhash)

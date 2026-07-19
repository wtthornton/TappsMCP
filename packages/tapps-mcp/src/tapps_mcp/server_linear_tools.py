"""Linear tool handlers for TappsMCP (TAP-964).

Provides a cache-only surface for Linear issue snapshots. The agent is
the authoritative Linear caller — it fetches via the Linear MCP plugin
(which already holds OAuth via Claude Code) and passes results here for
storage. tapps-mcp never calls Linear itself; that would duplicate the
plugin's auth and create a parallel credential surface.

Tools:
- ``tapps_linear_snapshot_get(team, project, state, label, limit)`` —
  cache-only read. Returns ``cached=True`` with the stored issue list
  when fresh, or ``cached=False`` with a hint to fetch via the plugin.
- ``tapps_linear_snapshot_put(team, project, issues_json, state, label,
  limit)`` — cache-set after the agent fetched via the plugin. TTL
  depends on the requested ``state`` bucket.
- ``tapps_linear_snapshot_invalidate(team, project)`` — prefix-match
  delete, called after a Linear write (``save_issue``, ``save_comment``)
  so the next ``_get`` sees fresh data.

Cache layout::

    <project_root>/.tapps-mcp-cache/linear-snapshots/<cache_key>.json

Each file stores ``{issues, cached_at, expires_at, team, project,
state}``. ``expires_at`` is enforced on read; stale entries are treated
as misses.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from tapps_core.cache import AtomicJsonCache, TTLStaleness, register_cache_stats
from tapps_core.config.settings import load_settings
from tapps_mcp.mcp_register import register_tool
from tapps_mcp.server_helpers import error_response, success_response

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

from mcp.types import ToolAnnotations

logger = structlog.get_logger(__name__)

_ANNOTATIONS_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
_ANNOTATIONS_WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
_ANNOTATIONS_INVALIDATE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=True,
    openWorldHint=False,
)

# TAP-1986: all Linear cache tools are deferred (not daily drivers).
_META_DEFERRED: dict[str, Any] = {"defer_loading": True}

# State values that indicate an open workflow (short TTL).
_OPEN_STATE_BUCKETS: frozenset[str] = frozenset({"backlog", "unstarted", "started", "triage"})
# State values that indicate a closed workflow (long TTL).
_CLOSED_STATE_BUCKETS: frozenset[str] = frozenset({"completed", "canceled"})

_CACHE_SUBDIR = "linear-snapshots"
_CACHE_MAX_FILES = 500
_CACHE_STALE_TTL_MULTIPLIER = 10
_FETCH_HINT = (
    "Cache miss. Call mcp__plugin_linear_linear__list_issues with the same "
    "team/project/state filters, then pass the result to "
    "tapps_linear_snapshot_put(issues_json=...) to populate the cache."
)

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


def _record_call(tool_name: str) -> None:
    """Delegate to server._record_call."""
    from tapps_mcp.server import _record_call as _rc

    _rc(tool_name)


def _cache_dir(project_root: Path) -> Path:
    """Return the cache directory for Linear snapshots, creating if needed."""
    cache_dir = project_root / ".tapps-mcp-cache" / _CACHE_SUBDIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


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
    if state_lc == "" or state_lc == _CANONICAL_OPEN_STATE or state_lc in _OPEN_STATE_BUCKETS:
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
    normalized = {k: v for k, v in sorted(kwargs.items()) if v not in (None, "")}
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


def _ttl_for_state(state: str | None, ttl_open: int, ttl_closed: int) -> int:
    """Choose TTL bucket based on the requested Linear ``state``."""
    if state and state.lower() in _CLOSED_STATE_BUCKETS:
        return ttl_closed
    # Default to the open-bucket TTL (also covers state=None / unknown).
    return ttl_open


# ADR-0029 / TAP-4561: unified cache-stats counters (snapshot reads/writes).
_snapshot_stats: dict[str, int] = {"hits": 0, "misses": 0, "writes": 0}
# TAP-4558: wall-clock timestamp of the most recent snapshot write (0 == never).
_snapshot_last_write_ts: float = 0.0


def _linear_snapshot_stats() -> dict[str, Any]:
    """Stats provider: counters + staleness/age of the freshest write (TAP-4558).

    ``age_seconds`` is the age of the most-recently written snapshot (``None``
    until the first write); ``stale`` reports whether that freshest write has
    already aged past the open-bucket TTL — the conservative (shorter) bound, so
    a freshest snapshot older than it is definitively stale. This gives the
    unified ``tapps_stats.caches`` surface the same age/staleness signal the
    code-graph cache already exposes.
    """
    out: dict[str, Any] = dict(_snapshot_stats)
    if _snapshot_last_write_ts <= 0:
        out["age_seconds"] = None
        out["stale"] = None
        return out
    ttl_open = load_settings().linear_cache_ttl_open_seconds
    age = time.time() - _snapshot_last_write_ts
    out["age_seconds"] = round(age, 1)
    out["stale"] = TTLStaleness(float(ttl_open)).is_stale(_snapshot_last_write_ts)
    return out


register_cache_stats("linear_snapshot", _linear_snapshot_stats)


def _cache_read(cache_dir: Path, cache_key: str) -> dict[str, Any] | None:
    """Return cached payload if present and unexpired; None otherwise."""
    cache_file = cache_dir / f"{cache_key}.json"
    if not cache_file.exists():
        _snapshot_stats["misses"] += 1
        return None
    try:
        raw = cache_file.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("linear_cache_read_failed", key=cache_key, exc=str(exc))
        _snapshot_stats["misses"] += 1
        return None
    expires_at = float(payload.get("expires_at", 0))
    if expires_at <= time.time():
        _snapshot_stats["misses"] += 1
        return None
    _snapshot_stats["hits"] += 1
    return payload  # type: ignore[no-any-return]


def _cache_write(cache_dir: Path, cache_key: str, payload: dict[str, Any]) -> None:
    """Write payload to the cache atomically (ADR-0029 shared primitive)."""
    cache_file = cache_dir / f"{cache_key}.json"
    try:
        # indent=None keeps the compact json.dumps byte layout from before.
        AtomicJsonCache.write_json(cache_file, payload, indent=None)
        _snapshot_stats["writes"] += 1
        global _snapshot_last_write_ts
        _snapshot_last_write_ts = time.time()
    except OSError as exc:
        logger.debug("linear_cache_write_failed", key=cache_key, exc=str(exc))


def _prune_linear_snapshot_cache(
    cache_dir: Path,
    *,
    ttl_open: int,
    ttl_closed: int,
) -> int:
    """Remove stale snapshot files and LRU-evict when over the file cap (TAP-1766).

    Deletes entries whose mtime age exceeds ``max(ttl_open, ttl_closed) x 10``
    and trims the directory to :data:`_CACHE_MAX_FILES` by oldest mtime.
    """
    if not cache_dir.is_dir():
        return 0

    # Use the shorter bucket TTL so open-state snapshots are not kept for
    # closed-state TTL x 10 (which would be hours on default settings).
    positive = [t for t in (ttl_open, ttl_closed) if t > 0]
    base_ttl = min(positive) if positive else 1
    stale_age = base_ttl * _CACHE_STALE_TTL_MULTIPLIER
    now = time.time()
    removed = 0
    survivors: list[tuple[Path, float]] = []

    for entry in cache_dir.glob("*.json"):
        if entry.name.endswith(".tmp"):
            continue
        try:
            mtime = entry.stat().st_mtime
        except OSError as exc:
            logger.debug("linear_cache_prune_stat_failed", path=str(entry), exc=str(exc))
            continue

        if now - mtime > stale_age:
            try:
                entry.unlink()
                removed += 1
            except OSError as exc:
                logger.debug("linear_cache_prune_unlink_failed", path=str(entry), exc=str(exc))
            continue

        survivors.append((entry, mtime))

    if len(survivors) > _CACHE_MAX_FILES:
        survivors.sort(key=lambda item: item[1])
        for entry, _ in survivors[: len(survivors) - _CACHE_MAX_FILES]:
            try:
                entry.unlink()
                removed += 1
            except OSError as exc:
                logger.debug("linear_cache_lru_unlink_failed", path=str(entry), exc=str(exc))

    if removed:
        logger.debug("linear_cache_pruned", removed=removed, dir=str(cache_dir))
    return removed


def _cache_invalidate_prefix(cache_dir: Path, prefix: str) -> int:
    """Remove cache files whose stems start with *prefix*. Return count removed."""
    count = 0
    for entry in cache_dir.glob(f"{prefix}*.json"):
        try:
            entry.unlink()
            count += 1
        except OSError as exc:
            logger.debug("linear_cache_invalidate_failed", path=str(entry), exc=str(exc))
    return count


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


async def tapps_linear_snapshot_get(
    team: str,
    project: str,
    state: str = "",
    label: str = "",
    limit: int = 50,
    projection: str = "full",
) -> dict[str, Any]:
    """Reads a Linear issue snapshot from the local cache, returning
    ``cached=True`` + the stored issues on hit or ``cached=False`` + a
    fetch hint on miss.

    Call this FIRST for every multi-issue Linear read — "list open
    issues in TAP", "what's assigned to me", "backlog review" — never
    call ``mcp__plugin_linear_linear__list_issues`` directly without a
    prior snapshot_get on the same ``(team, project, state, label,
    limit)`` slice (the cache-gate hook will reject the call). For
    single-issue lookups by id, skip this and use
    ``mcp__plugin_linear_linear__get_issue(id=...)`` directly. The
    ``linear-read`` skill orchestrates this dance automatically.

    Args:
        team: Linear team name (required).
        project: Linear project name (required).
        state: Optional Linear state type (``"backlog"``, ``"unstarted"``,
            ``"started"``, ``"completed"``, ``"canceled"``). Empty = any.
        label: Optional label name to filter by. Empty = any.
        limit: Max issues the caller requested (part of the cache key).
        projection: ``"compact"`` returns only triage-relevant fields
            ``{id, identifier, title, state, priority, estimate, assignee,
            parent}``, dropping description, comments, attachments, and
            history. A 50-issue backlog in compact mode serialises to
            under 48 kB — well within the 25 k-token Read cap that
            subagents face. ``"full"`` (default) returns the stored
            issue dicts unchanged.

    Returns:
        Envelope with:
          - ``data.cached``: ``True`` on hit, ``False`` on miss/expired.
          - ``data.issues``: stored list (only on hit; projected if
            ``projection="compact"``).
          - ``data.projection``: the projection mode applied.
          - ``data.cache_key``: cache-file stem.
          - ``data.cached_at`` / ``data.expires_at`` / ``data.age_seconds``
            on hit; ``data.hint`` on miss.
    """
    _record_call("tapps_linear_snapshot_get")
    start_ns = time.perf_counter_ns()

    if not team or not project:
        return error_response(
            "tapps_linear_snapshot_get",
            "invalid_input",
            "team and project are required and must be non-empty",
        )

    settings = load_settings()
    cache_dir = _cache_dir(settings.project_root)
    _prune_linear_snapshot_cache(
        cache_dir,
        ttl_open=settings.linear_cache_ttl_open_seconds,
        ttl_closed=settings.linear_cache_ttl_closed_seconds,
    )
    key = _resolve_cache_key(team, project, state, label, limit)

    cached = _cache_read(cache_dir, key)

    # TAP-4588: superset-limit + poisoning guards. The key no longer embeds
    # ``limit``, so an exact-key hit may carry a snapshot stored under a
    # different limit; only a stored ``limit >= requested`` can serve the read
    # (a smaller stored limit is an incomplete slice and must MISS). Also
    # reject an auto-populated empty payload as a false empty hit: it most
    # likely came from list_issues(state="<alias/invalid>") returning [].
    served_from_superset = False
    if cached is not None:
        stored_limit_raw = cached.get("limit")
        auto_populated = bool(cached.get("auto_populated"))
        issue_list: list[dict[str, Any]] = cached.get("issues", []) or []

        if auto_populated and not issue_list:
            # Poisoning guard: an empty auto-populated payload is not a
            # confident hit — undo the hit bookkeeping and fall through to MISS.
            _snapshot_stats["hits"] -= 1
            _snapshot_stats["misses"] += 1
            cached = None
        elif stored_limit_raw is not None:
            try:
                stored_limit = int(stored_limit_raw)
            except (TypeError, ValueError):
                stored_limit = limit
            if stored_limit < limit:
                # Smaller stored slice cannot satisfy a larger request.
                _snapshot_stats["hits"] -= 1
                _snapshot_stats["misses"] += 1
                cached = None
            elif stored_limit > limit:
                served_from_superset = True

    elapsed_ms = (time.perf_counter_ns() - start_ns) // 1_000_000

    if cached is None:
        return success_response(
            "tapps_linear_snapshot_get",
            elapsed_ms,
            {
                "cached": False,
                "cache_key": key,
                "team": team,
                "project": project,
                "state": state or None,
                "hint": _FETCH_HINT,
            },
        )

    now = time.time()
    cached_at = float(cached.get("cached_at", 0))
    issues: list[dict[str, Any]] = cached.get("issues", [])
    if served_from_superset:
        # Truncate the broader snapshot down to what the caller asked for.
        issues = issues[:limit]
    if projection == "compact":
        issues = [_compact_issue(i) for i in issues]
    return success_response(
        "tapps_linear_snapshot_get",
        elapsed_ms,
        {
            "cached": True,
            "issues": issues,
            "projection": projection,
            "cache_key": key,
            "cached_at": cached_at,
            "expires_at": cached.get("expires_at"),
            "age_seconds": max(0.0, now - cached_at) if cached_at else None,
            "team": team,
            "project": project,
            "state": state or None,
            "served_from_superset": served_from_superset,
        },
    )


async def tapps_linear_snapshot_put(
    team: str,
    project: str,
    issues_json: str,
    state: str = "",
    label: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    """Writes a Linear issue list into the local snapshot cache so the
    next ``tapps_linear_snapshot_get`` for the same slice returns
    ``cached=True``.

    Call this IMMEDIATELY after a successful
    ``mcp__plugin_linear_linear__list_issues`` fetch following a
    snapshot_get cache miss. The ``(team, project, state, label,
    limit)`` tuple MUST match the earlier snapshot_get call exactly —
    mismatched keys produce duplicate caches and break the cache-gate
    invariant. TTL is auto-selected from the ``state`` bucket
    (``linear_cache_ttl_open_seconds`` for backlog/unstarted/started,
    ``linear_cache_ttl_closed_seconds`` for completed/canceled).

    Args:
        team: Linear team name (required).
        project: Linear project name (required).
        issues_json: JSON-encoded list of issue dicts from the Linear
            plugin response (typically the ``issues`` field). Pass the
            list verbatim; do not reshape.
        state: Linear state type the fetch was scoped to. Empty = any.
        label: Label filter the fetch used. Empty = any.
        limit: Limit argument the fetch used.

    Returns:
        Envelope with ``data.stored``, ``data.cache_key``,
        ``data.cached_at``, ``data.expires_at``, ``data.ttl_seconds``,
        and ``data.issue_count``.
    """
    _record_call("tapps_linear_snapshot_put")
    start_ns = time.perf_counter_ns()

    if not team or not project:
        return error_response(
            "tapps_linear_snapshot_put",
            "invalid_input",
            "team and project are required and must be non-empty",
        )

    try:
        issues = json.loads(issues_json) if issues_json else []
    except json.JSONDecodeError as exc:
        return error_response(
            "tapps_linear_snapshot_put",
            "invalid_input",
            f"issues_json must be valid JSON: {exc}",
        )

    if not isinstance(issues, list):
        return error_response(
            "tapps_linear_snapshot_put",
            "invalid_input",
            "issues_json must decode to a list of issue dicts",
        )

    settings = load_settings()
    cache_dir = _cache_dir(settings.project_root)
    _prune_linear_snapshot_cache(
        cache_dir,
        ttl_open=settings.linear_cache_ttl_open_seconds,
        ttl_closed=settings.linear_cache_ttl_closed_seconds,
    )
    key = _resolve_cache_key(team, project, state, label, limit)

    now = time.time()
    ttl = _ttl_for_state(
        state or None,
        settings.linear_cache_ttl_open_seconds,
        settings.linear_cache_ttl_closed_seconds,
    )

    if ttl <= 0:
        elapsed_ms = (time.perf_counter_ns() - start_ns) // 1_000_000
        return success_response(
            "tapps_linear_snapshot_put",
            elapsed_ms,
            {
                "stored": False,
                "cache_key": key,
                "ttl_seconds": ttl,
                "issue_count": len(issues),
                "hint": "TTL is zero for this state bucket — cache disabled.",
            },
        )

    payload: dict[str, Any] = {
        "issues": issues,
        "cached_at": now,
        "expires_at": now + ttl,
        "state": state or None,
        "team": team,
        "project": project,
        # TAP-4588: record the stored limit so snapshot_get's superset fallback
        # can decide whether this snapshot can serve a smaller-limit read.
        "limit": limit,
    }
    _cache_write(cache_dir, key, payload)

    elapsed_ms = (time.perf_counter_ns() - start_ns) // 1_000_000
    return success_response(
        "tapps_linear_snapshot_put",
        elapsed_ms,
        {
            "stored": True,
            "cache_key": key,
            "cached_at": now,
            "expires_at": now + ttl,
            "ttl_seconds": ttl,
            "issue_count": len(issues),
            "state": state or None,
        },
    )


async def tapps_linear_snapshot_invalidate(
    team: str = "",
    project: str = "",
) -> dict[str, Any]:
    """Evicts cached Linear snapshots matching a team/project prefix so
    the next read picks up server-side writes.

    Call this after any Linear write — ``save_issue``, ``save_comment``,
    ``save_document``, or anything that mutates issues — otherwise the
    next ``tapps_linear_snapshot_get`` returns stale data and the agent
    will act on out-of-date state. The ``linear-issue`` and
    ``linear-release-update`` skills both call this automatically;
    invoke directly only for ad-hoc invalidations after raw plugin
    writes or wholesale cache reset (both args empty).

    Args:
        team: Linear team name prefix. Empty matches all teams.
        project: Linear project name prefix. Empty matches all projects.

    Returns:
        Envelope with ``data.removed`` (count of cache files deleted)
        and ``data.prefix`` (the key prefix used for matching).
    """
    _record_call("tapps_linear_snapshot_invalidate")
    start_ns = time.perf_counter_ns()

    settings = load_settings()
    cache_dir = _cache_dir(settings.project_root)

    if team and project:
        prefix = f"{team.replace('/', '_')}__{project.replace('/', '_')}__"
    elif team:
        prefix = f"{team.replace('/', '_')}__"
    else:
        prefix = ""

    removed = _cache_invalidate_prefix(cache_dir, prefix)
    elapsed_ms = (time.perf_counter_ns() - start_ns) // 1_000_000
    return success_response(
        "tapps_linear_snapshot_invalidate",
        elapsed_ms,
        {
            "removed": removed,
            "prefix": prefix,
            "team": team or None,
            "project": project or None,
        },
    )


# Reuse the state-bucket constants for open/done classification.
# _OPEN_STATE_BUCKETS = {"backlog","unstarted","started","triage"} (defined above)
# _CLOSED_STATE_BUCKETS = {"completed","canceled"} (defined above)


async def tapps_linear_count(
    team: str,
    project: str,
    max_age_seconds: int = 3600,
) -> dict[str, Any]:
    """Returns open + done issue counts from cached Linear snapshots
    without making any Linear API calls — credential-free monitoring.

    Call this from automation that needs project pulse ("how many open
    issues?") without burning a Linear API call or requiring
    ``LINEAR_API_KEY`` — e.g., credential-free loop consumers. For
    full issue listing use ``tapps_linear_snapshot_get`` (also
    cache-only) or the ``linear-read`` skill. Snapshots populated by
    the ``linear-read`` skill are reused; if none exists for
    ``(team, project)`` the response carries ``available=False`` so the
    caller can degrade gracefully.

    Issues are deduplicated across multiple state-slice snapshots by
    Linear id. Classification uses the issue's own ``statusType``:
    ``{"backlog","unstarted","started","triage"}`` count as open;
    ``{"completed","canceled"}`` count as done.

    Args:
        team: Linear team name (required).
        project: Linear project name (required).
        max_age_seconds: Maximum age of a snapshot to count as fresh.
            Defaults to 3600 (one hour). Pass 0 to disable staleness
            filtering and accept any non-expired snapshot.

    Returns:
        Envelope with:
          - ``data.available``: ``True`` when a fresh snapshot was found.
          - ``data.open``: count of open issues (backlog/unstarted/started/triage).
          - ``data.done``: count of done/cancelled issues.
          - ``data.age_seconds``: seconds since the freshest snapshot was written.
          - ``data.snapshot_count``: number of cache files aggregated.
          - ``data.reason``: explanation when ``available=False``.
    """
    _record_call("tapps_linear_count")
    start_ns = time.perf_counter_ns()

    if not team or not project:
        return error_response(
            "tapps_linear_count",
            "invalid_input",
            "team and project are required and must be non-empty",
        )

    settings = load_settings()
    cache_dir = _cache_dir(settings.project_root)
    prefix = f"{team.replace('/', '_')}__{project.replace('/', '_')}__"

    now = time.time()
    cutoff = now - max_age_seconds if max_age_seconds > 0 else 0.0

    # Collect issues deduplicated by id across all matching cache files.
    seen_ids: dict[str, str] = {}  # id → statusType
    freshest_cached_at: float = 0.0
    snapshot_count = 0

    for cache_file in cache_dir.glob(f"{prefix}*.json"):
        try:
            raw = cache_file.read_text(encoding="utf-8")
            payload = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            continue

        cached_at = float(payload.get("cached_at", 0))
        expires_at = float(payload.get("expires_at", 0))
        # Skip expired or stale entries.
        if expires_at <= now or cached_at < cutoff:
            continue

        snapshot_count += 1
        freshest_cached_at = max(freshest_cached_at, cached_at)

        for issue in payload.get("issues", []):
            issue_id = issue.get("id") or issue.get("identifier")
            if not issue_id or issue_id in seen_ids:
                continue
            raw_status = issue.get("status") or {}
            status_type = issue.get("statusType") or (
                raw_status.get("type", "") if isinstance(raw_status, dict) else ""
            )
            # Compact / GraphQL snapshots often keep state as {type, name}
            # without a separate statusType field.
            if not status_type:
                state = issue.get("state")
                if isinstance(state, dict):
                    status_type = state.get("type") or state.get("name") or ""
                elif isinstance(state, str):
                    status_type = state
            seen_ids[issue_id] = status_type.lower() if status_type else ""

    elapsed_ms = (time.perf_counter_ns() - start_ns) // 1_000_000

    if snapshot_count == 0:
        return success_response(
            "tapps_linear_count",
            elapsed_ms,
            {
                "available": False,
                "open": None,
                "done": None,
                "age_seconds": None,
                "snapshot_count": 0,
                "reason": (
                    f"No fresh Linear snapshot found for {team}/{project} "
                    f"(max_age_seconds={max_age_seconds}). "
                    "Run the linear-read skill to populate the cache."
                ),
            },
        )

    open_count = sum(1 for st in seen_ids.values() if st in _OPEN_STATE_BUCKETS)
    done_count = sum(1 for st in seen_ids.values() if st in _CLOSED_STATE_BUCKETS)
    age_seconds = max(0.0, now - freshest_cached_at)

    return success_response(
        "tapps_linear_count",
        elapsed_ms,
        {
            "available": True,
            "open": open_count,
            "done": done_count,
            "age_seconds": round(age_seconds, 1),
            "snapshot_count": snapshot_count,
            "team": team,
            "project": project,
        },
    )


async def tapps_linear_list_issues(
    team: str,
    project: str,
    state: str = "",
    label: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    """Pre-list gate for Linear issue reads (TAP-2010).

    Checks whether ``tapps_linear_snapshot_get`` has been called recently
    (within 5 minutes, for the same ``(team, project, state, label, limit)``
    slice) before allowing a ``list_issues`` call to proceed.

    When the gate passes, returns ``{ok: true}`` — the agent should then call
    ``mcp__plugin_linear_linear__list_issues`` with the same params. When the
    gate fires, returns the standard ``gate_miss`` refusal envelope (see
    ``docs/architecture/gateway-envelope.md``); call
    ``tapps_linear_snapshot_get`` first to satisfy the gate.

    This is the server-side counterpart to
    ``.claude/hooks/tapps-pre-linear-list.sh``, providing defence-in-depth
    when hooks are absent (other MCP clients, CI, read-only Claude Code
    configs).

    Args:
        team: Linear team name — must match the ``tapps_linear_snapshot_get``
            call that preceded this one.
        project: Linear project name — same as above.
        state: Linear state filter (e.g. ``"backlog"``, ``"open"``).
        label: Optional label filter.
        limit: Max results requested — part of the cache key.
    """
    _record_call("tapps_linear_list_issues")
    start_ns = time.perf_counter_ns()

    from tapps_mcp.tools.linear_list_gateway import gate_linear_list

    settings = load_settings()
    refusal = gate_linear_list(settings.project_root, team, project, state, label, limit)
    elapsed_ms = (time.perf_counter_ns() - start_ns) // 1_000_000

    if refusal is not None:
        return success_response(
            "tapps_linear_list_issues",
            elapsed_ms,
            refusal,
            next_steps=[
                f"Call tapps_linear_snapshot_get(team={team!r}, project={project!r}, state={state!r}) first.",
                "On cached=false, call list_issues then tapps_linear_snapshot_put.",
            ],
        )

    return success_response(
        "tapps_linear_list_issues",
        elapsed_ms,
        {
            "ok": True,
            "message": (
                "Gate passed — call mcp__plugin_linear_linear__list_issues "
                "with the same team, project, state, label, and limit params."
            ),
        },
        next_steps=[
            "Call mcp__plugin_linear_linear__list_issues(team, project, state, ...) now.",
            "Then call tapps_linear_snapshot_put to cache the result.",
        ],
    )


def register(mcp_instance: FastMCP, allowed_tools: frozenset[str]) -> None:
    """Register Linear tools on the shared *mcp_instance*.

    TAP-1986: all four Linear cache tools are deferred (not daily drivers).
    TAP-2010: tapps_linear_list_issues is a deferred gate tool.
    """
    if "tapps_linear_snapshot_get" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_linear_snapshot_get,
            annotations=_ANNOTATIONS_READ_ONLY,
            meta=_META_DEFERRED,
        )
    if "tapps_linear_snapshot_put" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_linear_snapshot_put,
            annotations=_ANNOTATIONS_WRITE,
            meta=_META_DEFERRED,
        )
    if "tapps_linear_snapshot_invalidate" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_linear_snapshot_invalidate,
            annotations=_ANNOTATIONS_INVALIDATE,
            meta=_META_DEFERRED,
        )
    if "tapps_linear_count" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_linear_count,
            annotations=_ANNOTATIONS_READ_ONLY,
            meta=_META_DEFERRED,
        )
    if "tapps_linear_list_issues" in allowed_tools:
        register_tool(
            mcp_instance,
            tapps_linear_list_issues,
            annotations=_ANNOTATIONS_READ_ONLY,
            meta=_META_DEFERRED,
        )

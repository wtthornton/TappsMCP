"""Linear tool handlers — the five async MCP tools + registration wiring.

Split under TAP-5606 from ``server_linear_tools.py``. Imports
:mod:`tapps_mcp.server_linear_tools_keys` and
:mod:`tapps_mcp.server_linear_tools_cache`; the ``linear_list_gateway``
import inside :func:`tapps_linear_list_issues` stays lazy, matching the
pre-split pattern.

``load_settings`` is deliberately re-resolved from the facade
(:mod:`tapps_mcp.server_linear_tools`) on every call via :func:`_get_settings`
rather than imported once at module scope: tests patch
``tapps_mcp.server_linear_tools.load_settings``, and a plain module-level
import here would freeze a reference that patch can never reach.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
from mcp.types import ToolAnnotations

from tapps_mcp.mcp_register import register_tool
from tapps_mcp.server_helpers import error_response, success_response
from tapps_mcp.server_linear_tools_cache import (
    _cache_dir,
    _cache_invalidate_glob,
    _cache_read,
    _cache_write,
    _prune_linear_snapshot_cache,
    _snapshot_stats,
)
from tapps_mcp.server_linear_tools_keys import (
    _CLOSED_STATE_BUCKETS,
    _OPEN_STATE_BUCKETS,
    _compact_issue,
    _extract_status_type,
    _fetch_hint_for_state,
    _list_issues_pass_payload,
    _resolve_cache_key,
    _ttl_for_state,
)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

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


def _record_call(tool_name: str) -> None:
    """Delegate to server._record_call."""
    from tapps_mcp.server import _record_call as _rc

    _rc(tool_name)


def _get_settings() -> Any:
    """Resolve ``load_settings`` from the facade so test patches take effect."""
    from tapps_mcp.server_linear_tools import load_settings

    return load_settings()


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
        limit: Max issues the caller requested. Not part of the cache key
            (TAP-4588); enforced at read time via the superset fallback.
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

    settings = _get_settings()
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
                "hint": _fetch_hint_for_state(state),
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

    settings = _get_settings()
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

    settings = _get_settings()
    cache_dir = _cache_dir(settings.project_root)

    if team and project:
        pattern = f"{team.replace('/', '_')}__{project.replace('/', '_')}__*"
    elif team:
        pattern = f"{team.replace('/', '_')}__*"
    elif project:
        # Project-only: match the project segment across all teams instead of
        # silently wiping every cached snapshot (cache keys are team__project__…).
        pattern = f"*__{project.replace('/', '_')}__*"
    else:
        pattern = "*"

    removed = _cache_invalidate_glob(cache_dir, pattern)
    elapsed_ms = (time.perf_counter_ns() - start_ns) // 1_000_000
    return success_response(
        "tapps_linear_snapshot_invalidate",
        elapsed_ms,
        {
            "removed": removed,
            "prefix": pattern,
            "team": team or None,
            "project": project or None,
        },
    )


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

    settings = _get_settings()
    cache_dir = _cache_dir(settings.project_root)
    prefix = f"{team.replace('/', '_')}__{project.replace('/', '_')}__"

    now = time.time()
    cutoff = now - max_age_seconds if max_age_seconds > 0 else 0.0

    # Collect issues deduplicated by id across all matching cache files.
    seen_ids: dict[str, str] = {}  # id → statusType
    freshest_cached_at: float = 0.0
    snapshot_count = 0

    for cache_file in cache_dir.glob(f"{prefix}*.json"):
        cached_at = _scan_snapshot_file(cache_file, now, cutoff, seen_ids)
        if cached_at is None:
            continue
        snapshot_count += 1
        freshest_cached_at = max(freshest_cached_at, cached_at)

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
        limit: Max results requested. Not part of the cache key (TAP-4588).
    """
    _record_call("tapps_linear_list_issues")
    start_ns = time.perf_counter_ns()

    from tapps_mcp.tools.linear_list_gateway import gate_linear_list

    settings = _get_settings()
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

    data, steps = _list_issues_pass_payload(state)
    return success_response(
        "tapps_linear_list_issues",
        elapsed_ms,
        data,
        next_steps=steps,
    )


def _scan_snapshot_file(
    cache_file: Path,
    now: float,
    cutoff: float,
    seen_ids: dict[str, str],
) -> float | None:
    """Read one snapshot cache file and fold its issues into *seen_ids*.

    Returns the file's ``cached_at`` on success, or ``None`` if the file is
    unreadable, expired, or older than *cutoff* — signalling the caller to
    skip it entirely (not counted as a snapshot).
    """
    try:
        raw = cache_file.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return None

    cached_at = float(payload.get("cached_at", 0))
    expires_at = float(payload.get("expires_at", 0))
    if expires_at <= now or cached_at < cutoff:
        return None

    for issue in payload.get("issues", []):
        issue_id = issue.get("id") or issue.get("identifier")
        if not issue_id or issue_id in seen_ids:
            continue
        seen_ids[issue_id] = _extract_status_type(issue)

    return cached_at


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

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

from tapps_core.config.settings import load_settings
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

# State values that indicate an open workflow (short TTL).
_OPEN_STATE_BUCKETS: frozenset[str] = frozenset(
    {"backlog", "unstarted", "started", "triage"}
)
# State values that indicate a closed workflow (long TTL).
_CLOSED_STATE_BUCKETS: frozenset[str] = frozenset({"completed", "canceled"})

_CACHE_SUBDIR = "linear-snapshots"
_FETCH_HINT = (
    "Cache miss. Call mcp__plugin_linear_linear__list_issues with the same "
    "team/project/state filters, then pass the result to "
    "tapps_linear_snapshot_put(issues_json=...) to populate the cache."
)


def _record_call(tool_name: str) -> None:
    """Delegate to server._record_call."""
    from tapps_mcp.server import _record_call as _rc

    _rc(tool_name)


def _cache_dir(project_root: Path) -> Path:
    """Return the cache directory for Linear snapshots, creating if needed."""
    cache_dir = project_root / ".tapps-mcp-cache" / _CACHE_SUBDIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _filter_hash(**kwargs: Any) -> str:
    """Stable hash of filter kwargs for cache-key construction."""
    normalized = {k: v for k, v in sorted(kwargs.items()) if v not in (None, "")}
    payload = json.dumps(normalized, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _cache_key(
    team: str, project: str, state: str | None, filter_hash: str
) -> str:
    """Build the cache-file stem from slice identifiers."""
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


def _cache_read(cache_dir: Path, cache_key: str) -> dict[str, Any] | None:
    """Return cached payload if present and unexpired; None otherwise."""
    cache_file = cache_dir / f"{cache_key}.json"
    if not cache_file.exists():
        return None
    try:
        raw = cache_file.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("linear_cache_read_failed", key=cache_key, exc=str(exc))
        return None
    expires_at = float(payload.get("expires_at", 0))
    if expires_at <= time.time():
        return None
    return payload  # type: ignore[no-any-return]


def _cache_write(
    cache_dir: Path, cache_key: str, payload: dict[str, Any]
) -> None:
    """Write payload to the cache atomically (tmp + rename)."""
    cache_file = cache_dir / f"{cache_key}.json"
    tmp = cache_file.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(cache_file)
    except OSError as exc:
        logger.debug("linear_cache_write_failed", key=cache_key, exc=str(exc))


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


def _resolve_cache_key(
    team: str, project: str, state: str, label: str, limit: int
) -> str:
    """Build the canonical cache key used by both _get and _put."""
    fhash = _filter_hash(state=state, label=label, limit=limit)
    return _cache_key(team, project, state or None, fhash)


async def tapps_linear_snapshot_get(
    team: str,
    project: str,
    state: str = "",
    label: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    """Cache-only read of a Linear issue snapshot.

    Returns the cached list of issues for the ``(team, project, state,
    label, limit)`` slice if a fresh entry exists. Otherwise signals a
    miss so the agent can fetch via
    ``mcp__plugin_linear_linear__list_issues`` and then call
    :func:`tapps_linear_snapshot_put` to populate the cache.

    Args:
        team: Linear team name (required).
        project: Linear project name (required).
        state: Optional Linear state type (``"backlog"``, ``"unstarted"``,
            ``"started"``, ``"completed"``, ``"canceled"``). Empty = any.
        label: Optional label name to filter by. Empty = any.
        limit: Max issues the caller requested (part of the cache key).

    Returns:
        Envelope with:
          - ``data.cached``: ``True`` on hit, ``False`` on miss/expired.
          - ``data.issues``: stored list (only on hit).
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
    key = _resolve_cache_key(team, project, state, label, limit)

    cached = _cache_read(cache_dir, key)
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
    return success_response(
        "tapps_linear_snapshot_get",
        elapsed_ms,
        {
            "cached": True,
            "issues": cached.get("issues", []),
            "cache_key": key,
            "cached_at": cached_at,
            "expires_at": cached.get("expires_at"),
            "age_seconds": max(0.0, now - cached_at) if cached_at else None,
            "team": team,
            "project": project,
            "state": state or None,
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
    """Cache-set for a Linear issue snapshot.

    Call after fetching via ``mcp__plugin_linear_linear__list_issues``.
    The ``(team, project, state, label, limit)`` tuple must match the
    earlier :func:`tapps_linear_snapshot_get` call so the cache key
    aligns. TTL is chosen from the ``state`` bucket (see
    ``linear_cache_ttl_open_seconds`` / ``linear_cache_ttl_closed_seconds``).

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
    """Invalidate cached Linear snapshots for a team/project slice.

    Call this after a Linear write (``save_issue``, ``save_comment``)
    so the next :func:`tapps_linear_snapshot_get` reflects the write.
    When both *team* and *project* are empty, invalidates the entire
    Linear snapshot cache.

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


def register(mcp_instance: FastMCP, allowed_tools: frozenset[str]) -> None:
    """Register Linear tools on the shared *mcp_instance*."""
    if "tapps_linear_snapshot_get" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(
            tapps_linear_snapshot_get
        )
    if "tapps_linear_snapshot_put" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_WRITE)(tapps_linear_snapshot_put)
    if "tapps_linear_snapshot_invalidate" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_INVALIDATE)(
            tapps_linear_snapshot_invalidate
        )

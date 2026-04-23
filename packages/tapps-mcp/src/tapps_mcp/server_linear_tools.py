"""Linear tool handlers for TappsMCP (TAP-964).

Provides ``tapps_linear_snapshot`` — a read-through cache over Linear's
``list_issues`` GraphQL query. Backed by a file-based cache under
``<project_root>/.tapps-mcp-cache/linear-snapshots/``.

TTL is enforced by an ``expires_at`` timestamp stored in each cached
value (state-dependent: open/in-progress issues use a short TTL, closed
issues use a longer one). Cache misses fall through to Linear's GraphQL
API; configure with ``TAPPS_MCP_LINEAR_API_KEY``.

Companion tool ``tapps_linear_snapshot_invalidate`` drops cached entries
for a specific ``(team, project)`` slice after a known write.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
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
    openWorldHint=True,
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
_GRAPHQL_QUERY = """
query ListIssues(
  $team: String
  $project: String
  $state: String
  $label: String
  $limit: Int
) {
  issues(
    first: $limit
    filter: {
      team: { name: { eq: $team } }
      project: { name: { eq: $project } }
      state: { type: { eq: $state } }
      labels: { name: { eq: $label } }
    }
  ) {
    nodes {
      id
      identifier
      title
      priority
      url
      state { name type }
      team { id name }
      project { id name }
      labels { nodes { name } }
      updatedAt
      createdAt
    }
  }
}
""".strip()


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


async def _fetch_from_linear(
    api_url: str,
    api_key: str,
    *,
    team: str,
    project: str,
    state: str | None,
    label: str | None,
    limit: int,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    """Call Linear's GraphQL API and return a list of issue dicts."""
    variables = {
        "team": team or None,
        "project": project or None,
        "state": state or None,
        "label": label or None,
        "limit": limit,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            api_url,
            headers={
                "Authorization": api_key,
                "Content-Type": "application/json",
            },
            json={"query": _GRAPHQL_QUERY, "variables": variables},
        )
        response.raise_for_status()
        body = response.json()
    if "errors" in body:
        raise RuntimeError(f"Linear GraphQL error: {body['errors']}")
    nodes = body.get("data", {}).get("issues", {}).get("nodes", [])
    return list(nodes)


async def tapps_linear_snapshot(
    team: str,
    project: str,
    state: str = "",
    label: str = "",
    limit: int = 50,
    bypass_cache: bool = False,
) -> dict[str, Any]:
    """Read-through cached snapshot of Linear issues for a team/project slice.

    Cache-first: returns cached result when fresh (TTL configured via
    ``linear_cache_ttl_open_seconds`` / ``linear_cache_ttl_closed_seconds``).
    On miss or expiry, fetches from Linear's GraphQL API, caches, and
    returns.

    Args:
        team: Linear team name (required). Narrow the query.
        project: Linear project name (required). Narrow the query.
        state: Optional Linear state type (``"backlog"``, ``"unstarted"``,
            ``"started"``, ``"completed"``, ``"canceled"``). Empty = any.
        label: Optional label name to filter by. Empty = any.
        limit: Max issues to return (default 50, Linear max 250).
        bypass_cache: When True, skip the cache read and force a fetch.
            Used for invalidation testing and staleness debugging.

    Returns:
        Envelope dict with:
          - ``data.issues``: list of Linear issue dicts
          - ``data.from_cache``: bool, whether served from cache
          - ``data.cache_key``: the cache-file stem (for invalidation)
          - ``data.cached_at`` / ``data.expires_at``: unix timestamps
          - ``degraded``: True when Linear API key missing or fetch failed
    """
    _record_call("tapps_linear_snapshot")
    start_ns = time.perf_counter_ns()

    if not team or not project:
        return error_response(
            "tapps_linear_snapshot",
            "invalid_input",
            "team and project are required and must be non-empty",
        )

    settings = load_settings()
    cache_dir = _cache_dir(settings.project_root)
    fhash = _filter_hash(state=state, label=label, limit=limit)
    key = _cache_key(team, project, state or None, fhash)

    # Cache read
    if not bypass_cache:
        cached = _cache_read(cache_dir, key)
        if cached is not None:
            elapsed_ms = (time.perf_counter_ns() - start_ns) // 1_000_000
            return success_response(
                "tapps_linear_snapshot",
                elapsed_ms,
                {
                    "issues": cached.get("issues", []),
                    "from_cache": True,
                    "cache_key": key,
                    "cached_at": cached.get("cached_at"),
                    "expires_at": cached.get("expires_at"),
                    "state": state or None,
                },
            )

    # Cache miss → fetch from Linear
    if settings.linear_api_key is None:
        elapsed_ms = (time.perf_counter_ns() - start_ns) // 1_000_000
        return success_response(
            "tapps_linear_snapshot",
            elapsed_ms,
            {
                "issues": [],
                "from_cache": False,
                "cache_key": key,
                "state": state or None,
                "hint": (
                    "Set TAPPS_MCP_LINEAR_API_KEY to enable live Linear "
                    "fetches. Without it, the tool returns an empty slice."
                ),
            },
            degraded=True,
        )

    api_key = settings.linear_api_key.get_secret_value()
    try:
        issues = await _fetch_from_linear(
            settings.linear_api_url,
            api_key,
            team=team,
            project=project,
            state=state or None,
            label=label or None,
            limit=limit,
            timeout=float(settings.tool_timeout),
        )
    except (httpx.HTTPError, RuntimeError) as exc:
        elapsed_ms = (time.perf_counter_ns() - start_ns) // 1_000_000
        logger.warning("linear_fetch_failed", exc=str(exc))
        return success_response(
            "tapps_linear_snapshot",
            elapsed_ms,
            {
                "issues": [],
                "from_cache": False,
                "cache_key": key,
                "state": state or None,
                "fetch_error": str(exc),
            },
            degraded=True,
        )

    now = time.time()
    ttl = _ttl_for_state(
        state or None,
        settings.linear_cache_ttl_open_seconds,
        settings.linear_cache_ttl_closed_seconds,
    )
    payload: dict[str, Any] = {
        "issues": issues,
        "cached_at": now,
        "expires_at": now + ttl,
        "state": state or None,
        "team": team,
        "project": project,
    }
    if ttl > 0:
        _cache_write(cache_dir, key, payload)

    elapsed_ms = (time.perf_counter_ns() - start_ns) // 1_000_000
    return success_response(
        "tapps_linear_snapshot",
        elapsed_ms,
        {
            "issues": issues,
            "from_cache": False,
            "cache_key": key,
            "cached_at": now,
            "expires_at": now + ttl,
            "state": state or None,
        },
    )


async def tapps_linear_snapshot_invalidate(
    team: str = "",
    project: str = "",
) -> dict[str, Any]:
    """Invalidate cached Linear snapshots for a team/project slice.

    Call this after writing to Linear (e.g. ``save_issue``, ``save_comment``)
    to ensure the next ``tapps_linear_snapshot`` read reflects the write.
    When both *team* and *project* are empty, invalidates the entire
    Linear snapshot cache.

    Args:
        team: Linear team name prefix. Empty matches all teams.
        project: Linear project name prefix. Empty matches all projects.

    Returns:
        Envelope dict with ``data.removed`` (count of cache files deleted)
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
    if "tapps_linear_snapshot" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_READ_ONLY)(tapps_linear_snapshot)
    if "tapps_linear_snapshot_invalidate" in allowed_tools:
        mcp_instance.tool(annotations=_ANNOTATIONS_INVALIDATE)(
            tapps_linear_snapshot_invalidate
        )

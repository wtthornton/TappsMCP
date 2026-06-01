"""TAP-2010: Server-side refusal envelope for the Linear cache-first read gate.

Checks that ``tapps_linear_snapshot_get`` has been called recently (within
``_SENTINEL_MAX_AGE_S`` seconds, matching the PreToolUse hook) before allowing
a Linear ``list_issues`` call to proceed.

The sentinel is written by ``.claude/hooks/tapps-post-linear-snapshot-get.sh``
at ``.tapps-mcp/.linear-snapshot-sentinel-{key}`` where *key* encodes the
``(team, project, state, label, limit)`` slice.

This module provides the Python-side gate as defence-in-depth alongside the
bash warn-mode hook (``.claude/hooks/tapps-pre-linear-list.sh``).  Clients
that understand the structured envelope self-correct; older clients see a
plain error instead of silent stale data.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

# Sentinel TTL — must match tapps-pre-linear-list.sh (300 s = 5 min)
_SENTINEL_MAX_AGE_S: int = 300

# Sentinel file prefix relative to project root
_SENTINEL_PREFIX: str = ".tapps-mcp/.linear-snapshot-sentinel-"

# Open-bucket states (TAP-1374): snapshot_get(state="open") covers all of these
_OPEN_BUCKET_STATES: frozenset[str] = frozenset({"backlog", "unstarted", "started", "triage"})


def _sentinel_key(
    team: str,
    project: str,
    state: str,
    label: str,
    limit: int,
) -> str:
    """Compute the sentinel key matching the bash hook and ``_resolve_cache_key``.

    Delegates to ``tapps_mcp.server_linear_tools._resolve_cache_key`` so
    both Python paths stay in lockstep with the bash hook's hash algorithm.
    """
    from tapps_mcp.server_linear_tools import _resolve_cache_key

    return _resolve_cache_key(team, project, state, label, limit)


def _sentinel_is_fresh(project_dir: Path, key: str) -> bool:
    """Return True if the sentinel file for *key* exists and is within TTL."""
    sentinel = project_dir / f"{_SENTINEL_PREFIX}{key}"
    if not sentinel.exists():
        return False
    try:
        age = time.time() - float(sentinel.read_text(encoding="utf-8").strip())
        return 0 <= age <= _SENTINEL_MAX_AGE_S
    except (ValueError, OSError):
        return False


def _alias_keys(
    team: str,
    project: str,
    state: str,
    label: str,
    limit: int,
) -> list[str]:
    """Return open-bucket alias keys for *state* (TAP-1374).

    When ``tapps_linear_snapshot_get`` is called with ``state="open"`` (or
    any open-bucket member), the PostToolUse hook also writes alias sentinels
    for every other open-bucket variant.  This mirrors that logic so a
    ``list_issues(state="backlog")`` call passes the gate after a
    ``snapshot_get(state="open")`` or vice-versa.
    """
    state_lc = state.lower() if state else ""
    if state_lc not in _OPEN_BUCKET_STATES and state_lc not in ("open", ""):
        return []

    from tapps_mcp.server_linear_tools import _resolve_cache_key

    seen: set[str] = set()
    aliases: list[str] = []
    for candidate in (*_OPEN_BUCKET_STATES, "open", ""):
        k = _resolve_cache_key(team, project, candidate, label, limit)
        if k not in seen:
            seen.add(k)
            aliases.append(k)
    return aliases


def check_snapshot_sentinel(
    project_dir: Path,
    team: str,
    project: str,
    state: str,
    label: str,
    limit: int,
) -> bool:
    """Return True if a fresh ``tapps_linear_snapshot_get`` sentinel exists.

    Checks both the primary key and open-bucket alias keys (TAP-1374) so
    a ``snapshot_get(state="open")`` satisfies a
    ``tapps_linear_list_issues(state="backlog")`` gate check.
    """
    primary_key = _sentinel_key(team, project, state, label, limit)
    if _sentinel_is_fresh(project_dir, primary_key):
        return True

    for alias_key in _alias_keys(team, project, state, label, limit):
        if _sentinel_is_fresh(project_dir, alias_key):
            return True

    return False


def gate_miss_envelope(
    team: str,
    project: str,
    state: str,
    label: str,
    limit: int,
    key: str,
) -> dict[str, Any]:
    """Return the Agent-Gateway ``gate_miss`` refusal envelope.

    The envelope shape follows the spec in
    ``docs/architecture/gateway-envelope.md``.
    """
    args: dict[str, Any] = {"team": team, "project": project}
    if state:
        args["state"] = state
    if label:
        args["label"] = label
    if limit != 50:
        args["limit"] = limit

    return {
        "ok": False,
        "code": "gate_miss",
        "gate": "linear_cache_first_read",
        "use": "tapps_linear_snapshot_get",
        "args": args,
        "hint": (
            "Call tapps_linear_snapshot_get(team, project, state) first. "
            "On cached=true use data.issues directly. "
            "On cached=false, call list_issues then tapps_linear_snapshot_put. "
            "The sentinel expires after 5 minutes."
        ),
        "bypass_env": "TAPPS_LINEAR_SKIP_CACHE_GATE",
        "logged_to": ".tapps-mcp/.cache-gate-violations.jsonl",
        "extra": {"expected_sentinel_key": key},
    }


def gate_linear_list(
    project_dir: Path,
    team: str,
    project: str,
    state: str = "",
    label: str = "",
    limit: int = 50,
) -> dict[str, Any] | None:
    """Check the linear cache-first read gate.

    Returns:
        ``None`` when the gate passes — the caller should proceed to
        ``mcp__plugin_linear_linear__list_issues``.
        A ``gate_miss`` refusal envelope when the gate fires.

    Bypass:
        Set ``TAPPS_LINEAR_SKIP_CACHE_GATE=1`` in the environment to skip
        the sentinel check.  Bypasses are logged by the bash hook; the
        server-side path just passes through.
    """
    if os.environ.get("TAPPS_LINEAR_SKIP_CACHE_GATE"):
        return None
    if check_snapshot_sentinel(project_dir, team, project, state, label, limit):
        return None
    key = _sentinel_key(team, project, state, label, limit)
    return gate_miss_envelope(team, project, state, label, limit, key)

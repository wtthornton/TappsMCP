"""Linear snapshot cache primitives — filesystem I/O, pruning, and stats.

Split under TAP-5606 from ``server_linear_tools.py``. Imports only
:mod:`tapps_mcp.server_linear_tools_keys` (leaf) — never
:mod:`tapps_mcp.server_linear_tools_handlers` or the facade — so the import
graph stays acyclic: keys -> cache -> handlers -> facade.
"""

from __future__ import annotations

import json
import operator
import time
from pathlib import Path
from typing import Any

import structlog

from tapps_core.cache import AtomicJsonCache, TTLStaleness, register_cache_stats
from tapps_core.config.settings import load_settings

logger = structlog.get_logger(__name__)

_CACHE_SUBDIR = "linear-snapshots"
_CACHE_MAX_FILES = 500
_CACHE_STALE_TTL_MULTIPLIER = 10


def _cache_dir(project_root: Path) -> Path:
    """Return the cache directory for Linear snapshots, creating if needed."""
    cache_dir = project_root / ".tapps-mcp-cache" / _CACHE_SUBDIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


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
        survivors.sort(key=operator.itemgetter(1))
        for entry, _ in survivors[: len(survivors) - _CACHE_MAX_FILES]:
            try:
                entry.unlink()
                removed += 1
            except OSError as exc:
                logger.debug("linear_cache_lru_unlink_failed", path=str(entry), exc=str(exc))

    if removed:
        logger.debug("linear_cache_pruned", removed=removed, dir=str(cache_dir))
    return removed


def _cache_invalidate_glob(cache_dir: Path, pattern: str) -> int:
    """Remove cache files whose stems match glob *pattern*. Return count removed."""
    count = 0
    for entry in cache_dir.glob(f"{pattern}.json"):
        try:
            entry.unlink()
            count += 1
        except OSError as exc:
            logger.debug("linear_cache_invalidate_failed", path=str(entry), exc=str(exc))
    return count

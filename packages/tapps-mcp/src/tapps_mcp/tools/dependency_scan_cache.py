"""Session-level cache for dependency vulnerability scan results.

Dependency scanning is project-level, not file-level. Results are cached
and reused across tapps_score_file calls to avoid re-running pip-audit
for every file. Populated by tapps_session_start and tapps_validate_changed.
"""

from __future__ import annotations

import time

from tapps_core.cache import TTLStaleness, register_cache_stats
from tapps_mcp.tools.pip_audit import VulnerabilityFinding

# TTL in seconds (5 minutes)
_CACHE_TTL = 300

_cache: dict[str, tuple[list[VulnerabilityFinding], float]] = {}

# ADR-0029 / TAP-4561: unified cache-stats counters.
_stats: dict[str, int] = {"hits": 0, "misses": 0}


def _dependency_scan_stats() -> dict[str, object]:
    """Stats provider: counters + staleness/age of the freshest entry (TAP-4558).

    ``age_seconds`` is the age of the most-recently populated entry (or ``None``
    when the cache is empty); ``stale`` reports whether that freshest entry has
    already aged past the TTL. This gives the unified ``tapps_stats.caches``
    surface the same age/staleness signal the code-graph cache already exposes.
    """
    out: dict[str, object] = {**_stats, "size": len(_cache)}
    if _cache:
        newest_ts = max(ts for _, ts in _cache.values())
        age = time.monotonic() - newest_ts
        out["age_seconds"] = round(age, 1)
        out["stale"] = TTLStaleness(float(_CACHE_TTL), now_fn=time.monotonic).is_stale(newest_ts)
    else:
        out["age_seconds"] = None
        out["stale"] = None
    return out


register_cache_stats("dependency_scan", _dependency_scan_stats)


def set_dependency_findings(project_root: str, findings: list[VulnerabilityFinding]) -> None:
    """Store dependency scan results for the given project root."""
    _cache[str(project_root)] = (findings, time.monotonic())


def get_dependency_findings(project_root: str, ttl: int = _CACHE_TTL) -> list[VulnerabilityFinding]:
    """Return cached dependency findings if present and not expired."""
    entry = _cache.get(str(project_root))
    if entry is None:
        _stats["misses"] += 1
        return []
    findings, ts = entry
    if TTLStaleness(float(ttl), now_fn=time.monotonic).is_stale(ts):
        _cache.pop(str(project_root), None)
        _stats["misses"] += 1
        return []
    _stats["hits"] += 1
    return findings


def clear_dependency_cache(project_root: str | None = None) -> None:
    """Clear cache for a project or all projects (for testing)."""
    if project_root is None:
        _cache.clear()
    else:
        _cache.pop(str(project_root), None)

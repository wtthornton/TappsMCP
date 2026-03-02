"""Session-level cache for dependency vulnerability scan results.

Dependency scanning is project-level, not file-level. Results are cached
and reused across tapps_score_file calls to avoid re-running pip-audit
for every file. Populated by tapps_session_start and tapps_validate_changed.
"""

from __future__ import annotations

import time

from tapps_mcp.tools.pip_audit import VulnerabilityFinding

# TTL in seconds (5 minutes)
_CACHE_TTL = 300

_cache: dict[str, tuple[list[VulnerabilityFinding], float]] = {}


def set_dependency_findings(project_root: str, findings: list[VulnerabilityFinding]) -> None:
    """Store dependency scan results for the given project root."""
    _cache[str(project_root)] = (findings, time.monotonic())


def get_dependency_findings(
    project_root: str, ttl: int = _CACHE_TTL
) -> list[VulnerabilityFinding]:
    """Return cached dependency findings if present and not expired."""
    entry = _cache.get(str(project_root))
    if entry is None:
        return []
    findings, ts = entry
    if time.monotonic() - ts > ttl:
        del _cache[str(project_root)]
        return []
    return findings


def clear_dependency_cache(project_root: str | None = None) -> None:
    """Clear cache for a project or all projects (for testing)."""
    if project_root is None:
        _cache.clear()
    else:
        _cache.pop(str(project_root), None)

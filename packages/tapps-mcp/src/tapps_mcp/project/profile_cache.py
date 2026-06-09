"""Disk cache for ``detect_project_profile`` summary (TAP-3253).

Avoids a full repo scan on every new MCP subprocess when project markers
(``pyproject.toml``, etc.) are unchanged since the last detection run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

PROFILE_CACHE_REL = ".tapps-mcp/profile-cache.json"

# Marker files whose mtime invalidates the cache when changed.
_PROFILE_MARKERS: tuple[str, ...] = (
    "pyproject.toml",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "setup.py",
)


def profile_marker_fingerprint(project_root: Path) -> str:
    """Stable fingerprint from marker-file mtimes under *project_root*."""
    import hashlib

    parts: list[str] = []
    for name in _PROFILE_MARKERS:
        path = project_root / name
        if path.is_file():
            parts.append(f"{name}:{path.stat().st_mtime_ns}")
    if not parts:
        parts.append(f"root:{project_root.resolve().stat().st_mtime_ns}")
    digest = hashlib.sha256("|".join(sorted(parts)).encode()).hexdigest()
    return digest[:16]


def _cache_path(project_root: Path) -> Path:
    return project_root / PROFILE_CACHE_REL


def load_cached_profile_summary(
    project_root: Path,
    fingerprint: str,
) -> dict[str, Any] | None:
    """Return cached profile summary when *fingerprint* matches on disk."""
    path = _cache_path(project_root)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("profile_cache_read_failed", path=str(path), error=str(exc))
        return None
    if not isinstance(raw, dict):
        return None
    if raw.get("fingerprint") != fingerprint:
        return None
    profile = raw.get("profile")
    if not isinstance(profile, dict):
        return None
    return profile


def save_cached_profile_summary(
    project_root: Path,
    fingerprint: str,
    profile_data: dict[str, Any],
) -> None:
    """Persist *profile_data* with *fingerprint* for future cold starts."""
    path = _cache_path(project_root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"fingerprint": fingerprint, "profile": profile_data}
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("profile_cache_write_failed", path=str(path), error=str(exc))

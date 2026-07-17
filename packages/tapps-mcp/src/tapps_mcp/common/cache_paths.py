"""Shared knowledge-base cache directory resolution (Fix E, v5).

Extracted from ``tapps_mcp.server._bootstrap_cache_dir`` so every caller
(server startup, lookup engine, usage gap analysis, session-start cache
warming) resolves the *same* cache directory instead of hardcoding
``.tapps-mcp-cache`` and silently ignoring ``TAPPS_CACHE_DIR`` / the
temp-dir fallback.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_CACHE_DIR_NAME = ".tapps-mcp-cache"


def resolve_kb_cache_dir(project_root: Path) -> tuple[Path, bool]:
    """Create the KB cache directory, returning ``(cache_dir, fallback_used)``.

    Priority:
    1. ``TAPPS_CACHE_DIR`` env var (if set)
    2. ``<project_root>/.tapps-mcp-cache``
    3. ``<tempdir>/.tapps-mcp-cache`` (fallback when project root not writable)
    """
    cache_dir = (
        Path(os.environ["TAPPS_CACHE_DIR"])
        if os.environ.get("TAPPS_CACHE_DIR")
        else (project_root / _CACHE_DIR_NAME)
    )
    fallback_used = False

    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError):
        # Fall back to temp directory if primary path not writable
        cache_dir = Path(tempfile.gettempdir()) / _CACHE_DIR_NAME
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            fallback_used = True
        except (PermissionError, OSError):
            logger.debug("cache_dir_creation_failed", cache_dir=str(cache_dir))

    return cache_dir, fallback_used

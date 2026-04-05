"""Shared utility functions to eliminate cross-module duplication."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "env",
        "ENV",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        "dist",
        "build",
        ".tox",
        ".eggs",
        "htmlcov",
        ".mypy_cache",
        ".tapps-agents",
        ".tapps-mcp-cache",
        "site-packages",
    }
)


def should_skip_path(path: Path) -> bool:
    """Return True if any component of *path* is in SKIP_DIRS or matches a skip prefix."""
    return any(
        part in SKIP_DIRS or part.startswith(".venv")
        for part in path.parts
    )


def utc_now() -> datetime:
    """Return the current UTC datetime (timezone-aware)."""
    return datetime.now(tz=UTC)


def ensure_dir(path: Path) -> Path:
    """Create directory (and parents) if it does not exist. Returns the path."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_text_utf8(path: Path) -> str:
    """Read a file as UTF-8 text."""
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Docker / container detection (Story 75.1)
# ---------------------------------------------------------------------------


def is_running_in_container() -> bool:
    """Detect whether the current process runs inside a Docker/OCI container.

    Checks (in order):
    1. ``TAPPS_DOCKER=1`` environment variable (explicit opt-in).
    2. Existence of ``/.dockerenv`` sentinel file.
    3. ``/proc/1/cgroup`` containing ``docker`` or ``containerd`` strings (Linux).
    """
    if os.environ.get("TAPPS_DOCKER", "").strip() == "1":
        return True

    if Path("/.dockerenv").exists():
        return True

    cgroup_path = Path("/proc/1/cgroup")
    if cgroup_path.exists():
        try:
            text = cgroup_path.read_text(encoding="utf-8", errors="replace")
            if "docker" in text or "containerd" in text:
                return True
        except OSError:
            pass

    return False


def get_path_mapping() -> dict[str, Any]:
    """Return a container→host path mapping dict for session responses.

    When ``TAPPS_HOST_ROOT`` is set, the mapping is considered available and
    :func:`translate_path` can convert host paths to container-relative ones.

    Returns a dict with keys:
        container_root, host_root, mapping_available
    """
    import os as _os

    container_root = str(Path.cwd())
    host_root = _os.environ.get("TAPPS_HOST_ROOT", "")
    return {
        "container_root": container_root,
        "host_root": host_root,
        "mapping_available": bool(host_root.strip()),
    }


def translate_path(host_path: str) -> str:
    """Translate a *host_path* to the container-relative equivalent.

    If ``TAPPS_HOST_ROOT`` is set and *host_path* starts with that prefix,
    the prefix is replaced with the container CWD.  Otherwise *host_path*
    is returned unchanged.
    """
    host_root = os.environ.get("TAPPS_HOST_ROOT", "").strip()
    if not host_root:
        return host_path

    # Normalise separators for cross-platform comparison
    normalised = host_path.replace("\\", "/")
    host_root_norm = host_root.replace("\\", "/").rstrip("/")

    if normalised.startswith(host_root_norm):
        suffix = normalised[len(host_root_norm):]
        container_root = str(Path.cwd())
        return container_root.rstrip("/") + suffix

    return host_path

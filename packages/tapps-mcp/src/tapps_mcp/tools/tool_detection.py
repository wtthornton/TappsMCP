"""Detect installed external quality tools and their versions."""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import structlog

from tapps_core.common.models import InstalledTool
from tapps_mcp.tools.subprocess_runner import run_command, run_command_async

_logger = structlog.get_logger(__name__)

# Tools we check for, with their version flags and install hints
_TOOL_SPECS: list[dict[str, str]] = [
    {
        "name": "ruff",
        "version_flag": "--version",
        "install_hint": "pip install ruff",
    },
    {
        "name": "mypy",
        "version_flag": "--version",
        "install_hint": "pip install mypy",
    },
    {
        "name": "bandit",
        "version_flag": "--version",
        "install_hint": "pip install bandit",
    },
    {
        "name": "radon",
        "version_flag": "--version",
        "install_hint": "pip install radon",
    },
    {
        "name": "vulture",
        "version_flag": "--version",
        "install_hint": "pip install vulture",
    },
    {
        "name": "pip-audit",
        "version_flag": "--version",
        "install_hint": "pip install pip-audit",
    },
]

# Per-tool timeout overrides for version checks (seconds).
# mypy can be slow on first run in cold environments.
_TOOL_TIMEOUTS: dict[str, int] = {"mypy": 20}

# Process-lifetime cache for tool detection results.
_cached_tools: list[InstalledTool] | None = None

# Disk cache validity period (24 hours).
_DISK_CACHE_MAX_AGE_SECONDS = 24 * 60 * 60

# Disk cache filename (relative to .tapps-mcp/ directory).
_DISK_CACHE_FILENAME = "tool-versions.json"


def _reset_tools_cache() -> None:
    """Reset the cached tool detection results.

    Call after installing or removing tools mid-session, or in test teardown.
    """
    global _cached_tools
    _cached_tools = None


def _get_disk_cache_path() -> Path | None:
    """Return the path to the disk cache file, or None if unavailable."""
    try:
        from tapps_core.config.settings import load_settings

        settings = load_settings()
        return settings.project_root / ".tapps-mcp" / _DISK_CACHE_FILENAME
    except Exception:
        _logger.debug("disk_cache_path_unavailable", exc_info=True)
        return None


def _write_disk_cache(tools: list[InstalledTool]) -> None:
    """Persist tool detection results to disk (best-effort, never raises)."""
    cache_path = _get_disk_cache_path()
    if cache_path is None:
        return
    try:
        data: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "timestamp_epoch": time.time(),
            "platform": sys.platform,
            "tools": [t.model_dump() for t in tools],
        }
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        _logger.debug("disk_cache_written", path=str(cache_path))
    except Exception:
        _logger.debug("disk_cache_write_failed", exc_info=True)


def _read_disk_cache() -> list[InstalledTool] | None:
    """Read tool detection results from disk cache if valid.

    Returns None if cache is missing, expired (>24h), or corrupt.
    """
    cache_path = _get_disk_cache_path()
    if cache_path is None or not cache_path.exists():
        return None
    try:
        raw = cache_path.read_text(encoding="utf-8")
        data = json.loads(raw)

        # Validate structure
        if not isinstance(data, dict) or "tools" not in data or "timestamp_epoch" not in data:
            _logger.debug("disk_cache_invalid_structure")
            return None

        # Check expiry
        age = time.time() - data["timestamp_epoch"]
        if age > _DISK_CACHE_MAX_AGE_SECONDS:
            _logger.debug("disk_cache_expired", age_hours=age / 3600)
            return None

        # Check platform match
        if data.get("platform") != sys.platform:
            _logger.debug("disk_cache_platform_mismatch")
            return None

        tools = [InstalledTool(**t) for t in data["tools"]]
        _logger.debug("disk_cache_hit", tool_count=len(tools))
        return tools
    except Exception:
        _logger.debug("disk_cache_read_failed", exc_info=True)
        return None


def detect_installed_tools(*, force_refresh: bool = False) -> list[InstalledTool]:
    """Probe for known external tools and return their availability.

    Results are cached in memory for the process lifetime and on disk for
    24 hours.  Call :func:`_reset_tools_cache` to clear the in-memory cache.

    Args:
        force_refresh: When True, bypass both memory and disk caches
            (used by ``tapps_doctor`` for fresh results).

    Returns:
        List of ``InstalledTool`` objects.
    """
    global _cached_tools

    if not force_refresh and _cached_tools is not None:
        return list(_cached_tools)

    # Try disk cache (unless force refresh)
    if not force_refresh:
        disk_result = _read_disk_cache()
        if disk_result is not None:
            _cached_tools = disk_result
            return list(_cached_tools)

    results: list[InstalledTool] = []

    for spec in _TOOL_SPECS:
        name = spec["name"]
        available = shutil.which(name) is not None
        version: str | None = None

        if available:
            result = run_command(
                [name, spec["version_flag"]],
                timeout=_TOOL_TIMEOUTS.get(name, 10),
            )
            if result.success:
                # Most tools print version on stdout or stderr
                raw = (result.stdout or result.stderr).strip()
                # Take first line, strip tool name prefix if present
                version = raw.splitlines()[0] if raw else None

        results.append(
            InstalledTool(
                name=name,
                version=version,
                available=available,
                install_hint=spec["install_hint"] if not available else None,
            )
        )

    _cached_tools = results
    _write_disk_cache(results)
    return list(_cached_tools)


async def _check_tool_async(spec: dict[str, str]) -> InstalledTool:
    """Check a single tool asynchronously."""
    name = spec["name"]
    available = shutil.which(name) is not None
    version: str | None = None

    if available:
        result = await run_command_async(
            [name, spec["version_flag"]],
            timeout=_TOOL_TIMEOUTS.get(name, 10),
        )
        if result.success:
            raw = (result.stdout or result.stderr).strip()
            version = raw.splitlines()[0] if raw else None

    return InstalledTool(
        name=name,
        version=version,
        available=available,
        install_hint=spec["install_hint"] if not available else None,
    )


async def detect_installed_tools_async(
    *, force_refresh: bool = False,
) -> list[InstalledTool]:
    """Probe for known external tools in parallel using async subprocesses.

    All 6 tools are checked concurrently via ``asyncio.gather``, giving
    ~3-6x speedup over the sequential :func:`detect_installed_tools`.

    Results share the same process-lifetime cache and disk cache.  Call
    :func:`_reset_tools_cache` to force re-detection.

    Args:
        force_refresh: When True, bypass both memory and disk caches.

    Returns:
        List of ``InstalledTool`` objects.
    """
    global _cached_tools

    if not force_refresh and _cached_tools is not None:
        return list(_cached_tools)

    # Try disk cache (unless force refresh)
    if not force_refresh:
        disk_result = _read_disk_cache()
        if disk_result is not None:
            _cached_tools = disk_result
            return list(_cached_tools)

    results = list(await asyncio.gather(*[_check_tool_async(s) for s in _TOOL_SPECS]))
    _cached_tools = results
    _write_disk_cache(results)
    return list(_cached_tools)

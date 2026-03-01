"""Detect installed external quality tools and their versions."""

from __future__ import annotations

import asyncio
import shutil

from tapps_core.common.models import InstalledTool
from tapps_mcp.tools.subprocess_runner import run_command, run_command_async

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


# Process-lifetime cache for tool detection results.
_cached_tools: list[InstalledTool] | None = None


def _reset_tools_cache() -> None:
    """Reset the cached tool detection results.

    Call after installing or removing tools mid-session, or in test teardown.
    """
    global _cached_tools  # noqa: PLW0603
    _cached_tools = None


def detect_installed_tools() -> list[InstalledTool]:
    """Probe for known external tools and return their availability.

    Results are cached for the process lifetime.  Call
    :func:`_reset_tools_cache` to force re-detection.

    Returns:
        List of ``InstalledTool`` objects.
    """
    global _cached_tools  # noqa: PLW0603
    if _cached_tools is not None:
        return list(_cached_tools)

    results: list[InstalledTool] = []

    for spec in _TOOL_SPECS:
        name = spec["name"]
        available = shutil.which(name) is not None
        version: str | None = None

        if available:
            result = run_command(
                [name, spec["version_flag"]],
                timeout=10,
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
    return list(_cached_tools)


async def _check_tool_async(spec: dict[str, str]) -> InstalledTool:
    """Check a single tool asynchronously."""
    name = spec["name"]
    available = shutil.which(name) is not None
    version: str | None = None

    if available:
        result = await run_command_async(
            [name, spec["version_flag"]],
            timeout=10,
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


async def detect_installed_tools_async() -> list[InstalledTool]:
    """Probe for known external tools in parallel using async subprocesses.

    All 6 tools are checked concurrently via ``asyncio.gather``, giving
    ~3-6x speedup over the sequential :func:`detect_installed_tools`.

    Results share the same process-lifetime cache.  Call
    :func:`_reset_tools_cache` to force re-detection.

    Returns:
        List of ``InstalledTool`` objects.
    """
    global _cached_tools  # noqa: PLW0603
    if _cached_tools is not None:
        return list(_cached_tools)

    results = list(await asyncio.gather(*[_check_tool_async(s) for s in _TOOL_SPECS]))
    _cached_tools = results
    return list(_cached_tools)

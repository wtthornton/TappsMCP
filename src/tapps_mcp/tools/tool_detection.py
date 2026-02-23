"""Detect installed external quality tools and their versions."""

from __future__ import annotations

import shutil

from tapps_mcp.common.models import InstalledTool
from tapps_mcp.tools.subprocess_runner import run_command

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


def detect_installed_tools() -> list[InstalledTool]:
    """Probe for known external tools and return their availability.

    Returns:
        List of ``InstalledTool`` objects.
    """
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

    return results

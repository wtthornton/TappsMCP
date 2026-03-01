"""Load TAPPS pipeline prompt content from package markdown files.

Uses ``importlib.resources`` for package-safe file loading that works in
editable installs, wheel installs, and zip imports.

This is the base prompt loader for the Tapps platform. It can load
resources from any package by passing ``package`` to ``_read_resource``.
The tapps-mcp package extends this with MCP-specific template loading.
"""

from __future__ import annotations

import importlib.resources
import sys
from pathlib import Path

_STAGES = ("discover", "research", "develop", "validate", "verify")

ENGAGEMENT_LEVELS = ("high", "medium", "low")

_DEFAULT_PACKAGE = "tapps_core.prompts"


def list_stages() -> list[str]:
    """Return the ordered list of pipeline stage names."""
    return list(_STAGES)


def _read_resource(filename: str, package: str = _DEFAULT_PACKAGE) -> str:
    """Read a text resource from a prompts package.

    Falls back to ``Path(__file__)``-based resolution when running inside
    a PyInstaller frozen executable where ``importlib.resources`` cannot
    locate package data files.

    Args:
        filename: Name of the markdown file to load.
        package: Dotted package name containing the resource. Defaults to
            ``tapps_core.prompts``.
    """
    if getattr(sys, "frozen", False):
        return (Path(__file__).parent / filename).read_text(encoding="utf-8")
    ref = importlib.resources.files(package).joinpath(filename)
    return ref.read_text(encoding="utf-8")


def load_stage_prompt(stage: str, package: str = _DEFAULT_PACKAGE) -> str:
    """Load the prompt content for a specific pipeline stage.

    Args:
        stage: One of ``discover``, ``research``, ``develop``, ``validate``, ``verify``.
        package: Dotted package name containing the resource.

    Raises:
        ValueError: If *stage* is not a valid stage name.
    """
    if stage not in _STAGES:
        valid = ", ".join(_STAGES)
        msg = f"Invalid stage {stage!r}. Valid stages: {valid}"
        raise ValueError(msg)
    return _read_resource(f"{stage}.md", package=package)


def load_overview(package: str = _DEFAULT_PACKAGE) -> str:
    """Load the full pipeline overview content."""
    return _read_resource("overview.md", package=package)


def load_handoff_template(package: str = _DEFAULT_PACKAGE) -> str:
    """Load the TAPPS_HANDOFF.md template."""
    return _read_resource("handoff_template.md", package=package)


def load_runlog_template(package: str = _DEFAULT_PACKAGE) -> str:
    """Load the TAPPS_RUNLOG.md template."""
    return _read_resource("runlog_template.md", package=package)

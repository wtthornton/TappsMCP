"""Load TAPPS pipeline prompt content from package markdown files.

Uses ``importlib.resources`` for package-safe file loading that works in
editable installs, wheel installs, and zip imports.

Base prompt loading is delegated to ``tapps_core.prompts.prompt_loader``.
This module adds MCP-specific template loading (agents, platform rules).
"""

from __future__ import annotations

import importlib.resources
import sys
from pathlib import Path

# Re-export base functions from tapps_core
from tapps_core.prompts.prompt_loader import ENGAGEMENT_LEVELS as ENGAGEMENT_LEVELS
from tapps_core.prompts.prompt_loader import list_stages as list_stages
from tapps_core.prompts.prompt_loader import load_handoff_template as load_handoff_template
from tapps_core.prompts.prompt_loader import load_overview as load_overview
from tapps_core.prompts.prompt_loader import load_runlog_template as load_runlog_template
from tapps_core.prompts.prompt_loader import load_stage_prompt as load_stage_prompt

_PACKAGE = "tapps_mcp.prompts"


def _read_resource(filename: str) -> str:
    """Read a text resource from the tapps_mcp prompts package.

    Falls back to ``Path(__file__)``-based resolution when running inside
    a PyInstaller frozen executable where ``importlib.resources`` cannot
    locate package data files.
    """
    if getattr(sys, "frozen", False):
        return (Path(__file__).parent / filename).read_text(encoding="utf-8")
    ref = importlib.resources.files(_PACKAGE).joinpath(filename)
    return ref.read_text(encoding="utf-8")


def load_agents_template(engagement_level: str = "medium") -> str:
    """Load the AGENTS.md template for consuming projects.

    Args:
        engagement_level: One of ``"high"``, ``"medium"``, ``"low"``. Selects
            the template variant (mandatory vs balanced vs optional language).
            Default ``"medium"`` preserves backward compatibility.

    Returns:
        Template content with version marker prepended so that
        ``AgentsValidation`` considers a freshly-written file up-to-date.

    Raises:
        ValueError: If *engagement_level* is not one of high, medium, low.
    """
    from tapps_mcp import __version__

    if engagement_level not in ENGAGEMENT_LEVELS:
        msg = (
            f"Invalid engagement_level {engagement_level!r}. Valid: {', '.join(ENGAGEMENT_LEVELS)}"
        )
        raise ValueError(msg)
    content = _read_resource(f"agents_template_{engagement_level}.md")
    return f"<!-- tapps-agents-version: {__version__} -->\n{content}"


def load_platform_rules(platform: str, engagement_level: str = "medium") -> str:
    """Load platform-specific rule content.

    Args:
        platform: ``"claude"`` or ``"cursor"``.
        engagement_level: One of ``"high"``, ``"medium"``, ``"low"``. Selects
            the template variant. Default ``"medium"`` preserves backward
            compatibility.

    Raises:
        ValueError: If *platform* or *engagement_level* is not recognized.
    """
    valid_platforms = ("claude", "cursor")
    if platform not in valid_platforms:
        msg = f"Invalid platform {platform!r}. Valid: {', '.join(valid_platforms)}"
        raise ValueError(msg)
    if engagement_level not in ENGAGEMENT_LEVELS:
        msg = (
            f"Invalid engagement_level {engagement_level!r}. Valid: {', '.join(ENGAGEMENT_LEVELS)}"
        )
        raise ValueError(msg)
    return _read_resource(f"platform_{platform}_{engagement_level}.md")

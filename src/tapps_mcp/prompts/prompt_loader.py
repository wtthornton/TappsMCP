"""Load TAPPS pipeline prompt content from package markdown files.

Uses ``importlib.resources`` for package-safe file loading that works in
editable installs, wheel installs, and zip imports.
"""

from __future__ import annotations

import importlib.resources

_STAGES = ("discover", "research", "develop", "validate", "verify")

ENGAGEMENT_LEVELS = ("high", "medium", "low")

_PACKAGE = "tapps_mcp.prompts"


def list_stages() -> list[str]:
    """Return the ordered list of pipeline stage names."""
    return list(_STAGES)


def _read_resource(filename: str) -> str:
    """Read a text resource from the prompts package."""
    ref = importlib.resources.files(_PACKAGE).joinpath(filename)
    return ref.read_text(encoding="utf-8")


def load_stage_prompt(stage: str) -> str:
    """Load the prompt content for a specific pipeline stage.

    Args:
        stage: One of ``discover``, ``research``, ``develop``, ``validate``, ``verify``.

    Raises:
        ValueError: If *stage* is not a valid stage name.
    """
    if stage not in _STAGES:
        valid = ", ".join(_STAGES)
        msg = f"Invalid stage {stage!r}. Valid stages: {valid}"
        raise ValueError(msg)
    return _read_resource(f"{stage}.md")


def load_overview() -> str:
    """Load the full pipeline overview content."""
    return _read_resource("overview.md")


def load_handoff_template() -> str:
    """Load the TAPPS_HANDOFF.md template."""
    return _read_resource("handoff_template.md")


def load_runlog_template() -> str:
    """Load the TAPPS_RUNLOG.md template."""
    return _read_resource("runlog_template.md")


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
            f"Invalid engagement_level {engagement_level!r}. "
            f"Valid: {', '.join(ENGAGEMENT_LEVELS)}"
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
            f"Invalid engagement_level {engagement_level!r}. "
            f"Valid: {', '.join(ENGAGEMENT_LEVELS)}"
        )
        raise ValueError(msg)
    return _read_resource(f"platform_{platform}_{engagement_level}.md")

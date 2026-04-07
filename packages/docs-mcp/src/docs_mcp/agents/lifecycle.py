"""Agent lifecycle management for catalog governance.

Handles soft-delete (deprecation) and cleanup of agents that have
been deprecated beyond the retention period.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
import yaml

from docs_mcp.agents.catalog import AgentCatalog
from docs_mcp.agents.models import AgentConfig

logger: Any = structlog.get_logger(__name__)

# Default retention period for deprecated agents (30 days in seconds)
DEFAULT_RETENTION_SECONDS: int = 30 * 24 * 60 * 60

# Frontmatter key for deprecation timestamp
DEPRECATED_AT_KEY: str = "deprecated_at"


@dataclass(frozen=True)
class DeprecationResult:
    """Result of deprecating an agent."""

    agent_name: str
    success: bool
    message: str


@dataclass(frozen=True)
class CleanupResult:
    """Result of running lifecycle cleanup."""

    agents_checked: int
    agents_removed: int
    removed_names: list[str]
    retention_days: int


def deprecate_agent(
    catalog: AgentCatalog,
    agent_name: str,
    agent_dir: Path | None = None,
) -> DeprecationResult:
    """Mark an agent as deprecated.

    Sets the ``deprecated`` flag to True on the AgentConfig. If agent_dir
    is provided and the agent has a source_path, updates the AGENT.md
    frontmatter on disk.

    Args:
        catalog: The agent catalog.
        agent_name: Name of the agent to deprecate.
        agent_dir: Optional directory containing AGENT.md files for
            persisting the deprecation to disk.

    Returns:
        DeprecationResult indicating success or failure.
    """
    agent = catalog.get(agent_name)
    if agent is None:
        return DeprecationResult(
            agent_name=agent_name,
            success=False,
            message=f"Agent '{agent_name}' not found in catalog.",
        )

    if agent.deprecated:
        return DeprecationResult(
            agent_name=agent_name,
            success=True,
            message=f"Agent '{agent_name}' is already deprecated.",
        )

    # Update in-memory
    agent.deprecated = True

    # Persist to disk if possible
    source = agent.source_path
    if source is not None and source.exists():
        _update_frontmatter_deprecated(source, deprecated=True)
        logger.info("agent_deprecated_on_disk", name=agent_name, path=str(source))

    logger.info("agent_deprecated", name=agent_name)
    return DeprecationResult(
        agent_name=agent_name,
        success=True,
        message=f"Agent '{agent_name}' has been deprecated.",
    )


def restore_agent(
    catalog: AgentCatalog,
    agent_name: str,
) -> DeprecationResult:
    """Restore a deprecated agent to active status.

    Args:
        catalog: The agent catalog.
        agent_name: Name of the agent to restore.

    Returns:
        DeprecationResult indicating success or failure.
    """
    agent = catalog.get(agent_name)
    if agent is None:
        return DeprecationResult(
            agent_name=agent_name,
            success=False,
            message=f"Agent '{agent_name}' not found in catalog.",
        )

    if not agent.deprecated:
        return DeprecationResult(
            agent_name=agent_name,
            success=True,
            message=f"Agent '{agent_name}' is already active.",
        )

    agent.deprecated = False

    source = agent.source_path
    if source is not None and source.exists():
        _update_frontmatter_deprecated(source, deprecated=False)

    logger.info("agent_restored", name=agent_name)
    return DeprecationResult(
        agent_name=agent_name,
        success=True,
        message=f"Agent '{agent_name}' has been restored to active status.",
    )


def cleanup_deprecated(
    catalog: AgentCatalog,
    retention_seconds: int = DEFAULT_RETENTION_SECONDS,
    current_time: float | None = None,
) -> CleanupResult:
    """Remove deprecated agents that have exceeded the retention period.

    Checks each deprecated agent's ``deprecated_at`` timestamp (if set
    in frontmatter). Agents without a timestamp are skipped — they need
    to age before cleanup.

    Args:
        catalog: The agent catalog to clean up.
        retention_seconds: How long to retain deprecated agents (default 30 days).
        current_time: Current timestamp (defaults to time.time()). Useful
            for testing.

    Returns:
        CleanupResult with details of removed agents.
    """
    now = current_time if current_time is not None else time.time()
    retention_days = retention_seconds // (24 * 60 * 60)

    deprecated = [a for a in catalog.agents if a.deprecated]
    removed_names: list[str] = []

    for agent in deprecated:
        deprecated_at = _get_deprecated_timestamp(agent)
        if deprecated_at is None:
            continue

        age = now - deprecated_at
        if age >= retention_seconds:
            source = agent.source_path
            if source is not None and source.exists():
                source.unlink()
                logger.info(
                    "agent_cleaned_up",
                    name=agent.name,
                    age_days=round(age / 86400, 1),
                    path=str(source),
                )

            catalog.remove(agent.name)
            removed_names.append(agent.name)

    return CleanupResult(
        agents_checked=len(deprecated),
        agents_removed=len(removed_names),
        removed_names=removed_names,
        retention_days=retention_days,
    )


def _get_deprecated_timestamp(agent: AgentConfig) -> float | None:
    """Read the deprecated_at timestamp from an agent's source file."""
    if agent.source_path is None or not agent.source_path.exists():
        return None

    try:
        content = agent.source_path.read_text(encoding="utf-8")
    except OSError:
        return None

    from docs_mcp.agents.catalog import _parse_frontmatter

    data = _parse_frontmatter(content)
    ts = data.get(DEPRECATED_AT_KEY)
    if isinstance(ts, int | float):
        return float(ts)
    return None


def _update_frontmatter_deprecated(path: Path, *, deprecated: bool) -> None:
    """Update the deprecated flag and timestamp in AGENT.md frontmatter."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return

    from docs_mcp.agents.catalog import _parse_frontmatter

    data = _parse_frontmatter(content)
    data["deprecated"] = deprecated
    if deprecated:
        data[DEPRECATED_AT_KEY] = int(time.time())
    elif DEPRECATED_AT_KEY in data:
        del data[DEPRECATED_AT_KEY]

    # Rebuild frontmatter
    frontmatter = yaml.dump(data, default_flow_style=False, sort_keys=False).strip()

    # Find and replace existing frontmatter
    lines = content.split("\n")
    if lines and lines[0].strip() == "---":
        end_idx = -1
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end_idx = i
                break
        if end_idx > 0:
            body = "\n".join(lines[end_idx + 1 :])
            new_content = f"---\n{frontmatter}\n---{body}"
            path.write_text(new_content, encoding="utf-8")

"""Agent catalog loader for DocsMCP.

Reads AGENT.md files from a directory and parses YAML frontmatter into
AgentConfig instances.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
import yaml

from docs_mcp.agents.models import AgentConfig

logger: Any = structlog.get_logger(__name__)


def _parse_frontmatter(content: str) -> dict[str, Any]:
    """Extract YAML frontmatter from markdown content.

    Frontmatter is delimited by ``---`` markers at the start of the file.
    Returns an empty dict if no valid frontmatter is found.
    """
    content = content.strip()
    if not content.startswith("---"):
        return {}

    # Find closing delimiter
    end_idx = content.index("---", 3) if "---" in content[3:] else -1
    if end_idx == -1:
        return {}

    # +3 to skip past the opening ---
    frontmatter_text = content[3:end_idx + 3]
    # Find the actual end of the opening --- line
    first_newline = content.index("\n", 0)
    closing_marker = content.find("---", first_newline + 1)
    if closing_marker == -1:
        return {}

    frontmatter_text = content[first_newline + 1 : closing_marker].strip()
    if not frontmatter_text:
        return {}

    try:
        parsed = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError:
        return {}

    return parsed if isinstance(parsed, dict) else {}


def load_agent_config(path: Path) -> AgentConfig | None:
    """Load a single AgentConfig from an AGENT.md file.

    Returns None if the file cannot be parsed or lacks a ``name`` field.
    """
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        logger.warning("agent_file_read_error", path=str(path))
        return None

    data = _parse_frontmatter(content)
    if not data:
        logger.debug("agent_no_frontmatter", path=str(path))
        return None

    # Filter to known fields only
    filtered = {k: v for k, v in data.items() if k in AgentConfig.FRONTMATTER_FIELDS}

    if "name" not in filtered:
        logger.debug("agent_missing_name", path=str(path))
        return None

    filtered["source_path"] = path

    try:
        return AgentConfig(**filtered)
    except Exception:
        logger.warning("agent_parse_error", path=str(path), exc_info=True)
        return None


class AgentCatalog:
    """Manages a collection of agent configurations.

    Loads agents from a directory of AGENT.md files and provides
    lookup and filtering operations.
    """

    def __init__(self, agents: list[AgentConfig] | None = None) -> None:
        self._agents: list[AgentConfig] = agents or []

    @classmethod
    def from_directory(cls, directory: Path) -> AgentCatalog:
        """Load all AGENT.md files from a directory.

        Scans for files matching ``*AGENT*.md`` (case-insensitive glob).
        Skips deprecated agents for matching but retains them in the catalog.
        """
        agents: list[AgentConfig] = []
        if not directory.is_dir():
            logger.warning("agent_dir_not_found", path=str(directory))
            return cls(agents)

        for md_file in sorted(directory.glob("*.md")):
            config = load_agent_config(md_file)
            if config is not None:
                agents.append(config)
                logger.debug("agent_loaded", name=config.name, path=str(md_file))

        logger.info("agent_catalog_loaded", count=len(agents))
        return cls(agents)

    @property
    def agents(self) -> list[AgentConfig]:
        """All agents in the catalog (including deprecated)."""
        return list(self._agents)

    @property
    def active_agents(self) -> list[AgentConfig]:
        """Non-deprecated agents available for matching."""
        return [a for a in self._agents if not a.deprecated]

    def get(self, name: str) -> AgentConfig | None:
        """Look up an agent by name."""
        for agent in self._agents:
            if agent.name == name:
                return agent
        return None

    def add(self, agent: AgentConfig) -> None:
        """Add an agent to the catalog."""
        self._agents.append(agent)

    def remove(self, name: str) -> bool:
        """Remove an agent by name. Returns True if found and removed."""
        for i, agent in enumerate(self._agents):
            if agent.name == name:
                self._agents.pop(i)
                return True
        return False

    def __len__(self) -> int:
        return len(self._agents)

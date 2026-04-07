"""Agent configuration models for DocsMCP."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, Field


class MemoryProfile(StrEnum):
    """Controls how an agent interacts with tapps-brain memory.

    - full: recall shared knowledge and save learnings after execution
    - readonly: recall shared knowledge but do not save
    - none: no memory interaction (useful for test/scratch agents)
    """

    FULL = "full"
    READONLY = "readonly"
    NONE = "none"


class AgentConfig(BaseModel):
    """Configuration for a single agent in the catalog.

    Parsed from AGENT.md frontmatter (YAML between ``---`` markers) or
    constructed programmatically.
    """

    FRONTMATTER_FIELDS: ClassVar[set[str]] = {
        "name",
        "description",
        "keywords",
        "capabilities",
        "memory_profile",
        "deprecated",
        "system_prompt_path",
    }

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Unique agent identifier.",
    )
    description: str = Field(
        default="",
        max_length=500,
        description="Human-readable description of what this agent does.",
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="Keywords for keyword-based matching.",
    )
    capabilities: list[str] = Field(
        default_factory=list,
        description="Structured capability identifiers.",
    )
    system_prompt_path: Path | None = Field(
        default=None,
        description="Path to the agent's system prompt file.",
    )
    memory_profile: MemoryProfile = Field(
        default=MemoryProfile.FULL,
        description="Controls memory recall/save behavior.",
    )
    deprecated: bool = Field(
        default=False,
        description="Deprecated agents are excluded from matching.",
    )
    source_path: Path | None = Field(
        default=None,
        description="Path to the AGENT.md file this config was loaded from.",
    )

    def embedding_text(self) -> str:
        """Return concatenated text used for embedding computation.

        Combines name, description, keywords, and capabilities into a single
        string for richer embedding representation.
        """
        parts = [self.name, self.description]
        parts.extend(self.keywords)
        parts.extend(self.capabilities)
        return " ".join(p for p in parts if p)

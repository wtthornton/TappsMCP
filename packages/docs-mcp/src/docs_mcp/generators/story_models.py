"""Story generation models and link helpers.

``StoryTask`` / ``StoryConfig`` and the relative-link helper, split out
of ``stories.py`` under TAP-5609. ``stories.py`` re-exports all three,
so existing imports keep resolving.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel


def markdown_relative_link(target: str, from_file: str) -> str:
    """Return ``target`` as a path relative to ``from_file``'s directory.

    Used so epic links in generated story files resolve correctly when the
    story lives in a subdirectory (e.g. ``EPIC-80/story-80.1.md`` → ``../EPIC.md``).
    """
    t = target.strip()
    f = from_file.strip()
    if not t or not f:
        return target
    if t.startswith(("http://", "https://", "mailto:")):
        return t
    try:
        return os.path.relpath(t, Path(f).parent).replace("\\", "/")
    except ValueError:
        return t.replace("\\", "/")


class StoryTask(BaseModel):
    """A single implementation task within a story."""

    description: str
    file_path: str = ""


class StoryConfig(BaseModel):
    """Configuration for user story generation."""

    title: str
    epic_number: int = 0
    story_number: int = 0
    purpose_and_intent: str = ""  # Required per design doc §2 (Epic 75.3)
    role: str = ""
    want: str = ""
    so_that: str = ""
    description: str = ""
    points: int = 0
    size: str = ""  # "S", "M", "L", "XL"
    tasks: list[StoryTask] = []
    acceptance_criteria: list[str] = []
    # TAP-5541: optional behavioral assertion IDs for agent stories.
    assertions: list[str] = []
    test_cases: list[str] = []
    dependencies: list[str] = []
    files: list[str] = []
    technical_notes: list[str] = []
    criteria_format: str = "checkbox"  # "checkbox" or "gherkin"
    style: str = "standard"  # "standard" or "comprehensive"
    inherit_context: bool = True
    epic_path: str = ""
    # STORY-104.1: default audience is "agent" — emits the 5-section Linear
    # template from docs/linear/AGENT_ISSUES.md. Pass "human" for the
    # full product-review shape.
    audience: str = "agent"  # "agent" | "human"

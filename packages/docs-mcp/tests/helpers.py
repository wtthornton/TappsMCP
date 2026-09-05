"""Shared test helpers for docs-mcp.

Centralises commonly duplicated utilities so individual test files can import
them instead of re-defining identical copies.

Usage::

    from tests.helpers import run_async, make_settings, make_commit, make_version, make_story_config
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from docs_mcp.analyzers.git_history import CommitInfo
from docs_mcp.analyzers.version_detector import VersionBoundary
from docs_mcp.generators.stories import StoryConfig, StoryTask


def run_async(coro: Any) -> Any:
    """Run an async coroutine synchronously for testing.

    Creates a fresh event loop per call to avoid cross-test contamination.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def make_settings(root: Path, **overrides: Any) -> MagicMock:
    """Create a mock ``DocsMCPSettings`` pointing to *root*.

    Sets all commonly-expected attributes.  Any keyword argument is forwarded
    as an attribute override (e.g. ``make_settings(root, diagram_format="d2")``).
    """
    settings = MagicMock()
    settings.project_root = root
    settings.output_dir = "docs"
    settings.default_style = "standard"
    settings.default_format = "markdown"
    settings.include_toc = True
    settings.include_badges = True
    settings.changelog_format = "keep-a-changelog"
    settings.adr_format = "madr"
    settings.diagram_format = "mermaid"
    settings.git_log_limit = 100
    settings.log_level = "INFO"
    settings.log_json = False
    settings.style_enabled_rules = [
        "passive_voice",
        "jargon",
        "sentence_length",
        "heading_consistency",
        "tense_consistency",
    ]
    settings.style_heading = "sentence"
    settings.style_max_sentence_words = 40
    settings.style_custom_terms = []
    settings.style_jargon_terms = []
    settings.style_include_in_project_scan = True
    settings.style_auto_detect_terms = False
    settings.style_auto_detect_max_files = 120
    settings.style_auto_detect_max_terms = 80
    for key, value in overrides.items():
        setattr(settings, key, value)
    return settings


def make_commit(
    message: str,
    *,
    hash: str = "abc1234567890",
    short_hash: str = "abc1234",
    author: str = "Test Author",
    author_email: str = "test@example.com",
    date: str = "2026-02-15T10:00:00+00:00",
) -> CommitInfo:
    """Create a test ``CommitInfo`` with sensible defaults."""
    return CommitInfo(
        hash=hash,
        short_hash=short_hash,
        author=author,
        author_email=author_email,
        date=date,
        message=message,
    )


def make_version(
    version: str,
    date: str,
    commits: list[CommitInfo] | None = None,
) -> VersionBoundary:
    """Create a test ``VersionBoundary`` with sensible defaults."""
    return VersionBoundary(
        version=version,
        tag=f"v{version}",
        date=date,
        commit_count=len(commits) if commits else 0,
        commits=commits or [],
    )


def make_story_config(**kwargs: Any) -> StoryConfig:
    """Build a ``StoryConfig`` with sensible defaults.

    TAP-5622: moved here from ``test_stories.py`` when that megafile was
    split by concern, so both halves (and any future story test file) share
    one definition instead of duplicating it.
    """
    defaults: dict[str, Any] = {
        "title": "Test Story",
        "epic_number": 23,
        "story_number": 1,
        "role": "developer",
        "want": "to validate login credentials",
        "so_that": "invalid logins are rejected",
        "description": "Implement client-side validation for the login form.",
        "points": 3,
        "size": "M",
        "tasks": [
            StoryTask(description="Create validation module", file_path="src/validators.py"),
            StoryTask(description="Write unit tests"),
        ],
        "acceptance_criteria": ["Validation rejects empty fields", "Error messages displayed"],
        "test_cases": ["Test empty email", "Test invalid password format"],
        "dependencies": ["Story 23.0"],
        "files": ["src/validators.py", "tests/test_validators.py"],
        "technical_notes": ["Use Pydantic for validation"],
        "criteria_format": "checkbox",
        "style": "standard",
        # STORY-104.1: existing tests were written against the human-shape
        # output. The default flipped to "agent" but these tests still
        # assert on the rich product-review sections -- keep them pointed
        # at the human renderer. Agent-audience tests live in
        # TestAgentAudience (test_stories_audience.py).
        "audience": "human",
    }
    defaults.update(kwargs)
    return StoryConfig(**defaults)

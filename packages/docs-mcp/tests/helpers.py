"""Shared test helpers for docs-mcp.

Centralises commonly duplicated utilities so individual test files can import
them instead of re-defining identical copies.

Usage::

    from tests.helpers import run_async, make_settings, make_commit, make_version
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from docs_mcp.analyzers.git_history import CommitInfo
from docs_mcp.analyzers.version_detector import VersionBoundary


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

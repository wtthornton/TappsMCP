"""Shared utility functions to eliminate cross-module duplication."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "env",
        "ENV",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        "dist",
        "build",
        ".tox",
        ".eggs",
        "htmlcov",
        ".mypy_cache",
        ".tapps-agents",
        ".tapps-mcp-cache",
        "site-packages",
    }
)


def should_skip_path(path: Path) -> bool:
    """Return True if any component of *path* is in SKIP_DIRS or matches a skip prefix."""
    return any(
        part in SKIP_DIRS or part.startswith(".venv")
        for part in path.parts
    )


def utc_now() -> datetime:
    """Return the current UTC datetime (timezone-aware)."""
    return datetime.now(tz=UTC)


def ensure_dir(path: Path) -> Path:
    """Create directory (and parents) if it does not exist. Returns the path."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_text_utf8(path: Path) -> str:
    """Read a file as UTF-8 text."""
    return path.read_text(encoding="utf-8")

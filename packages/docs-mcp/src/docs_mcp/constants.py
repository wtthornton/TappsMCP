"""Shared constants for the docs_mcp package."""

from __future__ import annotations

# Directories to skip when recursively scanning for source files.
# Used by analyzers, generators, and validators.
SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "node_modules",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".eggs",
        "site-packages",
    }
)

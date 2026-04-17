"""Shared test fixtures for docs-mcp.

Ensures test isolation by resetting module-level caches between tests.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

# Preload ``docs_mcp.server`` so that tests which import submodules first
# (e.g. ``from docs_mcp.server_gen_tools import ...``) don't trigger a
# circular-import failure. ``server.py`` calls ``_register_tool_modules()``
# during its own import, which re-imports each submodule; if a submodule
# is mid-init it returns a partial module and ``.register`` is undefined.
# Importing ``docs_mcp.server`` at conftest load time guarantees the full
# registration completes before any test-order variation can wedge it.
import docs_mcp.server  # noqa: F401


@pytest.fixture(autouse=True)
def _reset_caches() -> Generator[None, None, None]:
    """Reset all module-level singletons after each test.

    Caches populate normally during each test and are cleared in teardown,
    ensuring test isolation when caching is active in:

    - ``load_docs_settings()`` (config/settings.py)
    - ``_get_settings()`` (server_helpers.py)
    """
    yield

    from docs_mcp.config.settings import _reset_docs_settings_cache
    from docs_mcp.server import _reset_tool_calls
    from docs_mcp.server_helpers import _reset_settings_cache

    _reset_docs_settings_cache()
    _reset_settings_cache()
    _reset_tool_calls()


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    """Create a minimal project directory for testing.

    Uses a subdirectory of tmp_path to avoid conflicts with docs_project.
    Includes pyproject.toml, .git directory, README.md, and a sample source file.
    """
    root = tmp_path / "minimal"
    root.mkdir()
    (root / ".git").mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\nname = "test-project"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        "# Test Project\n\nA test project.\n",
        encoding="utf-8",
    )
    src_dir = root / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text(
        '"""Main module."""\n\ndef main() -> None:\n    pass\n',
        encoding="utf-8",
    )
    return root


@pytest.fixture
def docs_project(tmp_path: Path) -> Path:
    """Create a project directory with rich documentation for testing.

    Uses a subdirectory of tmp_path to avoid conflicts with sample_project.
    Includes README, CHANGELOG, CONTRIBUTING, LICENSE, and a docs/ directory
    with API and guide documentation.
    """
    root = tmp_path / "documented"
    root.mkdir()
    (root / ".git").mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\nname = "docs-test-project"\nversion = "2.0.0"\n',
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        "# Docs Test Project\n\nA well-documented project.\n",
        encoding="utf-8",
    )
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [2.0.0] - 2026-01-01\n\n- Initial release\n",
        encoding="utf-8",
    )
    (root / "CONTRIBUTING.md").write_text(
        "# Contributing\n\nSee guidelines below.\n",
        encoding="utf-8",
    )
    (root / "LICENSE").write_text(
        "MIT License\n\nCopyright (c) 2026\n",
        encoding="utf-8",
    )

    docs_dir = root / "docs"
    docs_dir.mkdir()
    (docs_dir / "api.md").write_text(
        "# API Reference\n\n## Functions\n",
        encoding="utf-8",
    )
    (docs_dir / "guide.md").write_text(
        "# User Guide\n\n## Getting Started\n",
        encoding="utf-8",
    )

    src_dir = root / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text(
        '"""App module."""\n\ndef run() -> None:\n    pass\n',
        encoding="utf-8",
    )
    return root

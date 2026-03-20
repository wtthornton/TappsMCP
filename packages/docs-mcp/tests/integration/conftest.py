"""Integration test fixtures for docs-mcp.

Provides heavier fixtures (real project trees with documentation) that are
too expensive for unit tests but needed for generator-validator flow tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def documented_project(tmp_path: Path) -> Path:
    """Create a project with source code and documentation for integration tests.

    More complete than unit test fixtures: includes multiple source files,
    a docs directory, git stub, and various config files that documentation
    tools need to produce realistic output.
    """
    root = tmp_path / "integration_docs"
    root.mkdir()
    (root / ".git").mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\nname = "docs-integration"\nversion = "2.0.0"\n'
        'description = "Integration test project"\n'
        'requires-python = ">=3.12"\n',
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        "# Docs Integration\n\nA project for integration testing.\n",
        encoding="utf-8",
    )
    (root / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [2.0.0] - 2026-01-15\n\n- Initial release\n",
        encoding="utf-8",
    )

    src = root / "src" / "myapp"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text('"""Application package."""\n', encoding="utf-8")
    (src / "api.py").write_text(
        '"""Public API module."""\n\nfrom __future__ import annotations\n\n\n'
        "def fetch(url: str, timeout: int = 30) -> str:\n"
        '    """Fetch content from a URL."""\n'
        '    return ""\n\n\n'
        "class Client:\n"
        '    """HTTP client."""\n\n'
        "    def __init__(self, base_url: str) -> None:\n"
        "        self.base_url = base_url\n",
        encoding="utf-8",
    )

    docs = root / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text(
        "# User Guide\n\n## Getting Started\n\nInstall with pip.\n",
        encoding="utf-8",
    )
    return root

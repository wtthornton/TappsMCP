"""Integration test fixtures for tapps-mcp.

Provides heavier fixtures (real project trees, temp config files) that are
too expensive for unit tests but needed for pipeline integration validation.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def scored_project(tmp_path: Path) -> Path:
    """Create a Python project with scoreable source files.

    Suitable for end-to-end scoring, quality gate, and security pipeline tests.
    """
    root = tmp_path / "scored_project"
    root.mkdir()
    (root / ".git").mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\nname = "scored-project"\nversion = "1.0.0"\n'
        'requires-python = ">=3.12"\n\n'
        "[tool.ruff]\nline-length = 100\n",
        encoding="utf-8",
    )
    src = root / "src" / "mylib"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text('"""Library package."""\n', encoding="utf-8")
    (src / "main.py").write_text(
        '"""Main module with type hints."""\n\nfrom __future__ import annotations\n\n\n'
        "def greet(name: str) -> str:\n"
        '    """Return a greeting."""\n'
        '    return f"Hello, {name}!"\n',
        encoding="utf-8",
    )
    tests_dir = root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_main.py").write_text(
        "from mylib.main import greet\n\n\ndef test_greet() -> None:\n"
        '    assert greet("World") == "Hello, World!"\n',
        encoding="utf-8",
    )
    return root

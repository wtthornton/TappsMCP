"""Integration test fixtures for tapps-core.

Provides heavier fixtures (real file trees, git repos) that are too
expensive for unit tests but needed for cross-module wiring validation.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def real_project(tmp_path: Path) -> Path:
    """Create a realistic Python project tree for integration tests.

    Includes pyproject.toml, src layout, tests directory, and a .git stub
    so that project-detection heuristics work correctly.
    """
    root = tmp_path / "integration_project"
    root.mkdir()
    (root / ".git").mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\nname = "integration-test"\nversion = "0.1.0"\n'
        'requires-python = ">=3.12"\n',
        encoding="utf-8",
    )
    src = root / "src" / "mypackage"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text('"""Package."""\n', encoding="utf-8")
    (src / "core.py").write_text(
        '"""Core module."""\n\n\ndef compute(x: int) -> int:\n    return x * 2\n',
        encoding="utf-8",
    )
    tests_dir = root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_core.py").write_text(
        "from mypackage.core import compute\n\ndef test_compute():\n"
        "    assert compute(2) == 4\n",
        encoding="utf-8",
    )
    return root

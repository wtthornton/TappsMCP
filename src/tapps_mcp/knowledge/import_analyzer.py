"""Analyze Python file imports to detect uncached external libraries.

Used by ``tapps_score_file`` to nudge the LLM toward calling
``tapps_lookup_docs`` for libraries whose docs are not yet cached.
"""

from __future__ import annotations

import ast
import sys
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from pathlib import Path

    from tapps_mcp.knowledge.cache import KBCache

logger = structlog.get_logger(__name__)

# Python stdlib top-level module names (available since 3.10)
_STDLIB_MODULES: frozenset[str] = frozenset(sys.stdlib_module_names)

# Common test/tool packages that aren't worth looking up docs for
_SKIP_MODULES: frozenset[str] = frozenset({
    "pytest", "unittest", "mock", "setuptools", "pip", "wheel",
    "mypy", "ruff", "bandit", "radon", "pylint", "flake8",
    "_pytest", "conftest",
})


def extract_external_imports(
    file_path: Path,
    project_root: Path,
) -> list[str]:
    """Parse file AST and return sorted external import names.

    Filters out:
    - stdlib modules (via ``sys.stdlib_module_names``)
    - local project imports (detected via src/ layout)
    - private modules (starting with ``_``)
    - common test/tool packages

    Args:
        file_path: Path to the Python file to analyze.
        project_root: Project root for detecting local packages.

    Returns:
        Sorted list of external top-level module names.
    """
    try:
        code = file_path.read_text(encoding="utf-8")
        tree = ast.parse(code)
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []

    top_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_modules.add(node.module.split(".")[0])

    project_package = _detect_project_package(project_root)

    external: list[str] = []
    for mod in sorted(top_modules):
        if mod in _STDLIB_MODULES:
            continue
        if mod in _SKIP_MODULES:
            continue
        if project_package and mod == project_package:
            continue
        if mod.startswith("_"):
            continue
        external.append(mod)

    return external


def find_uncached_libraries(
    external_imports: list[str],
    cache: KBCache,
) -> list[str]:
    """Check which external imports are not in the docs cache.

    Args:
        external_imports: List of external module names.
        cache: The knowledge base cache to check against.

    Returns:
        List of module names with no cached documentation.
    """
    uncached: list[str] = []
    for lib in external_imports:
        if not cache.has(lib):
            uncached.append(lib)
    return uncached


def _detect_project_package(project_root: Path) -> str | None:
    """Detect the project's own package name from directory layout.

    Checks ``src/`` layout first (PEP 517), then flat layout.
    """
    src_dir = project_root / "src"
    if src_dir.exists():
        for d in src_dir.iterdir():
            if d.is_dir() and (d / "__init__.py").exists():
                return d.name

    skip = {"venv", ".venv", "tests", "docs", "scripts", "build", "dist", "node_modules"}
    for d in project_root.iterdir():
        if (
            d.is_dir()
            and d.name not in skip
            and not d.name.startswith(".")
            and (d / "__init__.py").exists()
        ):
            return d.name
    return None

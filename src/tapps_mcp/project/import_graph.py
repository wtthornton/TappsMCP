"""Build a Python import graph from AST analysis.

Walks all ``.py`` files under a project root, extracts intra-project
import edges, and classifies them as runtime, type-checking, or
conditional (try/except ImportError).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from pathlib import Path

logger = structlog.get_logger(__name__)

# Directories to skip during recursive file discovery.
_DEFAULT_EXCLUDES: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        "dist",
        "build",
        ".tox",
        ".eggs",
        "htmlcov",
        ".mypy_cache",
        "migrations",
        "site-packages",
    }
)


@dataclass
class ImportEdge:
    """A single import relationship between two project modules."""

    source_module: str  # e.g. "tapps_mcp.tools.ruff"
    target_module: str  # e.g. "tapps_mcp.scoring.models"
    import_type: str = "runtime"  # runtime / type_checking / conditional
    line_number: int = 0
    import_name: str = ""  # what was imported (function/class name)


@dataclass
class ImportGraph:
    """Directed graph of intra-project import relationships."""

    edges: list[ImportEdge] = field(default_factory=list)
    modules: set[str] = field(default_factory=set)
    project_root: str = ""

    def get_dependencies(self, module: str) -> list[str]:
        """Get modules that *module* depends on (efferent coupling)."""
        return [e.target_module for e in self.edges if e.source_module == module]

    def get_dependents(self, module: str) -> list[str]:
        """Get modules that depend on *module* (afferent coupling)."""
        return [e.source_module for e in self.edges if e.target_module == module]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_import_graph(
    project_root: Path,
    *,
    exclude_patterns: list[str] | None = None,
    top_level_package: str = "",
) -> ImportGraph:
    """Walk all ``.py`` files and build an import graph.

    Only tracks **intra-project** imports (ignores stdlib and third-party).

    Args:
        project_root: Root directory to scan.
        exclude_patterns: Additional directory names to skip.
        top_level_package: Top-level package name used to resolve module
            names.  When empty the first ``__init__.py`` parent is used.
    """
    excludes = set(_DEFAULT_EXCLUDES)
    if exclude_patterns:
        excludes.update(exclude_patterns)

    # Phase 1 -- discover all project modules
    project_modules: set[str] = set()
    file_module_map: dict[Path, str] = {}

    for py_file in project_root.rglob("*.py"):
        if _should_skip(py_file, excludes):
            continue
        if py_file.name.endswith("_pb2.py"):
            continue
        mod = _file_to_module(py_file, project_root, top_level_package)
        if mod:
            project_modules.add(mod)
            file_module_map[py_file] = mod

    # Phase 2 -- extract import edges
    all_edges: list[ImportEdge] = []
    for py_file, source_module in file_module_map.items():
        edges = _extract_imports(py_file, source_module, project_modules, top_level_package)
        all_edges.extend(edges)

    graph = ImportGraph(
        edges=all_edges,
        modules=project_modules,
        project_root=str(project_root),
    )

    logger.info(
        "import_graph_built",
        modules=len(project_modules),
        edges=len(all_edges),
    )
    return graph


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _should_skip(path: Path, excludes: set[str]) -> bool:
    """Return True if any path component is in *excludes*."""
    return any(part in excludes for part in path.parts)


def _file_to_module(file_path: Path, project_root: Path, top_level: str) -> str:
    """Convert a file path to a dotted module name.

    Handles ``__init__.py`` -> package name and optional ``src/`` layout.
    """
    try:
        rel = file_path.relative_to(project_root)
    except ValueError:
        return ""

    parts = list(rel.with_suffix("").parts)
    if not parts:
        return ""

    # Strip leading "src" directory if present and top_level is specified
    if parts and parts[0] == "src" and top_level:
        parts = parts[1:]

    # __init__.py maps to its parent package
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]

    if not parts:
        return ""

    return ".".join(parts)


def _extract_imports(
    file_path: Path,
    source_module: str,
    project_modules: set[str],
    top_level: str,
) -> list[ImportEdge]:
    """Extract import edges from a single Python file using AST."""
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []

    edges: list[ImportEdge] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = alias.name
                if not _is_project_module(target, project_modules):
                    continue
                import_type = _classify_import(node, tree)
                edges.append(
                    ImportEdge(
                        source_module=source_module,
                        target_module=_resolve_target(target, project_modules),
                        import_type=import_type,
                        line_number=node.lineno,
                        import_name=alias.asname or alias.name,
                    )
                )

        elif isinstance(node, ast.ImportFrom):
            base_module = node.module or ""

            # Resolve relative imports
            if node.level and node.level > 0:
                base_module = _resolve_relative_import(source_module, base_module, node.level)

            if not base_module:
                continue

            # Check the base module first
            if _is_project_module(base_module, project_modules):
                import_type = _classify_import(node, tree)
                for alias in node.names:
                    import_name = alias.name
                    # Check if "base_module.name" is a more precise module
                    full_target = f"{base_module}.{import_name}"
                    resolved = (
                        _resolve_target(full_target, project_modules)
                        if _is_project_module(full_target, project_modules)
                        else _resolve_target(base_module, project_modules)
                    )
                    edges.append(
                        ImportEdge(
                            source_module=source_module,
                            target_module=resolved,
                            import_type=import_type,
                            line_number=node.lineno,
                            import_name=import_name,
                        )
                    )

    return edges


def _is_project_module(name: str, project_modules: set[str]) -> bool:
    """Check if *name* is or is a child of any project module."""
    if name in project_modules:
        return True
    # Check if it's a sub-path of a known module
    return any(name.startswith(m + ".") or m.startswith(name + ".") for m in project_modules)


def _resolve_target(target: str, project_modules: set[str]) -> str:
    """Resolve *target* to the best matching project module."""
    if target in project_modules:
        return target
    # Find the longest prefix that matches a known module
    best = ""
    for mod in project_modules:
        if target.startswith(mod + ".") or target == mod:
            if len(mod) > len(best):
                best = mod
        elif mod.startswith(target + ".") and len(target) > len(best):
            best = target
    return best or target


def _resolve_relative_import(source_module: str, module: str, level: int) -> str:
    """Resolve a relative import to an absolute module path.

    Args:
        source_module: The module containing the import statement.
        module: The module part of the import (may be empty for ``from . import``).
        level: Number of leading dots (1 = current package, 2 = parent, ...).
    """
    parts = source_module.split(".")
    # Go up *level* directories from the source module's package
    if level >= len(parts):
        return module
    package_parts = parts[: len(parts) - level]
    if module:
        return ".".join([*package_parts, module])
    return ".".join(package_parts)


def _classify_import(node: ast.AST, tree: ast.Module) -> str:
    """Determine if an import is runtime, type_checking, or conditional."""
    if _is_in_type_checking_block(node, tree):
        return "type_checking"
    if _is_in_try_except_import(node, tree):
        return "conditional"
    return "runtime"


def _is_in_type_checking_block(node: ast.AST, tree: ast.Module) -> bool:
    """Check if an import node is inside an ``if TYPE_CHECKING:`` block."""
    for top_node in ast.walk(tree):
        if not isinstance(top_node, ast.If):
            continue
        # Check for `if TYPE_CHECKING:` pattern
        test = top_node.test
        is_type_checking = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
            isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
        )

        if is_type_checking:
            for child in ast.walk(top_node):
                if child is node:
                    return True
    return False


def _is_in_try_except_import(node: ast.AST, tree: ast.Module) -> bool:
    """Check if an import is inside a ``try/except ImportError`` block."""
    for top_node in ast.walk(tree):
        if not isinstance(top_node, ast.Try):
            continue
        # Check if any handler catches ImportError
        has_import_error = any(
            handler.type is not None
            and isinstance(handler.type, ast.Name)
            and handler.type.id == "ImportError"
            for handler in top_node.handlers
        )
        if not has_import_error:
            continue
        # Check if our node is inside this try block
        for child in ast.walk(top_node):
            if child is node:
                return True
    return False

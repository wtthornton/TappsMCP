"""Build a Python import graph from AST analysis.

Walks ``.py`` files under a project root, extracts intra-project import
edges, and classifies them as runtime, type-checking, or conditional.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from pathlib import Path

logger = structlog.get_logger(__name__)

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

    source_module: str
    target_module: str
    import_type: str = "runtime"
    line_number: int = 0
    import_name: str = ""


@dataclass
class ImportGraph:
    """Directed graph of intra-project import relationships."""

    edges: list[ImportEdge] = field(default_factory=list)
    modules: set[str] = field(default_factory=set)
    project_root: str = ""
    external_imports: dict[str, set[str]] = field(default_factory=dict)

    def get_dependencies(self, module: str) -> list[str]:
        """Modules that *module* depends on (efferent coupling)."""
        return [e.target_module for e in self.edges if e.source_module == module]

    def get_dependents(self, module: str) -> list[str]:
        """Modules that depend on *module* (afferent coupling)."""
        return [e.source_module for e in self.edges if e.target_module == module]


def build_import_graph(
    project_root: Path,
    *,
    exclude_patterns: list[str] | None = None,
    top_level_package: str = "",
) -> ImportGraph:
    """Walk ``.py`` files and build an import graph."""
    excludes = set(_DEFAULT_EXCLUDES)
    if exclude_patterns:
        excludes.update(exclude_patterns)

    project_modules: set[str] = set()
    file_module_map: dict[Path, str] = {}
    for py_file in project_root.rglob("*.py"):
        if _should_skip(py_file, excludes) or py_file.name.endswith("_pb2.py"):
            continue
        mod = _file_to_module(py_file, project_root, top_level_package)
        if mod:
            project_modules.add(mod)
            file_module_map[py_file] = mod

    all_edges: list[ImportEdge] = []
    all_external: dict[str, set[str]] = {}
    for py_file, source_module in file_module_map.items():
        edges, externals = _extract_imports(py_file, source_module, project_modules)
        all_edges.extend(edges)
        _merge_externals(all_external, externals, source_module)

    graph = ImportGraph(
        edges=all_edges,
        modules=project_modules,
        project_root=str(project_root),
        external_imports=all_external,
    )
    logger.info(
        "import_graph_built",
        modules=len(project_modules),
        edges=len(all_edges),
        external_packages=len(all_external),
    )
    return graph


def _should_skip(path: Path, excludes: set[str]) -> bool:
    return any(part in excludes for part in path.parts)


def _file_to_module(
    file_path: Path,
    project_root: Path,
    top_level: str,
) -> str:
    """Convert a file path to a dotted module name."""
    try:
        rel = file_path.relative_to(project_root)
    except ValueError:
        return ""
    parts = list(rel.with_suffix("").parts)
    if not parts:
        return ""
    if parts[0] == "src" and top_level:
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else ""


def _build_context_map(tree: ast.Module) -> dict[int, str]:
    """Build node-id -> classification map in a single pass."""
    ctx: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_tc_guard(node.test):
            ctx.update(dict.fromkeys(map(id, ast.walk(node)), "type_checking"))
        elif isinstance(node, ast.Try) and _has_import_error_handler(node):
            ctx.update(dict.fromkeys(map(id, ast.walk(node)), "conditional"))
    return ctx


def _is_tc_guard(test: ast.expr) -> bool:
    """Check if a test expression is ``TYPE_CHECKING``."""
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _has_import_error_handler(node: ast.Try) -> bool:
    """Check if a try node catches ImportError."""
    return any(
        h.type is not None and isinstance(h.type, ast.Name) and h.type.id == "ImportError"
        for h in node.handlers
    )


def _extract_imports(
    file_path: Path,
    source_module: str,
    project_modules: set[str],
) -> tuple[list[ImportEdge], set[str]]:
    """Extract import edges and external package names from a Python file."""
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return [], set()

    ctx = _build_context_map(tree)
    edges: list[ImportEdge] = []
    external: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            _collect_import(node, ctx, source_module, project_modules, edges, external)
        elif isinstance(node, ast.ImportFrom):
            _collect_from_import(
                node,
                ctx,
                source_module,
                project_modules,
                edges,
                external,
            )
    return edges, external


def _collect_import(
    node: ast.Import,
    ctx: dict[int, str],
    source_module: str,
    project_modules: set[str],
    edges: list[ImportEdge],
    external: set[str],
) -> None:
    """Collect edges from ``import X`` statements."""
    itype = ctx.get(id(node), "runtime")
    for alias in node.names:
        target = alias.name
        if _is_project_module(target, project_modules):
            edges.append(
                ImportEdge(
                    source_module=source_module,
                    target_module=_resolve_target(target, project_modules),
                    import_type=itype,
                    line_number=node.lineno,
                    import_name=alias.asname or alias.name,
                )
            )
        else:
            _add_external(target, external)


def _collect_from_import(
    node: ast.ImportFrom,
    ctx: dict[int, str],
    source_module: str,
    project_modules: set[str],
    edges: list[ImportEdge],
    external: set[str],
) -> None:
    """Collect edges from ``from X import Y`` statements."""
    base = _resolve_from_base(node, source_module)
    if not base:
        return
    if not _is_project_module(base, project_modules):
        _add_external(base, external)
        return
    itype = ctx.get(id(node), "runtime")
    for alias in node.names:
        full = f"{base}.{alias.name}"
        resolved = (
            _resolve_target(full, project_modules)
            if _is_project_module(full, project_modules)
            else _resolve_target(base, project_modules)
        )
        edges.append(
            ImportEdge(
                source_module=source_module,
                target_module=resolved,
                import_type=itype,
                line_number=node.lineno,
                import_name=alias.name,
            )
        )


def _resolve_from_base(node: ast.ImportFrom, source_module: str) -> str:
    """Resolve the base module of a ``from`` import (handles relative)."""
    base = node.module or ""
    if not node.level or node.level <= 0:
        return base
    parts = source_module.split(".")
    if node.level >= len(parts):
        return base
    pkg = parts[: len(parts) - node.level]
    return ".".join([*pkg, base]) if base else ".".join(pkg)


def _merge_externals(
    target: dict[str, set[str]],
    externals: set[str],
    source_module: str,
) -> None:
    """Merge discovered externals into the accumulator."""
    for pkg in externals:
        target.setdefault(pkg, set()).add(source_module)


def _add_external(module_name: str, external: set[str]) -> None:
    """Add top-level package to externals if not stdlib."""
    pkg = module_name.split(".", maxsplit=1)[0] if module_name else ""
    if pkg and pkg not in sys.stdlib_module_names:
        external.add(pkg)


def _is_project_module(name: str, project_modules: set[str]) -> bool:
    """Check if *name* is or is a child of any project module."""
    if name in project_modules:
        return True
    return any(name.startswith(m + ".") or m.startswith(name + ".") for m in project_modules)


def _resolve_target(target: str, project_modules: set[str]) -> str:
    """Resolve *target* to the best matching project module."""
    if target in project_modules:
        return target
    # Find longest module that is a prefix of target
    prefixes = [m for m in project_modules if target.startswith(m + ".") or target == m]
    if prefixes:
        return max(prefixes, key=len)
    return target

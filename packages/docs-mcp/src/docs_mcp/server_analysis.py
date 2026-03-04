"""DocsMCP analysis tools — docs_module_map and docs_api_surface.

These tools register on the shared ``mcp`` FastMCP instance from
``server.py`` and provide code structure analysis capabilities.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from docs_mcp.server import _ANNOTATIONS_READ_ONLY, _record_call, mcp
from docs_mcp.server_helpers import _get_settings, error_response, success_response


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY)
async def docs_module_map(
    depth: int = 10,
    include_private: bool = False,
    source_dirs: str = "",
    project_root: str = "",
) -> dict[str, Any]:
    """Build a hierarchical module map of a project.

    Walks the source directory tree and extracts module/package structure,
    public API counts, docstrings, and entry points. Supports Python (.py)
    via AST parsing, plus TypeScript, Go, Rust, and Java via tree-sitter
    when installed.

    Args:
        depth: Maximum directory depth to traverse (default: 10).
        include_private: Whether to include modules starting with ``_``
            (``__init__.py`` is always included).
        source_dirs: Comma-separated source directories relative to project root.
            When empty, auto-detects ``src/`` layout or scans project root.
        project_root: Override project root path (default: configured root).
    """
    _record_call("docs_module_map")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_module_map", "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.analyzers.module_map import ModuleMapAnalyzer

    analyzer = ModuleMapAnalyzer()
    src_list = [s.strip() for s in source_dirs.split(",") if s.strip()] or None
    result = analyzer.analyze(
        root, depth=depth, include_private=include_private,
        source_dirs=src_list,
    )

    # Serialize module tree to dicts
    def _node_to_dict(node: Any) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": node.name,
            "path": node.path,
            "is_package": node.is_package,
            "public_api_count": node.public_api_count,
            "function_count": node.function_count,
            "class_count": node.class_count,
            "size_bytes": node.size_bytes,
        }
        if node.module_docstring:
            d["module_docstring"] = node.module_docstring
        if node.has_main:
            d["has_main"] = True
        if node.all_exports is not None:
            d["all_exports"] = node.all_exports
        if node.submodules:
            d["submodules"] = [_node_to_dict(s) for s in node.submodules]
        return d

    data: dict[str, Any] = {
        "project_root": str(root),
        "project_name": result.project_name,
        "module_tree": [_node_to_dict(n) for n in result.module_tree],
        "entry_points": result.entry_points,
        "total_modules": result.total_modules,
        "total_packages": result.total_packages,
        "public_api_count": result.public_api_count,
    }

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    return success_response("docs_module_map", elapsed_ms, data)


@mcp.tool(annotations=_ANNOTATIONS_READ_ONLY)
async def docs_api_surface(
    source_path: str,
    include_types: bool = True,
    depth: str = "public",
    project_root: str = "",
) -> dict[str, Any]:
    """Analyze the public API surface of a source file.

    Supports Python (.py), TypeScript (.ts/.tsx), Go (.go), Rust (.rs),
    and Java (.java). Identifies public functions, classes, and constants,
    calculates documentation coverage, and reports which public names are
    missing docstrings.

    Args:
        source_path: Path to a source file (absolute or relative to project root).
        include_types: Whether to detect type alias definitions.
        depth: Visibility depth — ``"public"``, ``"protected"``, or ``"all"``.
        project_root: Override project root path (default: configured root).
    """
    _record_call("docs_api_surface")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    file_path = Path(source_path)
    if not file_path.is_absolute():
        file_path = root / file_path

    if not file_path.exists():
        return error_response(
            "docs_api_surface", "FILE_NOT_FOUND",
            f"File does not exist: {file_path}",
        )

    if depth not in ("public", "protected", "all"):
        return error_response(
            "docs_api_surface", "INVALID_DEPTH",
            f"Invalid depth '{depth}'. Must be 'public', 'protected', or 'all'.",
        )

    from docs_mcp.analyzers.api_surface import APISurfaceAnalyzer

    analyzer = APISurfaceAnalyzer()
    surface = analyzer.analyze(
        file_path, project_root=root, depth=depth, include_types=include_types,
    )

    data: dict[str, Any] = {
        "source_path": surface.source_path,
        "functions": [
            {
                "name": f.name,
                "signature": f.signature,
                "line": f.line,
                "docstring_present": f.docstring_present,
                "docstring_summary": f.docstring_summary,
                "is_async": f.is_async,
                "decorators": f.decorators,
                "parameters": f.parameters,
                "return_type": f.return_type,
            }
            for f in surface.functions
        ],
        "classes": [
            {
                "name": c.name,
                "line": c.line,
                "bases": c.bases,
                "docstring_present": c.docstring_present,
                "docstring_summary": c.docstring_summary,
                "method_count": c.method_count,
                "public_methods": c.public_methods,
                "decorators": c.decorators,
            }
            for c in surface.classes
        ],
        "constants": [
            {
                "name": c.name,
                "line": c.line,
                "type": c.type,
                "value": c.value,
            }
            for c in surface.constants
        ],
        "type_aliases": surface.type_aliases,
        "re_exports": surface.re_exports,
        "all_exports": surface.all_exports,
        "coverage": round(surface.coverage, 3),
        "missing_docs": surface.missing_docs,
        "total_public": surface.total_public,
    }

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000
    return success_response("docs_api_surface", elapsed_ms, data)

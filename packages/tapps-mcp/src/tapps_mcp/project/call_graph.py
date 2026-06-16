"""Function-level call graph indexer (Epic 114 / TAP-4053)."""

from __future__ import annotations

from pathlib import Path

import structlog

from tapps_mcp.project.call_graph_analyze import analyze_file
from tapps_mcp.project.call_graph_cache import (
    index_fingerprint,
    load_call_graph_index,
    save_call_graph_index,
)
from tapps_mcp.project.call_graph_types import (
    CALL_GRAPH_CACHE_REL,
    INDEX_VERSION,
    CallEdge,
    CallGraphIndex,
    ResolutionGap,
    SymbolRecord,
)
from tapps_mcp.project.import_graph import _DEFAULT_EXCLUDES, _file_to_module, _should_skip

logger = structlog.get_logger(__name__)

__all__ = [
    "CALL_GRAPH_CACHE_REL",
    "INDEX_VERSION",
    "CallEdge",
    "CallGraphIndex",
    "ResolutionGap",
    "SymbolRecord",
    "build_call_graph_index",
    "load_call_graph_index",
]


def build_call_graph_index(
    project_root: Path,
    *,
    exclude_patterns: list[str] | None = None,
    top_level_package: str = "",
    force_rebuild: bool = False,
) -> CallGraphIndex:
    """Walk ``.py`` files, extract symbols and static CALLS edges."""
    fingerprint = index_fingerprint(project_root, exclude_patterns, top_level_package)
    if not force_rebuild:
        cached = load_call_graph_index(project_root)
        if cached is not None and cached.version == INDEX_VERSION and cached.fingerprint == fingerprint:
            return cached
        if cached is not None and cached.version != INDEX_VERSION:
            logger.info(
                "call_graph_cache_version_mismatch",
                cached_version=cached.version,
                current_version=INDEX_VERSION,
            )

    excludes = set(_DEFAULT_EXCLUDES)
    if exclude_patterns:
        excludes.update(exclude_patterns)

    symbols: list[SymbolRecord] = []
    edges: list[CallEdge] = []
    gaps: list[ResolutionGap] = []

    for py_file in sorted(project_root.rglob("*.py")):
        if _should_skip(py_file, excludes) or py_file.name.endswith("_pb2.py"):
            continue
        module = _file_to_module(py_file, project_root, top_level_package)
        if not module:
            continue
        file_symbols, file_edges, file_gaps = analyze_file(py_file, module, project_root)
        symbols.extend(file_symbols)
        edges.extend(file_edges)
        gaps.extend(file_gaps)

    symbols.sort(key=lambda s: (s.qualified_name, s.file_path, s.line))
    edges.sort(key=lambda e: (e.caller, e.line, e.callee_expr))
    gaps.sort(key=lambda g: (g.caller, g.line, g.expr))

    index = CallGraphIndex(
        symbols=symbols,
        edges=edges,
        resolution_gaps=gaps,
        project_root=str(project_root),
        fingerprint=fingerprint,
    )
    save_call_graph_index(project_root, index)
    logger.info("call_graph_index_built", symbols=len(symbols), edges=len(edges), gaps=len(gaps))
    return index

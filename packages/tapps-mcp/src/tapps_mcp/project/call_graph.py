"""Function-level call graph indexer (Epic 114 / TAP-4053)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import structlog

from tapps_mcp.project.call_graph_analyze import analyze_file
from tapps_mcp.project.call_graph_cache import (
    fingerprint_settings,
    load_call_graph_index,
    save_call_graph_index,
)
from tapps_mcp.project.call_graph_fingerprint import compute_index_fingerprint
from tapps_mcp.project.call_graph_types import (
    CALL_GRAPH_CACHE_REL,
    INDEX_VERSION,
    CallEdge,
    CallGraphIndex,
    ParseFailure,
    ResolutionGap,
    SymbolRecord,
)
from tapps_mcp.project.import_graph import _DEFAULT_EXCLUDES, _file_to_module, _should_skip

logger = structlog.get_logger(__name__)

# One analyze_file result tuple: (symbols, edges, gaps, parse_failures).
AnalyzeResult = tuple[
    list[SymbolRecord],
    list[CallEdge],
    list[ResolutionGap],
    list[ParseFailure],
]
# A file analyzer takes (file_path, module, project_root) and returns AnalyzeResult.
FileAnalyzer = Callable[[Path, str, Path], AnalyzeResult]

# Suffixes we collect during the walk. Python routes to the real analyzer;
# TypeScript routes to the S2 placeholder until the TS analyzer lands (TAP-4537).
_PY_SUFFIXES = (".py",)
_TS_SUFFIXES = (".ts", ".tsx")


def _analyze_ts_placeholder(
    file_path: Path,
    module: str,
    project_root: Path,
) -> AnalyzeResult:
    """Placeholder TS analyzer — returns empty results until S2 (TAP-4537).

    The real tree-sitter TypeScript analyzer arrives in S2; this keeps the
    suffix-dispatch wiring exercisable and the ``.ts``/``.tsx`` walk inert.
    """
    return ([], [], [], [])


def _analyzer_for(suffix: str) -> FileAnalyzer | None:
    """Route a file suffix to its analyzer, or ``None`` if unsupported."""
    if suffix in _PY_SUFFIXES:
        return analyze_file
    if suffix in _TS_SUFFIXES:
        return _analyze_ts_placeholder
    return None


def _ts_file_to_module(file_path: Path, project_root: Path) -> str:
    """Convert a ``.ts``/``.tsx`` path to a slash-delimited module name (TAP-4537).

    Mirrors ``import_graph._file_to_module`` for the Python side but keeps the
    TS convention: strip a leading ``src/`` segment and drop the ``.ts``/``.tsx``
    suffix. Returns "" when the path escapes ``project_root``.
    """
    try:
        rel = file_path.relative_to(project_root)
    except ValueError:
        return ""
    parts = list(rel.with_suffix("").parts)
    if not parts:
        return ""
    if parts[0] == "src":
        parts = parts[1:]
    return "/".join(parts) if parts else ""


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
    fp = fingerprint_settings(
        project_root,
        exclude_patterns=exclude_patterns,
        top_level_package=top_level_package,
    )
    fingerprint = compute_index_fingerprint(fp, index_version=INDEX_VERSION)
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
    parse_failures: list[ParseFailure] = []

    walk_suffixes = _PY_SUFFIXES + _TS_SUFFIXES
    source_files = sorted(
        f
        for suffix in walk_suffixes
        for f in project_root.rglob(f"*{suffix}")
    )
    for source_file in source_files:
        if _should_skip(source_file, excludes) or source_file.name.endswith("_pb2.py"):
            continue
        suffix = source_file.suffix
        analyzer = _analyzer_for(suffix)
        if analyzer is None:
            continue
        if suffix in _TS_SUFFIXES:
            module = _ts_file_to_module(source_file, project_root)
        else:
            module = _file_to_module(source_file, project_root, top_level_package)
        if not module:
            continue
        file_symbols, file_edges, file_gaps, file_failures = analyzer(
            source_file, module, project_root
        )
        symbols.extend(file_symbols)
        edges.extend(file_edges)
        gaps.extend(file_gaps)
        parse_failures.extend(file_failures)

    symbols.sort(key=lambda s: (s.qualified_name, s.file_path, s.line))
    edges.sort(key=lambda e: (e.caller, e.line, e.callee_expr))
    gaps.sort(key=lambda g: (g.caller, g.line, g.expr))
    parse_failures.sort(key=lambda p: (p.file_path, p.line))

    index = CallGraphIndex(
        symbols=symbols,
        edges=edges,
        resolution_gaps=gaps,
        parse_failures=parse_failures,
        project_root=str(project_root),
        fingerprint=fingerprint,
    )
    save_call_graph_index(project_root, index)
    logger.info("call_graph_index_built", symbols=len(symbols), edges=len(edges), gaps=len(gaps))
    return index

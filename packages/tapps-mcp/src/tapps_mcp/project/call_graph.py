"""Function-level call graph indexer (Epic 114 / TAP-4053)."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

import structlog

from tapps_mcp.project.call_graph_analyze import analyze_file
from tapps_mcp.project.call_graph_analyze_ts import analyze_file_ts, analyze_file_ts_full
from tapps_mcp.project.call_graph_cache import (
    fingerprint_settings,
    load_call_graph_index,
    save_call_graph_index,
)
from tapps_mcp.project.call_graph_fingerprint import (
    compute_index_fingerprint,
    compute_per_file_fingerprints,
)
from tapps_mcp.project.call_graph_resolve_ts import resolve_ts_cross_file
from tapps_mcp.project.call_graph_routes import (
    extract_fastapi_routes,
    extract_react_router_routes,
)
from tapps_mcp.project.call_graph_tsconfig import load_tsconfig_paths
from tapps_mcp.project.call_graph_types import (
    CALL_GRAPH_CACHE_REL,
    INDEX_VERSION,
    CallEdge,
    CallGraphIndex,
    DeferredCall,
    ModuleExports,
    ParseFailure,
    PerFileRaw,
    ResolutionGap,
    RouteEdge,
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

# Suffixes we collect during the walk. Python/``.pyi`` route to the Python
# analyzer; TS/JS routes to the tree-sitter TS analyzer (S2, TAP-4538).
_PY_SUFFIXES = (".py", ".pyi")
_TS_SUFFIXES = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")


def _analyzer_for(suffix: str) -> FileAnalyzer | None:
    """Route a file suffix to its analyzer, or ``None`` if unsupported."""
    if suffix in _PY_SUFFIXES:
        return analyze_file
    if suffix in _TS_SUFFIXES:
        return analyze_file_ts
    return None


def _ts_file_to_module(file_path: Path, project_root: Path) -> str:
    """Convert a TS/JS path to a slash-delimited module name (TAP-4537).

    Mirrors ``import_graph._file_to_module`` for the Python side but keeps the
    TS convention: strip a leading ``src/`` segment and drop the file suffix.
    Returns "" when the path escapes ``project_root``.
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
    "update_call_graph_index",
]


def _collect_source_files(project_root: Path, excludes: set[str]) -> list[Path]:
    """Return the sorted, filtered list of Python and TS/JS source files."""
    walk_suffixes = _PY_SUFFIXES + _TS_SUFFIXES
    source_files = sorted(f for suffix in walk_suffixes for f in project_root.rglob(f"*{suffix}"))
    return [
        f for f in source_files if not (_should_skip(f, excludes) or f.name.endswith("_pb2.py"))
    ]


def _analyze_one_file(
    source_file: Path,
    project_root: Path,
    top_level_package: str,
) -> tuple[str, PerFileRaw] | None:
    """Analyze a single source file, returning ``(rel_posix_path, PerFileRaw)``.

    Returns ``None`` when the suffix is unsupported or the module name resolves
    empty (path escapes ``project_root``) — matching the build walk's skips.
    This is the single expensive (parse) step the incremental update runs only
    for changed files.
    """
    suffix = source_file.suffix
    analyzer = _analyzer_for(suffix)
    if analyzer is None:
        return None
    if suffix in _TS_SUFFIXES:
        module = _ts_file_to_module(source_file, project_root)
    else:
        module = _file_to_module(source_file, project_root, top_level_package)
    if not module:
        return None
    rel = source_file.relative_to(project_root).as_posix()
    if suffix in _TS_SUFFIXES:
        (
            file_symbols,
            file_edges,
            file_gaps,
            file_failures,
            module_exports,
            deferred,
        ) = analyze_file_ts_full(source_file, module, project_root)
        raw = PerFileRaw(
            symbols=list(file_symbols),
            edges=list(file_edges),
            gaps=list(file_gaps),
            parse_failures=list(file_failures),
            routes=list(extract_react_router_routes(source_file, module, project_root)),
            ts_module=module,
            ts_exports=module_exports,
            ts_deferred=list(deferred),
        )
    else:
        file_symbols, file_edges, file_gaps, file_failures = analyzer(
            source_file, module, project_root
        )
        raw = PerFileRaw(
            symbols=list(file_symbols),
            edges=list(file_edges),
            gaps=list(file_gaps),
            parse_failures=list(file_failures),
            routes=list(extract_fastapi_routes(source_file, module, project_root)),
        )
    return rel, raw


def _finalize_index(
    project_root: Path,
    raw_by_file: dict[str, PerFileRaw],
    *,
    fingerprint: str,
    per_file_fingerprints: dict[str, str],
) -> CallGraphIndex:
    """Merge per-file raw results, run the TS post-pass, sort, and assemble.

    This is the *single* deterministic assembly path shared by
    ``build_call_graph_index`` and ``update_call_graph_index``. Feeding both
    through it is what guarantees byte-equivalence (ADR-0004 / AC2): an
    incremental update that reconstructs the same ``raw_by_file`` map yields an
    identical ``CallGraphIndex`` to a from-scratch build.

    Iteration follows sorted file order so merge order is deterministic
    regardless of how ``raw_by_file`` was assembled.
    """
    symbols: list[SymbolRecord] = []
    edges: list[CallEdge] = []
    gaps: list[ResolutionGap] = []
    parse_failures: list[ParseFailure] = []
    routes: list[RouteEdge] = []
    ts_exports: dict[str, ModuleExports] = {}
    ts_deferred: list[DeferredCall] = []

    for rel in sorted(raw_by_file):
        raw = raw_by_file[rel]
        symbols.extend(raw.symbols)
        edges.extend(raw.edges)
        gaps.extend(raw.gaps)
        parse_failures.extend(raw.parse_failures)
        routes.extend(raw.routes)
        if raw.ts_module is not None and raw.ts_exports is not None:
            ts_exports[raw.ts_module] = raw.ts_exports
            ts_deferred.extend(raw.ts_deferred)

    # S4 cross-file post-pass (TAP-4540): promote deferred default-export /
    # path-alias / re-export calls to edges, and follow already-resolved edges
    # through re-export barrels to their origin symbol. Anything unresolved
    # keeps its honest gap (ADR-0004 — never fabricate an edge). This ALWAYS
    # re-runs in full on an incremental update (TAP-4533): it is cheap and
    # cross-file, so a change to module B can flip module A's resolved edges.
    if ts_exports:
        symbol_names = {s.qualified_name for s in symbols}
        result = resolve_ts_cross_file(
            deferred_calls=ts_deferred,
            exports_by_module=ts_exports,
            symbol_names=symbol_names,
            resolved_edges=edges,
            tsconfig=load_tsconfig_paths(project_root),
        )
        edges.extend(result.new_edges)
        gaps.extend(result.remaining_gaps)
        if result.edge_rewrites:
            for edge in edges:
                rewritten = result.edge_rewrites.get(edge.callee)
                if rewritten is not None:
                    edge.callee = rewritten
        if result.dangling_callees:
            # Demote phantom edges (eager S3 named imports whose callee module
            # neither defines nor resolvably re-exports the symbol) to honest
            # gaps — never keep a fabricated target (ADR-0004).
            kept: list[CallEdge] = []
            for edge in edges:
                if edge.callee in result.dangling_callees:
                    gaps.append(
                        ResolutionGap(
                            edge.caller,
                            edge.callee_expr,
                            edge.line,
                            "reexport_unresolved",
                            language="typescript",
                        )
                    )
                else:
                    kept.append(edge)
            edges = kept

    symbols.sort(key=lambda s: (s.qualified_name, s.file_path, s.line))
    edges.sort(key=lambda e: (e.caller, e.line, e.callee_expr))
    gaps.sort(key=lambda g: (g.caller, g.line, g.expr))
    parse_failures.sort(key=lambda p: (p.file_path, p.line))
    routes.sort(key=lambda r: (r.file_path, r.line, r.method, r.path))

    index = CallGraphIndex(
        symbols=symbols,
        edges=edges,
        resolution_gaps=gaps,
        parse_failures=parse_failures,
        routes=routes,
        project_root=str(project_root),
        fingerprint=fingerprint,
        per_file_fingerprints=dict(per_file_fingerprints),
        raw_by_file=dict(raw_by_file),
    )
    save_call_graph_index(project_root, index)
    return index


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
        if (
            cached is not None
            and cached.version == INDEX_VERSION
            and cached.fingerprint == fingerprint
        ):
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

    raw_by_file: dict[str, PerFileRaw] = {}
    for source_file in _collect_source_files(project_root, excludes):
        analyzed = _analyze_one_file(source_file, project_root, top_level_package)
        if analyzed is not None:
            rel, raw = analyzed
            raw_by_file[rel] = raw

    index = _finalize_index(
        project_root,
        raw_by_file,
        fingerprint=fingerprint,
        per_file_fingerprints=compute_per_file_fingerprints(fp),
    )
    logger.info(
        "call_graph_index_built",
        symbols=len(index.symbols),
        edges=len(index.edges),
        gaps=len(index.resolution_gaps),
        routes=len(index.routes),
    )
    return index


def update_call_graph_index(
    project_root: Path,
    changed_paths: Iterable[Path | str],
    *,
    deleted_paths: Iterable[Path | str] = (),
    exclude_patterns: list[str] | None = None,
    top_level_package: str = "",
) -> CallGraphIndex:
    """Incrementally re-index only the changed/deleted files (TAP-4533).

    Loads the cached v5 index, drops the raw entries for the changed and deleted
    files, re-parses ONLY the changed files, merges the fresh raw results back
    into the persisted raw-per-file map, and re-runs the finalize step (TS
    cross-file post-pass + route linking + sort + atomic save).

    **Determinism (ADR-0004 / AC2):** the result is byte-equivalent to a full
    ``build_call_graph_index`` for the same tree because both feed the identical
    ``_finalize_index`` over the same ``raw_by_file`` map. Only *parsing* of
    unchanged files is skipped; the cross-file post-pass ALWAYS re-runs in full,
    since a change to module B can flip module A's resolved TS edges.

    Falls back to a full rebuild when there is no usable v5 cache (missing,
    unreadable, wrong version, or pre-v5 without a persisted raw map) — the
    incremental path needs the raw material to reconstruct exactly.

    A changed path that no longer exists on disk is treated as a deletion; a
    "changed" path that is not a recognized source file (unsupported suffix or
    outside ``project_root``) simply drops from the index, mirroring a rebuild.
    """
    fp = fingerprint_settings(
        project_root,
        exclude_patterns=exclude_patterns,
        top_level_package=top_level_package,
    )

    cached = load_call_graph_index(project_root)
    if cached is None or cached.version != INDEX_VERSION or not cached.raw_by_file:
        # No usable incremental base — a full rebuild is the only exact option.
        return build_call_graph_index(
            project_root,
            exclude_patterns=exclude_patterns,
            top_level_package=top_level_package,
            force_rebuild=True,
        )

    excludes = set(_DEFAULT_EXCLUDES)
    if exclude_patterns:
        excludes.update(exclude_patterns)

    def _rel(path: Path | str) -> str:
        """Normalize to a project-root-relative posix key.

        Mirrors ``_analyze_one_file``'s key scheme (``relative_to(project_root)``
        without resolving) so incremental keys collide exactly with build keys —
        load-bearing for byte-equivalence, since finalize merges in sorted-key
        order. Absolute paths under ``project_root`` are relativized directly;
        relative paths are treated as already project-relative.
        """
        p = Path(path)
        if p.is_absolute():
            try:
                return p.relative_to(project_root).as_posix()
            except ValueError:
                try:
                    return p.resolve().relative_to(project_root.resolve()).as_posix()
                except ValueError:
                    return p.as_posix()
        return p.as_posix()

    raw_by_file: dict[str, PerFileRaw] = dict(cached.raw_by_file)

    # Drop deleted files outright (AC4): their symbols/edges/routes vanish and
    # any edge/route that pointed at/from them is re-derived by the post-pass as
    # an honest gap or dropped — exactly as a full rebuild would produce, since
    # a deleted module contributes no exports/symbols to resolve against.
    for path in deleted_paths:
        raw_by_file.pop(_rel(path), None)

    # Re-analyze changed files. A changed path missing from disk is a deletion.
    for path in changed_paths:
        rel = _rel(path)
        source_file = project_root / rel
        if not source_file.is_file():
            raw_by_file.pop(rel, None)
            continue
        if _should_skip(source_file, excludes) or source_file.name.endswith("_pb2.py"):
            raw_by_file.pop(rel, None)
            continue
        analyzed = _analyze_one_file(source_file, project_root, top_level_package)
        if analyzed is None:
            # Unsupported suffix / empty module — drop from the index.
            raw_by_file.pop(rel, None)
            continue
        new_rel, raw = analyzed
        raw_by_file[new_rel] = raw

    fingerprint = compute_index_fingerprint(fp, index_version=INDEX_VERSION)
    index = _finalize_index(
        project_root,
        raw_by_file,
        fingerprint=fingerprint,
        per_file_fingerprints=compute_per_file_fingerprints(fp),
    )
    logger.info(
        "call_graph_index_incremental_update",
        symbols=len(index.symbols),
        edges=len(index.edges),
        gaps=len(index.resolution_gaps),
        routes=len(index.routes),
    )
    return index

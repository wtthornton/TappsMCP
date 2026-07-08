"""Shared types for function-level call graph indexing (TAP-4053)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

CALL_GRAPH_CACHE_REL = ".tapps-mcp/call-graph-index.json"
# v3 (TAP-4537): SymbolRecord gains a ``language`` tag for the TypeScript
# language-dispatch scaffold. Bumping this invalidates any v2 cache on load.
# v4 (TAP-4532): CallGraphIndex gains a persisted ``routes: list[RouteEdge]``
# for HTTP route -> handler edges (FastAPI decorators + React Router JSX).
# v5 (TAP-4533): CallGraphIndex gains persisted incremental-reindex material —
# ``per_file_fingerprints`` (changed-subset detection) and ``ts_exports`` /
# ``ts_deferred`` (the TS cross-file post-pass inputs, so unchanged TS files
# need not be re-parsed on an incremental update). Bumping invalidates v4.
# v6: Python resolver correctness — relative imports now honor ``ImportFrom.level``
# (``from .util`` resolves to the package-qualified module, not a bare name) and a
# nested function's calls are no longer mis-attributed to its enclosing function.
# The on-disk schema is unchanged, but cached EDGES differ, so bump to invalidate
# stale v5 indexes on upgrade (otherwise a project with static code keeps serving
# the old, less-accurate edges until its own source changes).
# v7: type-annotation binding — ``def f(x: C): x.m()`` and ``x: C = ...`` now resolve
# the method to ``C.m`` (previously an unresolved gap). Adds edges vs v6 (measured:
# +2067 edges / in-repo gap rate 0.61->0.51 on this repo), so bump to invalidate v6.
INDEX_VERSION = 7
SymbolKind = Literal["function", "method"]

# Stable taxonomy for resolution gaps (TAP-4092).
# TAP-4539 adds the TypeScript-specific reasons for deferred-resolution cases
# (default exports, untyped receivers, re-exports, tsconfig path aliases).
ResolutionGapReason = Literal[
    "unresolved_static_call",
    "dynamic_dispatch",
    "callback_opaque",
    "import_unresolved",
    "framework_hof",
    "receiver_untyped",
    "unresolved_default_export",
    "reexport_unresolved",
    "path_alias_unresolved",
]

PARSE_FAILURE_REASON = Literal["syntax_error", "decode_error", "io_error"]


@dataclass
class SymbolRecord:
    qualified_name: str
    module: str
    file_path: str
    line: int
    kind: SymbolKind
    # Source language of the symbol (TAP-4537). Defaults to "python" so cached
    # v2 indexes (which lack the field) still deserialize via index_from_dict.
    language: str = "python"


@dataclass
class CallEdge:
    caller: str
    callee: str
    callee_expr: str
    line: int
    resolved: bool


@dataclass
class ResolutionGap:
    caller: str
    expr: str
    line: int
    reason: ResolutionGapReason | str
    # Source language of the gap (TAP-4539). Lets the gap classifier apply
    # language-aware external/in-repo rules (e.g. TS `fs`/`lodash` are external,
    # not Python-stdlib misses). Defaults to "python" so older cached indexes
    # and existing call sites keep working.
    language: str = "python"


@dataclass
class ParseFailure:
    file_path: str
    line: int
    reason: PARSE_FAILURE_REASON | str


# HTTP route -> handler relationships as first-class edges (TAP-4532).
# ``framework`` names the router this edge came from ("fastapi" for Python
# decorator routes, "react-router" for React Router JSX). ``method`` is the
# uppercased HTTP verb for FastAPI (``GET``/``POST``/...) or the literal
# ``"ROUTE"`` for React Router (client-side routes have no HTTP method).
# ``handler_symbol`` is the qualified name of the handler function / component
# symbol when resolvable, else the bare local name (never a fabricated target).
RouteFramework = Literal["fastapi", "react-router"]


@dataclass
class RouteEdge:
    method: str
    path: str
    handler_symbol: str
    framework: RouteFramework | str
    file_path: str
    line: int


# --- TypeScript deferred cross-file resolution (TAP-4540) -----------------
# The following records are internal to the build-time cross-file resolution
# pass in ``call_graph.py``. They are NOT persisted in the on-disk index — they
# carry the structured hints the per-file TS analyzer cannot resolve on its own
# (default exports, tsconfig path aliases, re-export chains).

# How a deferred call binding was imported.
DeferredImportKind = Literal["default", "named", "namespace"]


@dataclass
class DeferredCall:
    """A TS call site the per-file analyzer could not resolve alone (TAP-4540).

    The cross-file post-pass tries to turn each ``DeferredCall`` into a
    ``CallEdge`` using module export tables + tsconfig aliases. When it cannot,
    the recorded ``gap`` is emitted verbatim so nothing is fabricated.
    """

    gap: ResolutionGap
    kind: DeferredImportKind
    # Real imported symbol name (named import) or accessed member (namespace).
    # ``None`` for a bare default import.
    imported_name: str | None
    # Resolved in-repo target module when the specifier is relative, else ``None``
    # (an unresolved specifier still needs ``specifier`` for alias resolution).
    target_module: str | None
    # Raw import specifier (``"./util"``, ``"@/util"``) for tsconfig aliasing.
    specifier: str
    caller: str


@dataclass
class PerFileRaw:
    """Persisted per-file raw analysis result for incremental re-index (TAP-4533).

    This is the pre-post-pass output of analyzing ONE source file: its symbols,
    raw edges, raw gaps, parse failures, routes, and (for TS files) the
    cross-file post-pass inputs. The finalize step merges every file's
    ``PerFileRaw`` and runs the TS post-pass over the combined set — so an
    incremental update re-parses only the changed files, swaps their
    ``PerFileRaw`` entries, and re-runs the identical finalize for a result
    byte-equivalent to a full rebuild (ADR-0004).

    Persisting the raw (pre-post-pass) edges/gaps — separately from the index's
    final post-processed edges/gaps — is what makes reconstruction exact: the TS
    post-pass is idempotent only when fed raw inputs, never its own output.
    """

    symbols: list[SymbolRecord] = field(default_factory=list)
    edges: list[CallEdge] = field(default_factory=list)
    gaps: list[ResolutionGap] = field(default_factory=list)
    parse_failures: list[ParseFailure] = field(default_factory=list)
    routes: list[RouteEdge] = field(default_factory=list)
    # TS-only cross-file post-pass inputs; ``ts_module`` is None for Python.
    ts_module: str | None = None
    ts_exports: ModuleExports | None = None
    ts_deferred: list[DeferredCall] = field(default_factory=list)


@dataclass
class ModuleExports:
    """Export surface of one TS module, for cross-file resolution (TAP-4540)."""

    module: str
    # Qualified name of the module's ``export default`` symbol, if any.
    default_symbol: str | None = None
    # Re-export edges: local exported name -> (from-specifier, origin name).
    # ``export {a as b} from "./y"`` -> {"b": ("./y", "a")}.
    reexports: dict[str, tuple[str, str]] = field(default_factory=dict)
    # ``export * from "./y"`` specifiers (star re-exports — any name may pass).
    star_reexports: list[str] = field(default_factory=list)


@dataclass
class CallGraphIndex:
    symbols: list[SymbolRecord] = field(default_factory=list)
    edges: list[CallEdge] = field(default_factory=list)
    resolution_gaps: list[ResolutionGap] = field(default_factory=list)
    parse_failures: list[ParseFailure] = field(default_factory=list)
    # HTTP route -> handler edges (TAP-4532). Persisted in the v4 index.
    routes: list[RouteEdge] = field(default_factory=list)
    project_root: str = ""
    fingerprint: str = ""
    version: int = INDEX_VERSION
    # Incremental-reindex material (TAP-4533), persisted in the v5 index.
    # ``per_file_fingerprints``: {relative_posix_path: content_hash} — the
    # changed subset for an incremental update is the diff of this map against a
    # freshly computed one. ``raw_by_file``: {relative_posix_path: PerFileRaw} —
    # the pre-post-pass analysis of every file, so an incremental update
    # re-parses only changed files then re-runs the finalize/post-pass over the
    # combined raw set (byte-equivalent to a full rebuild). Both are empty for a
    # v4 cache loaded before a rebuild, which correctly forces a full rebuild.
    per_file_fingerprints: dict[str, str] = field(default_factory=dict)
    raw_by_file: dict[str, PerFileRaw] = field(default_factory=dict)

    def symbol_names(self) -> set[str]:
        return {s.qualified_name for s in self.symbols}

    def callers_of(self, qualified_name: str) -> list[CallEdge]:
        return [e for e in self.edges if e.callee == qualified_name]

    def callees_of(self, qualified_name: str) -> list[CallEdge]:
        return [e for e in self.edges if e.caller == qualified_name]

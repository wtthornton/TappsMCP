"""Shared types for function-level call graph indexing (TAP-4053)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

CALL_GRAPH_CACHE_REL = ".tapps-mcp/call-graph-index.json"
# v3 (TAP-4537): SymbolRecord gains a ``language`` tag for the TypeScript
# language-dispatch scaffold. Bumping this invalidates any v2 cache on load.
INDEX_VERSION = 3
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
    project_root: str = ""
    fingerprint: str = ""
    version: int = INDEX_VERSION

    def symbol_names(self) -> set[str]:
        return {s.qualified_name for s in self.symbols}

    def callers_of(self, qualified_name: str) -> list[CallEdge]:
        return [e for e in self.edges if e.callee == qualified_name]

    def callees_of(self, qualified_name: str) -> list[CallEdge]:
        return [e for e in self.edges if e.caller == qualified_name]

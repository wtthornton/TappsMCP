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

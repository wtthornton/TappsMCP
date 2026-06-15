"""Shared types for function-level call graph indexing (TAP-4053)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

CALL_GRAPH_CACHE_REL = ".tapps-mcp/call-graph-index.json"
INDEX_VERSION = 1
SymbolKind = Literal["function", "method"]


@dataclass
class SymbolRecord:
    qualified_name: str
    module: str
    file_path: str
    line: int
    kind: SymbolKind


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
    reason: str


@dataclass
class CallGraphIndex:
    symbols: list[SymbolRecord] = field(default_factory=list)
    edges: list[CallEdge] = field(default_factory=list)
    resolution_gaps: list[ResolutionGap] = field(default_factory=list)
    project_root: str = ""
    fingerprint: str = ""
    version: int = INDEX_VERSION

    def symbol_names(self) -> set[str]:
        return {s.qualified_name for s in self.symbols}

    def callers_of(self, qualified_name: str) -> list[CallEdge]:
        return [e for e in self.edges if e.callee == qualified_name]

    def callees_of(self, qualified_name: str) -> list[CallEdge]:
        return [e for e in self.edges if e.caller == qualified_name]

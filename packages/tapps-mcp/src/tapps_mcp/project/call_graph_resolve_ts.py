"""Cross-file TypeScript resolution post-pass for the call graph (TAP-4540).

S4 of the call-graph language expansion. The per-file analyzer
(``call_graph_analyze_ts``) cannot resolve three import classes on its own —
default exports, tsconfig path aliases, and re-export chains — because each
needs *another* module's export surface. This module runs after every file is
analyzed and promotes those deferred cases to real edges where the origin
symbol can be found, following re-export chains to their origin.

Deterministic contract (ADR-0004): no LLM, no network. Every resolution ends at
a symbol that exists in the global symbol table, or the honest gap is kept. A
re-export cycle or a missing origin keeps the gap — never a fabricated edge.
"""

from __future__ import annotations

from dataclasses import dataclass

from tapps_mcp.project.call_graph_analyze_ts import _resolve_relative_module
from tapps_mcp.project.call_graph_tsconfig import TsconfigPaths, resolve_path_alias
from tapps_mcp.project.call_graph_types import (
    CallEdge,
    DeferredCall,
    ModuleExports,
    ResolutionGap,
)

# Cap re-export chain traversal so a pathological (or cyclic) barrel graph can
# never loop forever. Real re-export chains are shallow; 16 is generous.
_MAX_REEXPORT_DEPTH = 16


@dataclass
class TsResolutionResult:
    """Outcome of the cross-file TS post-pass."""

    # Newly promoted edges (a DeferredCall that resolved to an origin symbol).
    new_edges: list[CallEdge]
    # Gaps for DeferredCalls that stayed unresolved (emitted verbatim).
    remaining_gaps: list[ResolutionGap]
    # Callee rewrites: original qualified callee -> origin qualified callee, for
    # already-resolved edges whose target module merely re-exports the symbol.
    edge_rewrites: dict[str, str]
    # Dangling callees to demote from edge to gap: a named import resolved
    # eagerly (S3) to ``module.name`` where the module neither defines nor
    # (resolvably) re-exports the symbol — a broken chain. Keeping the edge
    # would fabricate a target (ADR-0004), so it becomes an honest gap instead.
    dangling_callees: set[str]


class _ReexportResolver:
    """Follows ``module.name`` through re-export tables to an origin symbol."""

    def __init__(
        self,
        exports_by_module: dict[str, ModuleExports],
        symbol_names: set[str],
    ) -> None:
        self._exports = exports_by_module
        self._symbols = symbol_names

    def exports_for(self, module: str) -> ModuleExports | None:
        """Export surface of ``module``, or ``None`` if it wasn't analyzed."""
        return self._exports.get(module)

    def is_symbol(self, qualified_name: str) -> bool:
        """True when ``qualified_name`` is a real symbol in the global table."""
        return qualified_name in self._symbols

    def resolve(self, module: str, name: str) -> str | None:
        """Resolve ``name`` exported by ``module`` to a real qualified symbol.

        Follows ``export { name } from "./other"`` / ``export * from "./other"``
        chains to the origin. Returns the qualified name when it lands on a real
        symbol, else ``None`` (unknown origin, broken chain, or cycle).
        """
        return self._resolve(module, name, depth=0, seen=set())

    def _resolve(
        self, module: str, name: str, *, depth: int, seen: set[tuple[str, str]]
    ) -> str | None:
        if depth > _MAX_REEXPORT_DEPTH:
            return None
        key = (module, name)
        if key in seen:
            return None  # cycle — keep the gap.
        seen.add(key)

        exports = self._exports.get(module)
        # Direct hit: the module owns a symbol with this qualified name.
        candidate = f"{module}.{name}"
        if candidate in self._symbols:
            # If the module also re-exports this name from elsewhere, the local
            # symbol wins (a same-name local definition shadows a re-export).
            if exports is None or name not in exports.reexports:
                return candidate

        if exports is None:
            return None

        # Named re-export: `export { origin as name } from "./src"`.
        reexport = exports.reexports.get(name)
        if reexport is not None:
            src_specifier, origin_name = reexport
            if src_specifier == "":
                # Local alias export (`export { impl as name }`) — origin lives
                # in this same module.
                origin_qual = f"{module}.{origin_name}"
                return origin_qual if origin_qual in self._symbols else None
            target = _resolve_relative_module(module, src_specifier)
            if target is None:
                return None  # non-relative re-export source — cannot follow.
            return self._resolve(target, origin_name, depth=depth + 1, seen=seen)

        # Star re-export: `export * from "./src"` — the name may live in any
        # star source. Try each in declared order; first real hit wins.
        for src_specifier in exports.star_reexports:
            target = _resolve_relative_module(module, src_specifier)
            if target is None:
                continue
            hit = self._resolve(target, name, depth=depth + 1, seen=set(seen))
            if hit is not None:
                return hit
        return None


def resolve_ts_cross_file(
    *,
    deferred_calls: list[DeferredCall],
    exports_by_module: dict[str, ModuleExports],
    symbol_names: set[str],
    resolved_edges: list[CallEdge],
    tsconfig: TsconfigPaths,
) -> TsResolutionResult:
    """Promote deferred TS calls to edges and follow re-export chains.

    ``deferred_calls`` are the per-file cases the analyzer could not resolve.
    ``exports_by_module`` maps every TS module to its export surface.
    ``symbol_names`` is the set of all qualified symbol names (origin check).
    ``resolved_edges`` are already-resolved edges we may rewrite when their
    callee module only re-exports the symbol. ``tsconfig`` supplies path aliases.
    """
    resolver = _ReexportResolver(exports_by_module, symbol_names)
    new_edges: list[CallEdge] = []
    remaining_gaps: list[ResolutionGap] = []

    for dc in deferred_calls:
        origin = _resolve_deferred_call(dc, resolver=resolver, tsconfig=tsconfig)
        if origin is not None:
            gap = dc.gap
            new_edges.append(CallEdge(dc.caller, origin, gap.expr, gap.line, True))
        else:
            remaining_gaps.append(dc.gap)

    # Follow-through for already-resolved edges: a named import that landed on a
    # barrel module (`barrel.x`) should point at the origin (`impl.x`) when
    # `barrel` merely re-exports `x`. When the callee is NOT a real symbol and
    # the re-export chain resolves nowhere, the eager S3 edge was a fabricated
    # target — demote it to a gap (dangling) rather than keep the phantom edge.
    edge_rewrites: dict[str, str] = {}
    dangling_callees: set[str] = set()
    for edge in resolved_edges:
        callee = edge.callee
        if callee in symbol_names or callee in edge_rewrites or callee in dangling_callees:
            continue
        module, _, name = callee.rpartition(".")
        if not module or not name:
            continue
        exports = exports_by_module.get(module)
        if exports is None:
            # The callee module isn't a TS module we analyzed — leave it be
            # (Python edges, or a symbol produced by another resolver).
            continue
        origin = resolver.resolve(module, name)
        if origin is not None and origin != callee:
            edge_rewrites[callee] = origin
            continue
        if origin is not None:
            continue
        # origin is None: the module neither defines the symbol nor resolvably
        # re-exports it. Only demote when the callee is a *re-export* that broke
        # (the name is in the re-export table or reachable solely via `export *`)
        # — a name the module locally exports but our extractor didn't capture as
        # a callable symbol is left as-is to preserve the S3 edge (no regression).
        if name in exports.reexports or exports.star_reexports:
            dangling_callees.add(callee)

    return TsResolutionResult(
        new_edges=new_edges,
        remaining_gaps=remaining_gaps,
        edge_rewrites=edge_rewrites,
        dangling_callees=dangling_callees,
    )


def _resolve_deferred_call(
    dc: DeferredCall,
    *,
    resolver: _ReexportResolver,
    tsconfig: TsconfigPaths,
) -> str | None:
    """Resolve a single deferred call to an origin symbol, or ``None``."""
    target_module = dc.target_module
    if target_module is None:
        # Path-alias case: resolve the specifier via tsconfig first. A missing
        # or non-matching config keeps the gap (never guess).
        target_module = resolve_path_alias(tsconfig, dc.specifier)
        if target_module is None:
            return None

    if dc.kind == "default":
        exports = resolver.exports_for(target_module)
        if exports is None or exports.default_symbol is None:
            return None
        # A default symbol is already a real qualified symbol (the analyzer only
        # sets it when it names an in-module declaration).
        return exports.default_symbol if resolver.is_symbol(exports.default_symbol) else None

    # Named / namespace import: resolve the accessed name through re-exports.
    if dc.imported_name is None:
        return None
    return resolver.resolve(target_module, dc.imported_name)

"""Call graph query layer: callers, callees, token-budgeted chains (TAP-4050)."""

from __future__ import annotations

import json
from collections import deque
from dataclasses import asdict
from typing import Any, Literal

from tapps_mcp.project.call_graph_types import CallGraphIndex, ResolutionGap

DEFAULT_TOKEN_BUDGET = 4000
_CHARS_PER_TOKEN = 4
QueryMode = Literal["callers", "callees", "chain", "all"]


def resolve_symbol_name(index: CallGraphIndex, symbol: str) -> str | None:
    """Resolve *symbol* to a qualified name in *index*."""
    trimmed = symbol.strip()
    if not trimmed:
        return None
    names = index.symbol_names()
    if trimmed in names:
        return trimmed
    suffix_matches = [n for n in names if n == trimmed or n.endswith(f".{trimmed}")]
    if len(suffix_matches) == 1:
        return suffix_matches[0]
    if len(suffix_matches) > 1:
        exact_tail = [n for n in suffix_matches if n.rsplit(".", maxsplit=1)[-1] == trimmed]
        if len(exact_tail) == 1:
            return exact_tail[0]
    return None


def _edge_payload(edge: Any) -> dict[str, Any]:
    return asdict(edge)


def _gaps_for_symbol(index: CallGraphIndex, qualified: str) -> list[dict[str, Any]]:
    gaps: list[ResolutionGap] = []
    for gap in index.resolution_gaps:
        if gap.caller == qualified or gap.caller.startswith(f"{qualified}."):
            gaps.append(gap)
    return [asdict(g) for g in gaps]


def _estimate_tokens(payload: object) -> int:
    return max(1, len(json.dumps(payload, default=str)) // _CHARS_PER_TOKEN)


def _collect_callers(
    index: CallGraphIndex,
    qualified: str,
    *,
    max_depth: int,
    token_budget: int,
) -> tuple[list[dict[str, Any]], bool]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    truncated = False
    frontier: deque[tuple[str, int]] = deque([(qualified, 0)])
    while frontier:
        current, depth = frontier.popleft()
        if depth >= max_depth:
            continue
        for edge in index.callers_of(current):
            if edge.caller in seen:
                continue
            item = {**_edge_payload(edge), "depth": depth + 1}
            trial = [*result, item]
            if _estimate_tokens(trial) > token_budget:
                truncated = True
                return result, truncated
            result.append(item)
            seen.add(edge.caller)
            frontier.append((edge.caller, depth + 1))
    return result, truncated


def _collect_callees(
    index: CallGraphIndex,
    qualified: str,
    *,
    max_depth: int,
    token_budget: int,
) -> tuple[list[dict[str, Any]], bool]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    truncated = False
    frontier: deque[tuple[str, int]] = deque([(qualified, 0)])
    while frontier:
        current, depth = frontier.popleft()
        if depth >= max_depth:
            continue
        for edge in index.callees_of(current):
            if edge.callee in seen:
                continue
            item = {**_edge_payload(edge), "depth": depth + 1}
            trial = [*result, item]
            if _estimate_tokens(trial) > token_budget:
                truncated = True
                return result, truncated
            result.append(item)
            seen.add(edge.callee)
            frontier.append((edge.callee, depth + 1))
    return result, truncated


def _collect_chain(
    index: CallGraphIndex,
    qualified: str,
    *,
    max_depth: int,
    token_budget: int,
) -> tuple[list[dict[str, Any]], bool]:
    """Depth-first caller chain from *qualified* upward (who calls who)."""
    chain: list[dict[str, Any]] = []
    truncated = False

    def walk(current: str, depth: int) -> None:
        nonlocal truncated
        if truncated or depth >= max_depth:
            return
        callers = index.callers_of(current)
        if not callers:
            return
        for edge in callers:
            item = {**_edge_payload(edge), "depth": depth + 1}
            trial = [*chain, item]
            if _estimate_tokens(trial) > token_budget:
                truncated = True
                return
            chain.append(item)
            walk(edge.caller, depth + 1)
            if truncated:
                return

    walk(qualified, 0)
    return chain, truncated


def query_call_graph(
    index: CallGraphIndex,
    symbol: str,
    *,
    mode: QueryMode = "all",
    max_depth: int = 5,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
) -> dict[str, Any]:
    """Query callers, callees, and/or chains for *symbol*."""
    qualified = resolve_symbol_name(index, symbol)
    if qualified is None:
        return {
            "symbol": symbol,
            "qualified_name": None,
            "found": False,
            "degraded": True,
            "error": "symbol_not_found",
            "callers": [],
            "callees": [],
            "chain": [],
            "resolution_gaps": [],
            "truncated": False,
        }

    gaps = _gaps_for_symbol(index, qualified)
    degraded = bool(gaps)
    truncated = False
    callers: list[dict[str, Any]] = []
    callees: list[dict[str, Any]] = []
    chain: list[dict[str, Any]] = []

    if mode in ("callers", "all"):
        callers, t1 = _collect_callers(
            index, qualified, max_depth=max_depth, token_budget=token_budget
        )
        truncated = truncated or t1
    if mode in ("callees", "all") and not truncated:
        remaining = token_budget - _estimate_tokens({"callers": callers})
        callees, t2 = _collect_callees(
            index, qualified, max_depth=max_depth, token_budget=max(remaining, 1)
        )
        truncated = truncated or t2
    if mode in ("chain", "all") and not truncated:
        remaining = token_budget - _estimate_tokens({"callers": callers, "callees": callees})
        chain, t3 = _collect_chain(
            index, qualified, max_depth=max_depth, token_budget=max(remaining, 1)
        )
        truncated = truncated or t3

    return {
        "symbol": symbol,
        "qualified_name": qualified,
        "found": True,
        "degraded": degraded,
        "callers": callers,
        "callees": callees,
        "chain": chain,
        "resolution_gaps": gaps,
        "truncated": truncated,
        "token_budget": token_budget,
    }


def compact_symbol_impact(
    index: CallGraphIndex,
    file_path: str,
    *,
    max_callers: int = 5,
    max_tests: int = 5,
    token_budget: int = 500,
) -> dict[str, Any] | None:
    """Token-capped caller/test summary for symbols defined in *file_path* (TAP-4270)."""
    normalized = file_path.replace("\\", "/")
    file_symbols = [
        s
        for s in index.symbols
        if s.file_path.replace("\\", "/") == normalized and s.kind in ("function", "method")
    ]
    if not file_symbols:
        return None

    from tapps_mcp.project.test_linker import build_test_edges, get_tests_for_symbol

    test_edges = build_test_edges(index)
    symbols_out: list[dict[str, Any]] = []
    truncated = False

    for sym in file_symbols:
        callers = [
            edge.caller.rsplit(".", maxsplit=1)[-1]
            for edge in index.callers_of(sym.qualified_name)[:max_callers]
        ]
        tests = get_tests_for_symbol(test_edges, sym.qualified_name, index=index)[:max_tests]
        entry = {
            "symbol": sym.qualified_name.rsplit(".", maxsplit=1)[-1],
            "qualified_name": sym.qualified_name,
            "callers": callers,
            "tests": [
                {
                    "test_file": t.get("test_file", ""),
                    "test_symbol": t.get("test_symbol", ""),
                }
                for t in tests
            ],
        }
        trial = {"symbols": [*symbols_out, entry]}
        if _estimate_tokens(trial) > token_budget:
            truncated = True
            break
        symbols_out.append(entry)

    if not symbols_out:
        return None
    return {
        "file_path": normalized,
        "symbols": symbols_out,
        "truncated": truncated,
        "token_budget": token_budget,
    }

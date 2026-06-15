"""TDAD-style TESTS edges linking test functions to code under test (TAP-4052)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from tapps_mcp.project.call_graph import build_call_graph_index
from tapps_mcp.project.call_graph_types import CallGraphIndex
from tapps_mcp.project.impact_analyzer import _is_test_file


@dataclass
class TestEdge:
    test_symbol: str
    test_file: str
    code_symbol: str
    code_file: str
    line: int


def _rel_path(path_str: str) -> str:
    return path_str.replace("\\", "/")


def is_test_path(path: Path | str) -> bool:
    return _is_test_file(Path(path))


def build_test_edges(
    index: CallGraphIndex,
    *,
    project_root: Path | None = None,
) -> list[TestEdge]:
    """Build TESTS edges from call-graph callees originating in test symbols."""
    symbol_by_name = {s.qualified_name: s for s in index.symbols}
    edges: list[TestEdge] = []
    seen: set[tuple[str, str]] = set()

    for sym in index.symbols:
        if not is_test_path(sym.file_path):
            continue
        if not sym.qualified_name.rsplit(".", maxsplit=1)[-1].startswith("test_"):
            continue
        for call in index.callees_of(sym.qualified_name):
            callee = symbol_by_name.get(call.callee)
            if callee is None or is_test_path(callee.file_path):
                continue
            key = (sym.qualified_name, call.callee)
            if key in seen:
                continue
            seen.add(key)
            edges.append(
                TestEdge(
                    test_symbol=sym.qualified_name,
                    test_file=_rel_path(sym.file_path),
                    code_symbol=call.callee,
                    code_file=_rel_path(callee.file_path),
                    line=call.line,
                )
            )

    edges.sort(key=lambda e: (e.code_symbol, e.test_symbol))
    if project_root is not None:
        _ = project_root  # reserved for future cache fingerprinting
    return edges


def edges_for_symbols(
    test_edges: list[TestEdge],
    symbols: set[str],
) -> list[TestEdge]:
    """Return TESTS edges whose code symbol is in *symbols*."""
    return [e for e in test_edges if e.code_symbol in symbols]


def get_tests_for_symbol(
    test_edges: list[TestEdge],
    symbol: str,
    *,
    index: CallGraphIndex | None = None,
) -> list[dict[str, object]]:
    """Return ranked test files/functions that exercise *symbol*."""
    from tapps_mcp.project.call_graph_queries import resolve_symbol_name

    symbols: set[str] = {symbol.strip()}
    if index is not None and symbol.strip():
        qualified = resolve_symbol_name(index, symbol.strip())
        if qualified:
            symbols = {qualified}

    ranked: dict[str, dict[str, object]] = {}
    for edge in edges_for_symbols(test_edges, symbols):
        entry = ranked.get(edge.test_symbol)
        if entry is None:
            entry = {
                "test_file": edge.test_file,
                "test_symbol": edge.test_symbol,
                "code_symbols": [],
            }
            ranked[edge.test_symbol] = entry
        code_syms = entry["code_symbols"]
        if isinstance(code_syms, list) and edge.code_symbol not in code_syms:
            code_syms.append(edge.code_symbol)

    return sorted(ranked.values(), key=lambda item: str(item.get("test_file", "")))


def load_or_build_test_edges(project_root: Path, *, force_rebuild: bool = False) -> list[TestEdge]:
    index = build_call_graph_index(project_root, force_rebuild=force_rebuild)
    return build_test_edges(index, project_root=project_root)


def test_edges_to_dicts(edges: list[TestEdge]) -> list[dict[str, object]]:
    return [asdict(e) for e in edges]

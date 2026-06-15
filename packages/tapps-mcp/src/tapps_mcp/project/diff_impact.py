"""Diff impact: rank affected tests for changed Python files (TAP-4054)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from tapps_mcp.project.call_graph import build_call_graph_index
from tapps_mcp.project.call_graph_queries import resolve_symbol_name
from tapps_mcp.project.impact_analyzer import analyze_impact, build_import_graph
from tapps_mcp.project.test_linker import build_test_edges, edges_for_symbols

DEFAULT_AFFECTED_TESTS_LIMIT = 20


@dataclass
class RankedTest:
    test_file: str
    score: float
    reasons: list[str]
    test_symbols: list[str]
    code_symbols: list[str]


def _symbols_in_file(index: object, rel_path: str) -> set[str]:
    from tapps_mcp.project.call_graph_types import CallGraphIndex

    if not isinstance(index, CallGraphIndex):
        return set()
    normalized = rel_path.replace("\\", "/")
    return {s.qualified_name for s in index.symbols if s.file_path.replace("\\", "/") == normalized}


def analyze_diff_impact(
    changed_files: list[Path],
    project_root: Path,
    *,
    max_tests: int = DEFAULT_AFFECTED_TESTS_LIMIT,
) -> dict[str, object]:
    """Rank tests affected by *changed_files* using TESTS edges and import impact."""
    index = build_call_graph_index(project_root)
    test_edges = build_test_edges(index, project_root=project_root)
    graph = build_import_graph(project_root)

    ranked: dict[str, RankedTest] = {}

    def bump(test_file: str, score: float, reason: str, test_sym: str = "", code_sym: str = "") -> None:
        entry = ranked.get(test_file)
        if entry is None:
            entry = RankedTest(test_file, 0.0, [], [], [])
            ranked[test_file] = entry
        entry.score += score
        if reason and reason not in entry.reasons:
            entry.reasons.append(reason)
        if test_sym and test_sym not in entry.test_symbols:
            entry.test_symbols.append(test_sym)
        if code_sym and code_sym not in entry.code_symbols:
            entry.code_symbols.append(code_sym)

    for changed in changed_files:
        try:
            rel = str(changed.resolve().relative_to(project_root.resolve()))
        except ValueError:
            rel = str(changed)
        rel_norm = rel.replace("\\", "/")
        changed_symbols = _symbols_in_file(index, rel_norm)

        for edge in edges_for_symbols(test_edges, changed_symbols):
            bump(
                edge.test_file,
                10.0,
                f"TESTS edge from {edge.code_symbol}",
                edge.test_symbol,
                edge.code_symbol,
            )

        for sym in changed_symbols:
            for edge in index.callers_of(sym):
                caller_sym = resolve_symbol_name(index, edge.caller)
                if caller_sym is None:
                    continue
                caller_file = next(
                    (s.file_path for s in index.symbols if s.qualified_name == caller_sym),
                    "",
                )
                if "test" in caller_file.replace("\\", "/").lower():
                    bump(
                        caller_file.replace("\\", "/"),
                        5.0,
                        f"test caller of changed symbol {sym}",
                        caller_sym,
                        sym,
                    )

        report = analyze_impact(changed.resolve(), project_root.resolve(), graph=graph)
        for test in report.test_files:
            bump(test.file_path.replace("\\", "/"), 3.0, test.reason)

    ordered = sorted(ranked.values(), key=lambda r: (-r.score, r.test_file))
    cap = max(1, max_tests)
    degraded = bool(index.resolution_gaps)
    return {
        "changed_files": [str(p) for p in changed_files],
        "affected_tests": [asdict(r) for r in ordered[:cap]],
        "total_affected_tests": len(ordered),
        "tests_edges_used": len(test_edges),
        "max_tests": cap,
        "degraded": degraded,
    }

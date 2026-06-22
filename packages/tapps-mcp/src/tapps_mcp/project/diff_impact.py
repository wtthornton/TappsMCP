"""Diff impact: rank affected tests for changed Python files (TAP-4054)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from tapps_mcp.project.call_graph import build_call_graph_index
from tapps_mcp.project.call_graph_queries import resolve_symbol_name
from tapps_mcp.project.impact_analyzer import analyze_impact, build_import_graph
from tapps_mcp.project.test_linker import build_test_edges, edges_for_symbols

DEFAULT_AFFECTED_TESTS_LIMIT = 20
DEFAULT_DOC_DRIFT_CALLER_THRESHOLD = 5


@dataclass
class RankedTest:
    test_file: str
    score: float
    reasons: list[str]
    test_symbols: list[str]
    code_symbols: list[str]


def _doc_paths_for_module(module: str) -> list[str]:
    """Heuristic doc paths agents may want to refresh after structural edits."""
    parts = module.split(".")
    candidates = [
        f"docs/{'/'.join(parts)}.md",
        f"docs/{parts[-1]}.md",
        f"docs/architecture/{parts[-1]}.md",
    ]
    if len(parts) >= 2:
        candidates.append(f"docs/{parts[0]}/{parts[-1]}.md")
    seen: set[str] = set()
    ordered: list[str] = []
    for path in candidates:
        if path not in seen:
            seen.add(path)
            ordered.append(path)
    return ordered


def _collect_doc_drift_hints(
    index: object,
    changed_symbols: set[str],
    *,
    caller_threshold: int = DEFAULT_DOC_DRIFT_CALLER_THRESHOLD,
) -> list[dict[str, object]]:
    from tapps_mcp.project.call_graph_types import CallGraphIndex

    if not isinstance(index, CallGraphIndex):
        return []
    hints: list[dict[str, object]] = []
    for sym in sorted(changed_symbols):
        direct_callers = index.callers_of(sym)
        if len(direct_callers) < caller_threshold:
            continue
        record = next((s for s in index.symbols if s.qualified_name == sym), None)
        module = record.module if record else sym.rsplit(".", maxsplit=1)[0]
        hints.append(
            {
                "symbol": sym,
                "direct_callers": len(direct_callers),
                "suggested_doc_paths": _doc_paths_for_module(module),
                "message": (
                    f"{sym} has {len(direct_callers)} direct callers — "
                    "consider updating related documentation."
                ),
            }
        )
    return hints


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
    doc_drift_caller_threshold: int = DEFAULT_DOC_DRIFT_CALLER_THRESHOLD,
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
    degraded = bool(index.resolution_gaps or index.parse_failures)
    all_changed_symbols: set[str] = set()
    for changed in changed_files:
        try:
            rel = str(changed.resolve().relative_to(project_root.resolve()))
        except ValueError:
            rel = str(changed)
        all_changed_symbols.update(_symbols_in_file(index, rel.replace("\\", "/")))

    doc_drift_hints = _collect_doc_drift_hints(
        index,
        all_changed_symbols,
        caller_threshold=doc_drift_caller_threshold,
    )
    payload: dict[str, object] = {
        "changed_files": [str(p) for p in changed_files],
        "affected_tests": [asdict(r) for r in ordered[:cap]],
        "total_affected_tests": len(ordered),
        "tests_edges_used": len(test_edges),
        "max_tests": cap,
        "degraded": degraded,
        "parse_failures": len(index.parse_failures),
    }
    if doc_drift_hints:
        payload["doc_drift_hints"] = doc_drift_hints
    return payload


def export_test_map(
    project_root: Path,
    output_path: Path | None = None,
    *,
    force_rebuild: bool = False,
) -> Path:
    """Write TDAD-style static test_map.txt from TESTS edges (TAP-4095)."""
    index = build_call_graph_index(project_root, force_rebuild=force_rebuild)
    test_edges = build_test_edges(index, project_root=project_root)
    target = output_path or (project_root / "test_map.txt")
    lines = [
        "# TappsMCP test_map — code symbol -> test file (TDAD static artifact)",
        f"# project: {project_root}",
        f"# tests_edges: {len(test_edges)}",
        "",
    ]
    for edge in sorted(test_edges, key=lambda e: (e.code_symbol, e.test_file)):
        lines.append(f"{edge.code_symbol}\t{edge.test_file}\t{edge.test_symbol}")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target

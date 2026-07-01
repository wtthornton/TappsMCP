"""Diff impact: rank affected tests for changed Python files (TAP-4054)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from tapps_mcp.pipeline.agent_contract import CALL_GRAPH_STALE_HINT
from tapps_mcp.project.call_graph import build_call_graph_index
from tapps_mcp.project.call_graph_queries import resolve_symbol_name
from tapps_mcp.project.impact_analyzer import analyze_impact, build_import_graph
from tapps_mcp.project.test_linker import build_test_edges, edges_for_symbols

DEFAULT_AFFECTED_TESTS_LIMIT = 20
DEFAULT_DOC_DRIFT_CALLER_THRESHOLD = 5

# Blast-radius caveat: in-repo gap rate at or above this fraction of edges means
# the impact analysis is materially incomplete and the review verdict should say so.
# Below the threshold (a handful of stray unresolved refs) is normal and must NOT
# raise a caveat — otherwise every healthy review gets a false alarm (TAP-4528).
BLAST_RADIUS_GAP_RATE_THRESHOLD = 0.10


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

    def bump(
        test_file: str, score: float, reason: str, test_sym: str = "", code_sym: str = ""
    ) -> None:
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


def build_diff_impact_enrichment(
    changed_files: list[Path],
    project_root: Path,
    *,
    max_callers: int = 10,
    max_tests: int = 10,
) -> dict[str, object]:
    """Per-changed-symbol callers + ranked affected tests for the review path (TAP-4526).

    Deterministic (ADR-0004): reuses the cached call-graph index and TESTS edges.
    Never rebuilds the index and never hits the network / an LLM. When the
    call-graph cache is missing or stale, returns a ``degraded`` block with a
    ``note`` and empty ``symbols`` — the caller must not crash.

    Returns a dict shaped::

        {
            "degraded": bool,
            "note": str,                # present only when degraded
            "cache_status": str,        # missing | unreadable | stale | ready
            "symbols": {
                "<qualified_name>": {
                    "callers": ["<qualified caller>", ...],   # in-repo only
                    "affected_tests": [{"test_file", "test_symbol"}, ...],
                },
                ...,
            },
            "changed_files": ["...", ...],
        }
    """
    from tapps_mcp.project.call_graph_cache import (
        load_call_graph_index,
        summarize_call_graph_cache,
    )

    changed_paths = [str(p) for p in changed_files]

    cache = summarize_call_graph_cache(project_root)
    status = str(cache.get("status", "missing"))
    if status != "ready":
        note = str(
            cache.get("hint")
            or "Call-graph cache is missing or stale — run tapps_call_graph or "
            "tapps_diff_impact(force_rebuild=True) to enable diff-impact enrichment."
        )
        return {
            "degraded": True,
            "note": note,
            "cache_status": status,
            "symbols": {},
            "changed_files": changed_paths,
        }

    index = load_call_graph_index(project_root)
    if index is None:
        return {
            "degraded": True,
            "note": CALL_GRAPH_STALE_HINT,
            "cache_status": "unreadable",
            "symbols": {},
            "changed_files": changed_paths,
        }

    from tapps_mcp.project.test_linker import build_test_edges, get_tests_for_symbol

    test_edges = build_test_edges(index, project_root=project_root)

    symbols_out: dict[str, dict[str, object]] = {}
    for changed in changed_files:
        try:
            rel = str(changed.resolve().relative_to(project_root.resolve()))
        except ValueError:
            rel = str(changed)
        for sym in sorted(_symbols_in_file(index, rel.replace("\\", "/"))):
            if sym in symbols_out:
                continue
            callers = [edge.caller for edge in index.callers_of(sym)[:max_callers]]
            tests = get_tests_for_symbol(test_edges, sym, index=index)[:max_tests]
            symbols_out[sym] = {
                "callers": callers,
                "affected_tests": [
                    {
                        "test_file": str(t.get("test_file", "")),
                        "test_symbol": str(t.get("test_symbol", "")),
                    }
                    for t in tests
                ],
            }

    degraded = bool(index.resolution_gaps or index.parse_failures)
    payload: dict[str, object] = {
        "degraded": degraded,
        "cache_status": status,
        "symbols": symbols_out,
        "changed_files": changed_paths,
    }
    if degraded:
        payload["note"] = (
            f"Call graph has {len(index.resolution_gaps)} unresolved reference(s) and "
            f"{len(index.parse_failures)} parse failure(s) — some callers/tests may be missing."
        )
    return payload


def caveat_from_call_graph_summary(
    summary: dict[str, object],
    *,
    gap_rate_threshold: float = BLAST_RADIUS_GAP_RATE_THRESHOLD,
) -> dict[str, object] | None:
    """Map a ``summarize_call_graph_cache`` summary → optional blast-radius caveat.

    Deterministic (ADR-0004): consumes the already-computed cache summary — no
    new analysis pass, no index rebuild, no network / LLM. Returns ``None`` for a
    healthy / low-gap region (no false alarms, TAP-4528 AC2) and a caveat dict
    when the call graph is materially incomplete::

        {
            "degraded": True,
            "in_repo_gap_rate": 0.42,
            "parse_failures": 2,
            "reason": "parse_failures" | "high_in_repo_gap_rate" | "cache_not_ready",
            "note": "<human-readable caveat>",
        }

    A caveat is raised when ANY of:
      * the cache is not ready (missing / stale / unreadable) — impact analysis
        could not run at all, so the blast radius is unknown;
      * one or more files failed to parse (``parse_failures > 0``);
      * the in-repo gap rate meets ``gap_rate_threshold`` — enough unresolved
        in-repo references that callers/tests are likely missing.
    """
    status = str(summary.get("status", "missing"))
    raw_parse_failures = summary.get("parse_failures", 0) or 0
    raw_gap_rate = summary.get("in_repo_gap_rate", 0.0) or 0.0
    parse_failures = int(raw_parse_failures) if isinstance(raw_parse_failures, (int, float)) else 0
    in_repo_gap_rate = float(raw_gap_rate) if isinstance(raw_gap_rate, (int, float)) else 0.0

    if status != "ready":
        note = str(
            summary.get("hint")
            or "Call-graph cache is not ready — the reviewed change's blast radius "
            "could not be computed, so impact analysis may be partial. Run "
            "tapps_call_graph or tapps_diff_impact(force_rebuild=True) to rebuild it."
        )
        return {
            "degraded": True,
            "in_repo_gap_rate": in_repo_gap_rate,
            "parse_failures": parse_failures,
            "reason": "cache_not_ready",
            "note": note,
        }

    if parse_failures > 0:
        return {
            "degraded": True,
            "in_repo_gap_rate": in_repo_gap_rate,
            "parse_failures": parse_failures,
            "reason": "parse_failures",
            "note": (
                f"{parse_failures} file(s) failed to parse — the call graph is "
                "incomplete for those modules, so this change's blast radius "
                "(callers / affected tests) may be partial."
            ),
        }

    if in_repo_gap_rate >= gap_rate_threshold:
        return {
            "degraded": True,
            "in_repo_gap_rate": in_repo_gap_rate,
            "parse_failures": parse_failures,
            "reason": "high_in_repo_gap_rate",
            "note": (
                f"In-repo call-graph gap rate is {in_repo_gap_rate:.0%} "
                f"(threshold {gap_rate_threshold:.0%}) — many in-repo references "
                "are unresolved, so this change's blast radius may be incomplete."
            ),
        }

    return None


def build_blast_radius_caveat(
    project_root: Path,
    *,
    gap_rate_threshold: float = BLAST_RADIUS_GAP_RATE_THRESHOLD,
) -> dict[str, object] | None:
    """Load the call-graph cache summary and derive a blast-radius caveat (TAP-4528).

    Thin convenience over :func:`caveat_from_call_graph_summary` for callers that
    do not already hold a summary. Deterministic: reuses
    ``summarize_call_graph_cache`` output only. Returns ``None`` when healthy.
    """
    from tapps_mcp.project.call_graph_cache import summarize_call_graph_cache

    summary = summarize_call_graph_cache(project_root)
    return caveat_from_call_graph_summary(summary, gap_rate_threshold=gap_rate_threshold)


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

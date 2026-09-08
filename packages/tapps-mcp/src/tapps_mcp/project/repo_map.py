"""Directory-level repo map over the existing call-graph + import-graph indexes (LANE_ISSUE).

A pure function of the indexes tapps-mcp already builds (ADR-0004: no LLM,
no embeddings, no ranking that needs a model): per-directory symbol/edge
counts, per-directory hubs, and global call-graph hotspots. Coupling
numbers are computed by the existing ``coupling_metrics`` module (Martin
afferent/efferent), the same one ``tapps_dependency_graph`` already uses —
not re-implemented here.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tapps_mcp.project.file_api import index_completeness, index_is_empty

if TYPE_CHECKING:
    from tapps_mcp.project.call_graph_types import CallGraphIndex

DEFAULT_TOKEN_BUDGET = 4000
DEFAULT_MAX_DIRS = 16
_CHARS_PER_TOKEN = 4
_MAX_HUBS_PER_DIR = 3
_MAX_HOTSPOTS = 20


def _normalize(path: str) -> str:
    return path.replace("\\", "/").lstrip("/")


def _dir_of(path: str) -> str:
    normalized = _normalize(path)
    if "/" not in normalized:
        return "."
    return normalized.rsplit("/", maxsplit=1)[0]


def _estimate_tokens(payload: object) -> int:
    return max(1, len(json.dumps(payload, default=str)) // _CHARS_PER_TOKEN)


def _module_to_dir(index: CallGraphIndex) -> dict[str, str]:
    """Map a Python dotted module name to its directory via the call-graph index.

    ``SymbolRecord.module`` and ``ImportGraph``'s module names are both
    produced by the same ``import_graph._file_to_module`` helper (verified:
    ``call_graph.py`` imports it directly for the Python side), so a
    coupling-metrics module name can be joined back to a directory through
    any symbol carrying that module — no re-derivation of the monorepo
    path-stripping rules.
    """
    mapping: dict[str, str] = {}
    for sym in index.symbols:
        if sym.module and sym.module not in mapping:
            mapping[sym.module] = _dir_of(sym.file_path)
    return mapping


def _directory_hubs(
    project_root: Path, module_to_dir: dict[str, str]
) -> dict[str, list[dict[str, Any]]]:
    """Top afferent-coupling modules per directory (Martin Ca), grouped."""
    from tapps_mcp.project.coupling_metrics import calculate_coupling
    from tapps_mcp.project.import_graph import build_import_graph

    graph = build_import_graph(project_root)
    couplings = calculate_coupling(graph)

    by_dir: dict[str, list[dict[str, Any]]] = {}
    for c in couplings:
        directory = module_to_dir.get(c.module)
        if directory is None:
            continue
        by_dir.setdefault(directory, []).append(
            {
                "module": c.module,
                "afferent": c.afferent,
                "efferent": c.efferent,
                "instability": round(c.instability, 3),
            }
        )
    for directory, hubs in by_dir.items():
        hubs.sort(key=lambda h: (-h["afferent"], h["module"]))
        by_dir[directory] = hubs[:_MAX_HUBS_PER_DIR]
    return by_dir


def _global_hotspots(index: CallGraphIndex) -> list[dict[str, Any]]:
    """Highest in-degree symbols across the whole repo (deterministic order)."""
    in_degree: Counter[str] = Counter(edge.callee for edge in index.edges)
    ranked = sorted(in_degree.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"qualified_name": name, "in_degree": count} for name, count in ranked[:_MAX_HOTSPOTS]]


def build_repo_map(
    index: CallGraphIndex,
    project_root: Path,
    *,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    max_dirs: int = DEFAULT_MAX_DIRS,
) -> dict[str, Any]:
    """Directory clusters, per-directory hubs, and global hotspots for *index*."""
    completeness = index_completeness(index)
    if index_is_empty(index):
        return {
            "project_root": str(project_root),
            "index_status": "unavailable",
            "directories": [],
            "hotspots": [],
            "total_directories": 0,
            "dropped": {"directories": 0, "hotspots": 0},
            "token_budget": token_budget,
            "max_dirs": max_dirs,
            "completeness": completeness,
        }

    symbol_counts: Counter[str] = Counter(_dir_of(s.file_path) for s in index.symbols)
    file_of_symbol = {s.qualified_name: s.file_path for s in index.symbols}
    edge_counts: Counter[str] = Counter()
    for edge in index.edges:
        caller_file = file_of_symbol.get(edge.caller)
        if caller_file is not None:
            edge_counts[_dir_of(caller_file)] += 1

    all_dirs = sorted(set(symbol_counts) | set(edge_counts))
    ranked = sorted(all_dirs, key=lambda d: (-symbol_counts.get(d, 0), d))
    total_directories = len(ranked)
    capped = ranked[: max(0, max_dirs)]
    dropped_by_cap = total_directories - len(capped)

    module_to_dir = _module_to_dir(index)
    hubs_by_dir = _directory_hubs(project_root, module_to_dir)

    directories: list[dict[str, Any]] = []
    dropped_by_budget = 0
    for directory in capped:
        entry = {
            "directory": directory,
            "symbols": symbol_counts.get(directory, 0),
            "edges": edge_counts.get(directory, 0),
            "hubs": hubs_by_dir.get(directory, []),
        }
        trial = {"directories": [*directories, entry], "hotspots": []}
        if _estimate_tokens(trial) > token_budget:
            dropped_by_budget += 1
            continue
        directories.append(entry)

    hotspots = _global_hotspots(index)
    dropped_hotspots = 0
    kept_hotspots: list[dict[str, Any]] = []
    for spot in hotspots:
        trial = {"directories": directories, "hotspots": [*kept_hotspots, spot]}
        if _estimate_tokens(trial) > token_budget:
            dropped_hotspots += 1
            continue
        kept_hotspots.append(spot)

    return {
        "project_root": str(project_root),
        "index_status": "ready",
        "directories": directories,
        "hotspots": kept_hotspots,
        "total_directories": total_directories,
        "dropped": {
            "directories": dropped_by_cap + dropped_by_budget,
            "hotspots": dropped_hotspots,
        },
        "token_budget": token_budget,
        "max_dirs": max_dirs,
        "completeness": completeness,
    }

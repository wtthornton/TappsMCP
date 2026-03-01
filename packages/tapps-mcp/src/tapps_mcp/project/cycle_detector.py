"""Cycle detection for Python import graphs.

Uses iterative DFS with color-based cycle detection to find all circular
import chains.  Cycles that only involve ``TYPE_CHECKING`` imports are
classified as warnings rather than errors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from tapps_mcp.project.import_graph import ImportGraph

logger = structlog.get_logger(__name__)

# Maximum number of cycles to report (avoids flooding output).
_MAX_REPORTED_CYCLES = 20

# Minimum cycle length to be considered meaningful.
_MIN_CYCLE_LENGTH = 2

# Length threshold for suggesting types.py extraction vs lazy import.
_SHORT_CYCLE_LENGTH = 2


@dataclass
class ImportCycle:
    """A single circular import chain."""

    modules: list[str] = field(default_factory=list)  # ordered cycle path
    length: int = 0
    involves_type_checking: bool = False  # True if ALL edges are TYPE_CHECKING
    severity: str = "error"  # "error" for runtime, "warning" for type-checking-only

    @property
    def description(self) -> str:
        """Human-readable cycle description."""
        if not self.modules:
            return ""
        return " -> ".join([*self.modules, self.modules[0]])


@dataclass
class CycleAnalysis:
    """Results of cycle detection across the whole import graph."""

    cycles: list[ImportCycle] = field(default_factory=list)
    total_modules: int = 0
    total_edges: int = 0
    runtime_cycles: int = 0
    type_checking_cycles: int = 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_cycles(
    graph: ImportGraph,
    *,
    include_type_checking: bool = False,
) -> CycleAnalysis:
    """Find all circular import chains in *graph*.

    Uses iterative DFS to find cycles.  By default only considers runtime
    and conditional imports (not ``TYPE_CHECKING``).

    Args:
        graph: The import graph to analyse.
        include_type_checking: When ``True``, include edges guarded by
            ``TYPE_CHECKING`` as well.

    Returns:
        A :class:`CycleAnalysis` with all detected cycles.
    """
    # Build adjacency list, filtering edges by type
    adjacency: dict[str, list[str]] = {mod: [] for mod in graph.modules}
    edge_type_map: dict[tuple[str, str], str] = {}

    for edge in graph.edges:
        if not include_type_checking and edge.import_type == "type_checking":
            continue
        adjacency.setdefault(edge.source_module, []).append(edge.target_module)
        # Record the edge type for classification later
        edge_type_map[(edge.source_module, edge.target_module)] = edge.import_type

    raw_cycles = _find_cycles_dfs(adjacency)

    # De-duplicate and normalise cycles
    unique_cycles = _deduplicate_cycles(raw_cycles)

    # Classify each cycle
    import_cycles: list[ImportCycle] = []
    for cycle_path in unique_cycles:
        if len(import_cycles) >= _MAX_REPORTED_CYCLES:
            break
        is_type_checking_only = _is_type_checking_only(cycle_path, edge_type_map, graph)
        severity = "warning" if is_type_checking_only else "error"
        import_cycles.append(
            ImportCycle(
                modules=cycle_path,
                length=len(cycle_path),
                involves_type_checking=is_type_checking_only,
                severity=severity,
            )
        )

    # Sort by length (shorter = more critical), then alphabetically
    import_cycles.sort(key=lambda c: (c.length, c.modules))

    runtime_count = sum(1 for c in import_cycles if c.severity == "error")
    tc_count = sum(1 for c in import_cycles if c.severity == "warning")

    analysis = CycleAnalysis(
        cycles=import_cycles,
        total_modules=len(graph.modules),
        total_edges=len(graph.edges),
        runtime_cycles=runtime_count,
        type_checking_cycles=tc_count,
    )

    logger.info(
        "cycle_detection_complete",
        total_cycles=len(import_cycles),
        runtime_cycles=runtime_count,
        type_checking_cycles=tc_count,
    )
    return analysis


def suggest_cycle_fixes(cycles: list[ImportCycle]) -> list[str]:
    """Generate suggestions for breaking import cycles.

    Args:
        cycles: List of detected import cycles.

    Returns:
        Human-readable suggestions for resolving the cycles.
    """
    if not cycles:
        return ["No import cycles detected - no fixes needed."]

    suggestions: list[str] = []

    for cycle in cycles:
        desc = cycle.description
        if cycle.severity == "warning":
            suggestions.append(
                f"Cycle ({desc}) only involves TYPE_CHECKING imports"
                " - safe at runtime but consider restructuring for clarity."
            )
        elif cycle.length == _SHORT_CYCLE_LENGTH:
            suggestions.append(
                f"Cycle ({desc}) - move shared types to a dedicated"
                " types.py or models.py module to break the cycle."
            )
        else:
            suggestions.append(
                f"Cycle ({desc}) - consider using TYPE_CHECKING guards"
                " for annotation-only imports or deferring imports"
                " to function scope (lazy import)."
            )

    # General advice
    if any(c.severity == "error" for c in cycles):
        suggestions.append(
            "Extract shared dependencies into a separate module to break runtime circular imports."
        )

    return suggestions


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_cycles_dfs(adjacency: dict[str, list[str]]) -> list[list[str]]:
    """Find all cycles using iterative DFS with color-based detection.

    Colors: WHITE = unvisited, GRAY = in current path, BLACK = fully explored.
    When we encounter a GRAY node we have found a cycle.
    """
    white, gray, black = 0, 1, 2
    color: dict[str, int] = dict.fromkeys(adjacency, white)
    cycles: list[list[str]] = []

    for start in adjacency:
        if color[start] != white:
            continue

        # Stack entries: (node, iterator_over_neighbours, path_so_far)
        path: list[str] = [start]
        path_set: set[str] = {start}
        color[start] = gray

        stack: list[tuple[str, int]] = [(start, 0)]

        while stack:
            node, idx = stack[-1]
            neighbours = adjacency.get(node, [])

            if idx < len(neighbours):
                # Advance the neighbour index
                stack[-1] = (node, idx + 1)
                neighbour = neighbours[idx]

                if color.get(neighbour, white) == gray and neighbour in path_set:
                    # Found a cycle - extract it
                    cycle_start_idx = path.index(neighbour)
                    cycle_path = path[cycle_start_idx:]
                    cycles.append(cycle_path)
                elif color.get(neighbour, white) == white:
                    color[neighbour] = gray
                    path.append(neighbour)
                    path_set.add(neighbour)
                    stack.append((neighbour, 0))
            else:
                # Backtrack
                color[node] = black
                stack.pop()
                if path:
                    removed = path.pop()
                    path_set.discard(removed)

    return cycles


def _deduplicate_cycles(raw_cycles: list[list[str]]) -> list[list[str]]:
    """Remove duplicate cycles (same nodes, different starting points)."""
    seen: set[tuple[str, ...]] = set()
    unique: list[list[str]] = []

    for cycle in raw_cycles:
        if len(cycle) < _MIN_CYCLE_LENGTH:
            continue
        # Normalise: rotate so the lexicographically smallest element is first
        normalised = _normalise_cycle(cycle)
        key = tuple(normalised)
        if key not in seen:
            seen.add(key)
            unique.append(normalised)

    return unique


def _normalise_cycle(cycle: list[str]) -> list[str]:
    """Rotate *cycle* so the smallest element comes first."""
    if not cycle:
        return cycle
    min_idx = cycle.index(min(cycle))
    return cycle[min_idx:] + cycle[:min_idx]


def _is_type_checking_only(
    cycle_path: list[str],
    edge_type_map: dict[tuple[str, str], str],
    graph: ImportGraph,
) -> bool:
    """Return True if every edge in the cycle is a TYPE_CHECKING import."""
    for i in range(len(cycle_path)):
        source = cycle_path[i]
        target = cycle_path[(i + 1) % len(cycle_path)]
        edge_type = edge_type_map.get((source, target), "")
        if not edge_type:
            # Look up from the full graph
            for edge in graph.edges:
                if edge.source_module == source and edge.target_module == target:
                    edge_type = edge.import_type
                    break
        if edge_type != "type_checking":
            return False
    return True

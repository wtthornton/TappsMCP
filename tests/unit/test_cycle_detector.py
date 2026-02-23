"""Tests for the cycle detector."""

from __future__ import annotations

from tapps_mcp.project.cycle_detector import (
    CycleAnalysis,
    ImportCycle,
    detect_cycles,
    suggest_cycle_fixes,
)
from tapps_mcp.project.import_graph import ImportEdge, ImportGraph

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph(
    edges: list[tuple[str, str, str]],
) -> ImportGraph:
    """Build an ImportGraph from (source, target, import_type) tuples."""
    modules: set[str] = set()
    import_edges: list[ImportEdge] = []
    for src, tgt, itype in edges:
        modules.add(src)
        modules.add(tgt)
        import_edges.append(
            ImportEdge(
                source_module=src,
                target_module=tgt,
                import_type=itype,
            )
        )
    return ImportGraph(edges=import_edges, modules=modules)


# ---------------------------------------------------------------------------
# detect_cycles
# ---------------------------------------------------------------------------


class TestDetectCycles:
    def test_no_cycles(self):
        """Clean graph returns no cycles."""
        graph = _make_graph(
            [
                ("a", "b", "runtime"),
                ("b", "c", "runtime"),
            ]
        )

        result = detect_cycles(graph)

        assert len(result.cycles) == 0
        assert result.runtime_cycles == 0
        assert result.type_checking_cycles == 0
        assert result.total_modules == 3

    def test_simple_cycle(self):
        """A -> B -> A is detected."""
        graph = _make_graph(
            [
                ("a", "b", "runtime"),
                ("b", "a", "runtime"),
            ]
        )

        result = detect_cycles(graph)

        assert len(result.cycles) == 1
        assert result.cycles[0].length == 2
        assert set(result.cycles[0].modules) == {"a", "b"}
        assert result.runtime_cycles == 1

    def test_longer_cycle(self):
        """A -> B -> C -> D -> A is detected."""
        graph = _make_graph(
            [
                ("a", "b", "runtime"),
                ("b", "c", "runtime"),
                ("c", "d", "runtime"),
                ("d", "a", "runtime"),
            ]
        )

        result = detect_cycles(graph)

        assert len(result.cycles) == 1
        assert result.cycles[0].length == 4
        assert set(result.cycles[0].modules) == {"a", "b", "c", "d"}

    def test_multiple_cycles(self):
        """Two independent cycles are both found."""
        graph = _make_graph(
            [
                ("a", "b", "runtime"),
                ("b", "a", "runtime"),
                ("c", "d", "runtime"),
                ("d", "c", "runtime"),
            ]
        )

        result = detect_cycles(graph)

        assert len(result.cycles) == 2
        assert result.runtime_cycles == 2

    def test_type_checking_cycle_excluded(self):
        """TYPE_CHECKING-only cycle excluded by default."""
        graph = _make_graph(
            [
                ("a", "b", "type_checking"),
                ("b", "a", "type_checking"),
            ]
        )

        result = detect_cycles(graph, include_type_checking=False)

        assert len(result.cycles) == 0

    def test_type_checking_cycle_included(self):
        """TYPE_CHECKING cycle included when flag is set."""
        graph = _make_graph(
            [
                ("a", "b", "type_checking"),
                ("b", "a", "type_checking"),
            ]
        )

        result = detect_cycles(graph, include_type_checking=True)

        assert len(result.cycles) == 1
        assert result.cycles[0].involves_type_checking is True
        assert result.cycles[0].severity == "warning"
        assert result.type_checking_cycles == 1

    def test_cycle_severity_runtime(self):
        """Runtime cycles have severity 'error'."""
        graph = _make_graph(
            [
                ("a", "b", "runtime"),
                ("b", "a", "runtime"),
            ]
        )

        result = detect_cycles(graph)

        assert result.cycles[0].severity == "error"

    def test_cycle_severity_type_checking(self):
        """TYPE_CHECKING-only cycles have severity 'warning'."""
        graph = _make_graph(
            [
                ("a", "b", "type_checking"),
                ("b", "a", "type_checking"),
            ]
        )

        result = detect_cycles(graph, include_type_checking=True)

        assert result.cycles[0].severity == "warning"

    def test_mixed_cycle_is_runtime(self):
        """Cycle with mixed edge types is classified as runtime (error)."""
        graph = _make_graph(
            [
                ("a", "b", "runtime"),
                ("b", "a", "type_checking"),
            ]
        )

        # include_type_checking must be True to see the type_checking edge
        result = detect_cycles(graph, include_type_checking=True)

        assert len(result.cycles) == 1
        assert result.cycles[0].severity == "error"
        assert result.cycles[0].involves_type_checking is False

    def test_max_cycles_limit(self):
        """At most 20 cycles are reported."""
        # Create 25 independent 2-node cycles
        edges = []
        for i in range(25):
            a = f"mod_{i}_a"
            b = f"mod_{i}_b"
            edges.append((a, b, "runtime"))
            edges.append((b, a, "runtime"))

        graph = _make_graph(edges)
        result = detect_cycles(graph)

        assert len(result.cycles) <= 20


# ---------------------------------------------------------------------------
# ImportCycle.description
# ---------------------------------------------------------------------------


class TestCycleDescription:
    def test_description_format(self):
        """Description shows 'A -> B -> C -> A' format."""
        cycle = ImportCycle(modules=["a", "b", "c"], length=3)
        assert cycle.description == "a -> b -> c -> a"

    def test_empty_description(self):
        """Empty cycle returns empty string."""
        cycle = ImportCycle(modules=[], length=0)
        assert cycle.description == ""

    def test_two_node_description(self):
        """Two-node cycle shows both nodes plus wrap-around."""
        cycle = ImportCycle(modules=["x", "y"], length=2)
        assert cycle.description == "x -> y -> x"


# ---------------------------------------------------------------------------
# suggest_cycle_fixes
# ---------------------------------------------------------------------------


class TestSuggestCycleFixes:
    def test_no_cycles(self):
        """No cycles yields 'no fixes needed' message."""
        suggestions = suggest_cycle_fixes([])
        assert len(suggestions) == 1
        assert "no fixes needed" in suggestions[0].lower()

    def test_two_node_cycle_suggestion(self):
        """Two-node runtime cycle suggests types.py extraction."""
        cycles = [
            ImportCycle(modules=["a", "b"], length=2, severity="error"),
        ]
        suggestions = suggest_cycle_fixes(cycles)
        combined = " ".join(suggestions)
        assert "types.py" in combined or "models.py" in combined

    def test_longer_cycle_suggestion(self):
        """Longer cycle suggests TYPE_CHECKING or lazy import."""
        cycles = [
            ImportCycle(modules=["a", "b", "c"], length=3, severity="error"),
        ]
        suggestions = suggest_cycle_fixes(cycles)
        combined = " ".join(suggestions)
        assert "TYPE_CHECKING" in combined or "lazy import" in combined

    def test_type_checking_cycle_suggestion(self):
        """TYPE_CHECKING-only cycle gets appropriate suggestion."""
        cycles = [
            ImportCycle(
                modules=["a", "b"],
                length=2,
                involves_type_checking=True,
                severity="warning",
            ),
        ]
        suggestions = suggest_cycle_fixes(cycles)
        combined = " ".join(suggestions)
        assert "TYPE_CHECKING" in combined

    def test_general_advice_for_runtime(self):
        """Runtime cycles get general extract-shared-dependency advice."""
        cycles = [
            ImportCycle(modules=["a", "b"], length=2, severity="error"),
        ]
        suggestions = suggest_cycle_fixes(cycles)
        combined = " ".join(suggestions)
        assert "extract" in combined.lower() or "shared" in combined.lower()


# ---------------------------------------------------------------------------
# CycleAnalysis
# ---------------------------------------------------------------------------


class TestCycleAnalysis:
    def test_default_values(self):
        """CycleAnalysis has sensible defaults."""
        analysis = CycleAnalysis()
        assert analysis.cycles == []
        assert analysis.total_modules == 0
        assert analysis.total_edges == 0
        assert analysis.runtime_cycles == 0
        assert analysis.type_checking_cycles == 0

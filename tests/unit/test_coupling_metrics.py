"""Tests for module coupling metrics."""

from __future__ import annotations

from tapps_mcp.project.coupling_metrics import (
    HUB_THRESHOLD,
    ModuleCoupling,
    calculate_coupling,
    suggest_coupling_fixes,
)
from tapps_mcp.project.import_graph import ImportEdge, ImportGraph

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph(
    edges: list[tuple[str, str]],
    modules: set[str] | None = None,
) -> ImportGraph:
    """Build an ImportGraph from (source, target) tuples."""
    all_modules: set[str] = modules or set()
    import_edges: list[ImportEdge] = []
    for src, tgt in edges:
        all_modules.add(src)
        all_modules.add(tgt)
        import_edges.append(ImportEdge(source_module=src, target_module=tgt))
    return ImportGraph(edges=import_edges, modules=all_modules)


# ---------------------------------------------------------------------------
# calculate_coupling
# ---------------------------------------------------------------------------


class TestCalculateCoupling:
    def test_empty_graph(self):
        """No modules produces no metrics."""
        graph = ImportGraph(edges=[], modules=set())
        result = calculate_coupling(graph)
        assert result == []

    def test_single_module_no_deps(self):
        """One isolated module has zero coupling."""
        graph = ImportGraph(edges=[], modules={"lonely"})
        result = calculate_coupling(graph)

        assert len(result) == 1
        assert result[0].module == "lonely"
        assert result[0].afferent == 0
        assert result[0].efferent == 0
        assert result[0].instability == 0.0
        assert result[0].is_hub is False

    def test_afferent_coupling(self):
        """Count modules that depend on target."""
        graph = _make_graph(
            [
                ("a", "c"),
                ("b", "c"),
                ("d", "c"),
            ]
        )

        result = calculate_coupling(graph)
        c_metrics = next(m for m in result if m.module == "c")

        assert c_metrics.afferent == 3

    def test_efferent_coupling(self):
        """Count modules that target depends on."""
        graph = _make_graph(
            [
                ("a", "b"),
                ("a", "c"),
                ("a", "d"),
            ]
        )

        result = calculate_coupling(graph)
        a_metrics = next(m for m in result if m.module == "a")

        assert a_metrics.efferent == 3

    def test_instability_calculation(self):
        """I = Ce / (Ca + Ce) is calculated correctly."""
        # Module "a" has Ce=3, Ca=0 -> I = 1.0 (fully unstable)
        graph = _make_graph(
            [
                ("a", "b"),
                ("a", "c"),
                ("a", "d"),
            ]
        )

        result = calculate_coupling(graph)
        a_metrics = next(m for m in result if m.module == "a")

        assert a_metrics.instability == 1.0

    def test_instability_stable(self):
        """Module with only afferent coupling has I = 0.0."""
        graph = _make_graph(
            [
                ("b", "a"),
                ("c", "a"),
                ("d", "a"),
            ]
        )

        result = calculate_coupling(graph)
        a_metrics = next(m for m in result if m.module == "a")

        assert a_metrics.instability == 0.0

    def test_instability_balanced(self):
        """Module with equal Ca and Ce has I = 0.5."""
        graph = _make_graph(
            [
                ("x", "center"),
                ("y", "center"),
                ("center", "a"),
                ("center", "b"),
            ]
        )

        result = calculate_coupling(graph)
        center = next(m for m in result if m.module == "center")

        assert center.afferent == 2
        assert center.efferent == 2
        assert center.instability == 0.5

    def test_hub_detection(self):
        """Module with high Ca AND high Ce is flagged as hub."""
        edges = []
        # Create a hub module that is depended on by 8+ and depends on 8+
        for i in range(HUB_THRESHOLD):
            src = f"dependent_{i}"
            edges.append((src, "hub_module"))
        for i in range(HUB_THRESHOLD):
            tgt = f"dependency_{i}"
            edges.append(("hub_module", tgt))

        graph = _make_graph(edges)
        result = calculate_coupling(graph)
        hub = next(m for m in result if m.module == "hub_module")

        assert hub.is_hub is True
        assert hub.afferent >= HUB_THRESHOLD
        assert hub.efferent >= HUB_THRESHOLD

    def test_not_hub_low_afferent(self):
        """High efferent but low afferent is NOT a hub."""
        edges = []
        for i in range(HUB_THRESHOLD):
            edges.append(("mod", f"dep_{i}"))

        graph = _make_graph(edges)
        result = calculate_coupling(graph)
        mod = next(m for m in result if m.module == "mod")

        assert mod.is_hub is False

    def test_sorting_by_total_coupling(self):
        """Results are sorted by total coupling descending."""
        graph = _make_graph(
            [
                ("a", "b"),
                ("c", "d"),
                ("c", "e"),
                ("c", "f"),
                ("x", "c"),
            ]
        )

        result = calculate_coupling(graph)

        # "c" has Ce=3 + Ca=1 = 4, should be first
        assert result[0].module == "c"

    def test_duplicate_edges_counted_once(self):
        """Multiple imports between same pair count as one coupling."""
        graph = _make_graph(
            [
                ("a", "b"),
                ("a", "b"),
                ("a", "b"),
            ]
        )

        result = calculate_coupling(graph)
        a_metrics = next(m for m in result if m.module == "a")

        # Only one unique efferent dependency
        assert a_metrics.efferent == 1


# ---------------------------------------------------------------------------
# suggest_coupling_fixes
# ---------------------------------------------------------------------------


class TestSuggestCouplingFixes:
    def test_empty_metrics(self):
        """No modules yields default message."""
        suggestions = suggest_coupling_fixes([])
        assert len(suggestions) == 1
        assert "no modules" in suggestions[0].lower()

    def test_hub_suggestion(self):
        """Hub module gets a splitting suggestion."""
        metrics = [
            ModuleCoupling(
                module="big_mod",
                afferent=10,
                efferent=12,
                instability=0.545,
                is_hub=True,
            ),
        ]
        suggestions = suggest_coupling_fixes(metrics)
        combined = " ".join(suggestions)
        assert "big_mod" in combined
        assert "splitting" in combined.lower() or "split" in combined.lower()

    def test_high_efferent_suggestion(self):
        """High efferent (non-hub) gets dependency reduction suggestion."""
        metrics = [
            ModuleCoupling(
                module="importer",
                afferent=2,
                efferent=10,
                instability=0.833,
                is_hub=False,
            ),
        ]
        suggestions = suggest_coupling_fixes(metrics)
        combined = " ".join(suggestions)
        assert "importer" in combined

    def test_acceptable_coupling(self):
        """Low coupling gives positive message."""
        metrics = [
            ModuleCoupling(module="good", afferent=2, efferent=3, instability=0.6),
        ]
        suggestions = suggest_coupling_fixes(metrics)
        combined = " ".join(suggestions)
        assert "acceptable" in combined.lower() or "within" in combined.lower()

    def test_limit_respected(self):
        """Limit caps the number of suggestions for hubs."""
        metrics = [
            ModuleCoupling(
                module=f"hub_{i}",
                afferent=10,
                efferent=10,
                instability=0.5,
                is_hub=True,
            )
            for i in range(10)
        ]
        suggestions = suggest_coupling_fixes(metrics, limit=3)
        # At most 3 hub suggestions + possibly general advice
        hub_suggestions = [s for s in suggestions if "hub_" in s]
        assert len(hub_suggestions) <= 3

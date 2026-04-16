"""Tests for docs_mcp.generators.pattern_poster.

Covers:
- ArchPatternPosterGenerator.generate_single: HTML structure, badge, SVG presence
- ArchPatternPosterGenerator.generate_comparison: 2×3 grid, detected highlight
- Per-archetype _panel_svg topology shapes (distinct SVG content per archetype)
- prefers-reduced-motion CSS rule present
- DiagramGenerator dispatching to poster for pattern_card/html and pattern_comparison
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from docs_mcp.generators.diagrams import DiagramGenerator
from docs_mcp.generators.pattern_poster import ArchPatternPosterGenerator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_result(archetype: str = "layered", confidence: float = 0.85) -> MagicMock:
    r = MagicMock()
    r.archetype = archetype
    r.confidence = confidence
    r.evidence = [f"{archetype} evidence"]
    return r


def _pkg(names: list[str]) -> list[tuple[str, str]]:
    roles = ["presentation", "business", "data", "infra", "business", "data"]
    return [(n, roles[i % len(roles)]) for i, n in enumerate(names)]


# ---------------------------------------------------------------------------
# generate_single
# ---------------------------------------------------------------------------


class TestGenerateSingle:
    def test_returns_html_string(self) -> None:
        gen = ArchPatternPosterGenerator()
        html = gen.generate_single([], _mock_result("layered", 0.9))
        assert "<!DOCTYPE html>" in html
        assert "<html" in html

    def test_badge_contains_archetype_label(self) -> None:
        gen = ArchPatternPosterGenerator()
        html = gen.generate_single([], _mock_result("microservice", 0.75))
        assert "MICROSERVICE" in html

    def test_badge_contains_confidence(self) -> None:
        gen = ArchPatternPosterGenerator()
        html = gen.generate_single([], _mock_result("pipeline", 0.62))
        assert "62%" in html

    def test_svg_present_in_output(self) -> None:
        gen = ArchPatternPosterGenerator()
        html = gen.generate_single([], _mock_result("hexagonal", 0.8))
        assert "<svg" in html
        assert "</svg>" in html

    def test_legend_present(self) -> None:
        gen = ArchPatternPosterGenerator()
        html = gen.generate_single([], _mock_result("layered", 0.9))
        assert "Presentation" in html
        assert "Business" in html

    def test_prefers_reduced_motion_rule_present(self) -> None:
        gen = ArchPatternPosterGenerator()
        html = gen.generate_single([], _mock_result("layered", 0.9))
        assert "prefers-reduced-motion" in html
        assert "animation: none" in html

    def test_packages_used_in_layered_output(self) -> None:
        gen = ArchPatternPosterGenerator()
        pkgs = _pkg(["views", "services", "models", "config"])
        html = gen.generate_single(pkgs, _mock_result("layered", 0.9))
        assert "views" in html

    def test_low_confidence_result_still_renders(self) -> None:
        gen = ArchPatternPosterGenerator()
        html = gen.generate_single([], _mock_result("unknown", 0.1))
        assert "<!DOCTYPE html>" in html


# ---------------------------------------------------------------------------
# generate_comparison
# ---------------------------------------------------------------------------


class TestGenerateComparison:
    def test_contains_all_six_archetypes(self) -> None:
        gen = ArchPatternPosterGenerator()
        html = gen.generate_comparison()
        for arch in [
            "EVENT DRIVEN",
            "LAYERED",
            "MONOLITH",
            "MICROSERVICE",
            "PIPELINE",
            "HEXAGONAL",
        ]:
            assert arch in html

    def test_title_banner_present(self) -> None:
        gen = ArchPatternPosterGenerator()
        html = gen.generate_comparison()
        assert "SOFTWARE ARCHITECTURAL" in html
        assert "PATTERNS" in html

    def test_detected_arch_highlighted(self) -> None:
        gen = ArchPatternPosterGenerator()
        html = gen.generate_comparison(detected_archetype="microservice")
        # The highlighted panel gets the 'highlighted' CSS class
        assert 'class="panel highlighted"' in html

    def test_no_highlight_when_no_detected(self) -> None:
        gen = ArchPatternPosterGenerator()
        html = gen.generate_comparison()
        # CSS defines .panel.highlighted but no element should carry that class
        assert 'class="panel highlighted"' not in html

    def test_six_svg_panels_present(self) -> None:
        gen = ArchPatternPosterGenerator()
        html = gen.generate_comparison()
        # Each panel embeds one <svg> element
        assert html.count("<svg") == 6

    def test_docs_mcp_site_tag(self) -> None:
        gen = ArchPatternPosterGenerator()
        html = gen.generate_comparison()
        assert "docs-mcp" in html


# ---------------------------------------------------------------------------
# Per-archetype topology (_panel_svg distinctness)
# ---------------------------------------------------------------------------


class TestPanelSvgTopologies:
    """Each archetype must produce SVG with its canonical marker elements."""

    def _svg(self, arch: str) -> str:
        return ArchPatternPosterGenerator()._panel_svg(arch, [], w=280, h=200)

    def test_layered_has_four_role_bands(self) -> None:
        svg = self._svg("layered")
        # Four band rectangles plus the background rect — check for role labels
        for label in ["Presentation", "Business", "Data Access", "Persistence"]:
            assert label in svg

    def test_event_driven_has_bus(self) -> None:
        svg = self._svg("event_driven")
        assert "Event" in svg
        assert "Bus" in svg

    def test_event_driven_has_publishers_and_consumers(self) -> None:
        svg = self._svg("event_driven")
        assert "Publisher" in svg
        assert "Consumer" in svg

    def test_hexagonal_has_domain_core(self) -> None:
        svg = self._svg("hexagonal")
        assert "Domain" in svg
        assert "Core" in svg
        # Hexagon is a <polygon>
        assert "<polygon" in svg

    def test_hexagonal_has_adapter_ring(self) -> None:
        svg = self._svg("hexagonal")
        assert "REST API" in svg
        assert "DB Repo" in svg

    def test_microservice_has_gateway(self) -> None:
        svg = self._svg("microservice")
        assert "API Gateway" in svg

    def test_microservice_has_db_cylinders(self) -> None:
        svg = self._svg("microservice")
        # Each service has a DB ellipse
        assert svg.count("<ellipse") >= 3

    def test_monolith_has_container_label(self) -> None:
        svg = self._svg("monolith")
        assert "APPLICATION" in svg
        assert "Shared DB" in svg

    def test_monolith_has_pulse_ring(self) -> None:
        svg = self._svg("monolith")
        assert "mono-ring" in svg

    def test_pipeline_has_multiple_stages(self) -> None:
        svg = self._svg("pipeline")
        assert "Data Pipeline" in svg
        # Default stage labels
        for label in ["Input", "Outpu"]:  # "Output" truncated to 5 chars
            assert label in svg

    def test_all_archetypes_have_background_rect(self) -> None:
        for arch in ArchPatternPosterGenerator.ALL_ARCHETYPES:
            svg = self._svg(arch)
            assert "#0a0a0f" in svg, f"{arch} missing dark background"

    def test_all_archetypes_have_animated_element(self) -> None:
        """Each archetype SVG must embed at least one animated CSS class."""
        animated_classes = {
            "layered": "dot-lyr",
            "event_driven": "dot-evt",
            "hexagonal": "dot-hex",
            "microservice": "dot-ms",
            "monolith": "mono-ring",
            "pipeline": "dot-pipe",
        }
        for arch, css_class in animated_classes.items():
            svg = ArchPatternPosterGenerator()._panel_svg(arch, [], w=280, h=200)
            assert css_class in svg, f"{arch}: expected CSS class '{css_class}' not found in SVG"

    def test_archetypes_produce_distinct_svgs(self) -> None:
        """No two archetypes should produce identical SVG content."""
        svgs = {arch: self._svg(arch) for arch in ArchPatternPosterGenerator.ALL_ARCHETYPES}
        unique = set(svgs.values())
        assert len(unique) == len(ArchPatternPosterGenerator.ALL_ARCHETYPES), (
            "Two or more archetypes produced identical SVG output"
        )


# ---------------------------------------------------------------------------
# DiagramGenerator integration
# ---------------------------------------------------------------------------


class TestDiagramGeneratorIntegration:
    """Verify DiagramGenerator routes pattern_card/html and pattern_comparison correctly."""

    def test_pattern_comparison_in_valid_types(self) -> None:
        assert "pattern_comparison" in DiagramGenerator.VALID_TYPES

    def test_pattern_card_html_format_allowed(self, tmp_path: Path) -> None:
        gen = DiagramGenerator()
        with (
            patch("docs_mcp.generators.diagrams.DiagramGenerator._generate_pattern_card") as mock,
        ):
            mock.return_value = MagicMock(
                diagram_type="pattern_card",
                format="html",
                content="<html/>",
                node_count=0,
                edge_count=0,
                degraded=False,
                scanned_dirs=[],
                skipped_count=0,
            )
            result = gen.generate(tmp_path, diagram_type="pattern_card", output_format="html")
        mock.assert_called_once_with(tmp_path, "html")

    def test_pattern_card_mermaid_still_works(self, tmp_path: Path) -> None:
        """Mermaid fallback path is not broken."""
        gen = DiagramGenerator()
        with (
            patch("docs_mcp.generators.diagrams.DiagramGenerator._generate_pattern_card") as mock,
        ):
            mock.return_value = MagicMock(
                diagram_type="pattern_card",
                format="mermaid",
                content="flowchart TD",
                node_count=0,
                edge_count=0,
                degraded=False,
                scanned_dirs=[],
                skipped_count=0,
            )
            result = gen.generate(tmp_path, diagram_type="pattern_card", output_format="mermaid")
        mock.assert_called_once_with(tmp_path, "mermaid")

    def test_pattern_comparison_dispatches_to_handler(self, tmp_path: Path) -> None:
        gen = DiagramGenerator()
        with (
            patch(
                "docs_mcp.generators.diagrams.DiagramGenerator._generate_pattern_comparison"
            ) as mock,
        ):
            mock.return_value = MagicMock(
                diagram_type="pattern_comparison",
                format="html",
                content="<html/>",
                node_count=6,
                edge_count=0,
                degraded=False,
                scanned_dirs=[],
                skipped_count=0,
            )
            gen.generate(tmp_path, diagram_type="pattern_comparison", output_format="html")
        mock.assert_called_once_with(tmp_path, "html")

    def test_pattern_comparison_non_html_returns_degraded(self, tmp_path: Path) -> None:
        gen = DiagramGenerator()
        result = gen.generate(tmp_path, diagram_type="pattern_comparison", output_format="mermaid")
        assert result.degraded is True
        assert result.content == ""

    def test_invalid_type_still_blocked(self, tmp_path: Path) -> None:
        gen = DiagramGenerator()
        result = gen.generate(tmp_path, diagram_type="not_a_type", output_format="mermaid")
        assert result.content == ""


# ---------------------------------------------------------------------------
# STORY-100.6 — Auto-select poster for small projects
# ---------------------------------------------------------------------------


class TestAutoPosterForSmallProjects:
    """dependency diagram auto-selects pattern_card when project is small."""

    def test_small_project_redirects_dependency_to_pattern_card(self, tmp_path: Path) -> None:
        gen = DiagramGenerator()
        fake_mm = MagicMock()
        # 5 nodes → below _POSTER_AUTO_THRESHOLD (15)
        fake_mm.module_tree = [MagicMock() for _ in range(5)]
        for i, node in enumerate(fake_mm.module_tree):
            node.name = f"pkg{i}"

        with (
            patch(
                "docs_mcp.analyzers.module_map.ModuleMapAnalyzer.analyze",
                return_value=fake_mm,
            ),
            patch(
                "docs_mcp.generators.diagrams.DiagramGenerator._generate_pattern_card"
            ) as mock_pc,
        ):
            mock_pc.return_value = MagicMock(
                diagram_type="pattern_card",
                format="mermaid",
                content="flowchart TD",
                node_count=5,
                edge_count=0,
                degraded=False,
                scanned_dirs=[],
                skipped_count=0,
                adr_link=None,
            )
            gen.generate(tmp_path, diagram_type="dependency", output_format="mermaid")

        mock_pc.assert_called_once()

    def test_large_project_keeps_dependency_diagram(self, tmp_path: Path) -> None:
        gen = DiagramGenerator()
        fake_mm = MagicMock()
        # 20 nodes → above threshold
        fake_mm.module_tree = [MagicMock() for _ in range(20)]
        for i, node in enumerate(fake_mm.module_tree):
            node.name = f"pkg{i}"

        with (
            patch(
                "docs_mcp.analyzers.module_map.ModuleMapAnalyzer.analyze",
                return_value=fake_mm,
            ),
            patch("docs_mcp.generators.diagrams.DiagramGenerator._generate_dependency") as mock_dep,
        ):
            mock_dep.return_value = MagicMock(
                diagram_type="dependency",
                format="mermaid",
                content="flowchart LR",
                node_count=20,
                edge_count=5,
                degraded=False,
                scanned_dirs=[],
                skipped_count=0,
                adr_link=None,
            )
            gen.generate(tmp_path, diagram_type="dependency", output_format="mermaid")

        mock_dep.assert_called_once()

    def test_auto_redirect_only_for_mermaid_and_html(self, tmp_path: Path) -> None:
        """d2/plantuml formats skip auto-redirect (only mermaid/html trigger it)."""
        gen = DiagramGenerator()
        with (
            patch("docs_mcp.generators.diagrams.DiagramGenerator._generate_dependency") as mock_dep,
        ):
            mock_dep.return_value = MagicMock(
                diagram_type="dependency",
                format="d2",
                content="",
                node_count=0,
                edge_count=0,
                degraded=False,
                scanned_dirs=[],
                skipped_count=0,
                adr_link=None,
            )
            gen.generate(tmp_path, diagram_type="dependency", output_format="d2")

        # d2 format → no auto-redirect → dependency handler called
        mock_dep.assert_called_once()


# ---------------------------------------------------------------------------
# STORY-100.7 — ADR cross-link from detected pattern
# ---------------------------------------------------------------------------


class TestAdrCrossLink:
    """_find_adr_for_archetype and wiring into DiagramResult."""

    def test_returns_none_when_no_adr_dirs(self, tmp_path: Path) -> None:
        gen = DiagramGenerator()
        result = gen._find_adr_for_archetype(tmp_path, "layered")
        assert result is None

    def test_finds_adr_in_docs_adr(self, tmp_path: Path) -> None:
        adr_dir = tmp_path / "docs" / "adr"
        adr_dir.mkdir(parents=True)
        adr_file = adr_dir / "0001-layered-architecture.md"
        adr_file.write_text("# ADR-0001\n\nWe adopt the layered pattern.\n")

        gen = DiagramGenerator()
        result = gen._find_adr_for_archetype(tmp_path, "layered")
        assert result == "docs/adr/0001-layered-architecture.md"

    def test_finds_adr_in_docs_decisions(self, tmp_path: Path) -> None:
        dec_dir = tmp_path / "docs" / "decisions"
        dec_dir.mkdir(parents=True)
        (dec_dir / "0002-event-driven.md").write_text("Use event_driven approach.\n")

        gen = DiagramGenerator()
        result = gen._find_adr_for_archetype(tmp_path, "event_driven")
        assert result == "docs/decisions/0002-event-driven.md"

    def test_returns_none_when_no_keyword_match(self, tmp_path: Path) -> None:
        adr_dir = tmp_path / "docs" / "adr"
        adr_dir.mkdir(parents=True)
        (adr_dir / "0001-something-else.md").write_text("Nothing about architecture here.\n")

        gen = DiagramGenerator()
        result = gen._find_adr_for_archetype(tmp_path, "hexagonal")
        assert result is None

    def test_mermaid_output_includes_adr_comment(self) -> None:
        gen = DiagramGenerator()
        result = _mock_result("layered", 0.9)
        output = gen._render_pattern_card_mermaid(result, [], adr_link="docs/adr/0001-layered.md")
        assert "%% ADR: docs/adr/0001-layered.md" in output

    def test_mermaid_output_no_comment_when_no_adr(self) -> None:
        gen = DiagramGenerator()
        result = _mock_result("layered", 0.9)
        output = gen._render_pattern_card_mermaid(result, [])
        assert "%% ADR:" not in output

    def test_generate_single_includes_adr_link_html(self) -> None:
        gen = ArchPatternPosterGenerator()
        html = gen.generate_single([], _mock_result("layered"), adr_link="docs/adr/0001.md")
        assert "docs/adr/0001.md" in html
        assert "adr-link" in html

    def test_generate_single_no_adr_section_when_none(self) -> None:
        gen = ArchPatternPosterGenerator()
        html = gen.generate_single([], _mock_result("layered"), adr_link=None)
        assert "adr-link" not in html

    def test_diagram_result_carries_adr_link(self) -> None:
        from docs_mcp.generators.diagrams import DiagramResult

        r = DiagramResult(
            diagram_type="pattern_card",
            format="mermaid",
            content="flowchart TD",
            adr_link="docs/adr/0001-layered.md",
        )
        assert r.adr_link == "docs/adr/0001-layered.md"

    def test_diagram_result_adr_link_defaults_none(self) -> None:
        from docs_mcp.generators.diagrams import DiagramResult

        r = DiagramResult(diagram_type="pattern_card", format="mermaid", content="")
        assert r.adr_link is None

    def test_generate_pattern_card_wires_adr_link(self, tmp_path: Path) -> None:
        """Full integration: _generate_pattern_card includes adr_link in result."""
        # Create a matching ADR
        adr_dir = tmp_path / "docs" / "adr"
        adr_dir.mkdir(parents=True)
        (adr_dir / "0001-layered.md").write_text("Adopt layered architecture.\n")

        gen = DiagramGenerator()
        mock_cls_result = _mock_result("layered", 0.85)
        mock_mm = MagicMock()
        mock_mm.module_tree = []
        mock_graph = MagicMock()
        mock_graph.most_imported = []

        with (
            patch("docs_mcp.analyzers.module_map.ModuleMapAnalyzer.analyze", return_value=mock_mm),
            patch(
                "docs_mcp.analyzers.dependency.ImportGraphBuilder.build", return_value=mock_graph
            ),
            patch(
                "docs_mcp.analyzers.pattern.PatternClassifier.classify",
                return_value=mock_cls_result,
            ),
        ):
            diagram = gen._generate_pattern_card(tmp_path, "mermaid")

        assert diagram.adr_link == "docs/adr/0001-layered.md"
        assert "%% ADR: docs/adr/0001-layered.md" in diagram.content

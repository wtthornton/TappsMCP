"""Tests for the interactive HTML viewer's motion layer (TAP-1037 + TAP-1039).

Covers the four ``motion`` values (``off``/``subtle``/``particles``/invalid)
crossed with the two diagram-type sets: flow-direction (dependency,
module_map, sequence, c4_container) and relationship-only (class_hierarchy,
er_diagram, c4_context). Also asserts that the ``@media print`` block
disables animations, ``prefers-reduced-motion`` gates motion CSS, and (for
TAP-1039) the JS particle layer is present only for ``motion="particles"``.
"""

from __future__ import annotations

from docs_mcp.generators.interactive_html import (
    _MOTION_DASHARRAY,
    _MOTION_DURATION_S,
    _PARTICLE_SPEED_UNITS_PER_S,
    _PARTICLES_PER_EDGE,
    InteractiveHtmlGenerator,
)

_FLOW_TYPES = ["dependency", "module_map", "sequence", "c4_container"]
_RELATIONSHIP_ONLY_TYPES = ["class_hierarchy", "er_diagram", "c4_context"]
_SAMPLE_DIAGRAM = [("Test Diagram", "graph TD\n  A --> B")]
_KEYFRAMES_NAME = "tapps-marching-ants"
_PARTICLE_SENTINEL = "tapps-particle"


def _animation_present(html: str) -> bool:
    return _KEYFRAMES_NAME in html


def _particle_js_present(html: str) -> bool:
    """Particle JS block is uniquely identified by its module-level constants
    being inlined into the script body."""
    return (
        _PARTICLE_SENTINEL in html
        and "getPointAtLength" in html
        and "requestAnimationFrame" in html
    )


# ---------------------------------------------------------------------------
# motion="subtle" — flow-direction diagrams
# ---------------------------------------------------------------------------


class TestMotionSubtleFlow:
    def test_subtle_emits_marching_ants_for_flow_types(self) -> None:
        gen = InteractiveHtmlGenerator()
        result = gen.generate(
            _SAMPLE_DIAGRAM,
            motion="subtle",
            diagram_types=_FLOW_TYPES,
        )
        assert _animation_present(result.content)
        assert "stroke-dashoffset" in result.content
        assert _MOTION_DASHARRAY in result.content
        assert f"{_MOTION_DURATION_S}s linear infinite" in result.content
        assert "prefers-reduced-motion: no-preference" in result.content
        assert ".edgePath path" in result.content
        assert ".flowchart-link" in result.content

    def test_subtle_default_emits_motion_when_no_types_passed(self) -> None:
        # With no diagram_types provided, the gate is disabled and motion
        # CSS is emitted when motion is enabled (default = "subtle").
        gen = InteractiveHtmlGenerator()
        result = gen.generate(_SAMPLE_DIAGRAM)
        assert _animation_present(result.content)


# ---------------------------------------------------------------------------
# motion="subtle" — relationship-only diagrams (gate suppresses CSS)
# ---------------------------------------------------------------------------


class TestMotionSubtleRelationshipOnly:
    def test_subtle_suppressed_for_relationship_only_types(self) -> None:
        gen = InteractiveHtmlGenerator()
        result = gen.generate(
            _SAMPLE_DIAGRAM,
            motion="subtle",
            diagram_types=_RELATIONSHIP_ONLY_TYPES,
        )
        assert not _animation_present(result.content)
        assert "stroke-dashoffset" not in result.content

    def test_subtle_emits_when_mixed_types_include_flow(self) -> None:
        gen = InteractiveHtmlGenerator()
        result = gen.generate(
            _SAMPLE_DIAGRAM,
            motion="subtle",
            diagram_types=["class_hierarchy", "dependency"],
        )
        assert _animation_present(result.content)


# ---------------------------------------------------------------------------
# motion="off" — never emits animation, regardless of types
# ---------------------------------------------------------------------------


class TestMotionOff:
    def test_off_for_flow_types_emits_no_animation(self) -> None:
        gen = InteractiveHtmlGenerator()
        result = gen.generate(
            _SAMPLE_DIAGRAM,
            motion="off",
            diagram_types=_FLOW_TYPES,
        )
        assert not _animation_present(result.content)
        assert "stroke-dashoffset" not in result.content

    def test_off_for_relationship_types_emits_no_animation(self) -> None:
        gen = InteractiveHtmlGenerator()
        result = gen.generate(
            _SAMPLE_DIAGRAM,
            motion="off",
            diagram_types=_RELATIONSHIP_ONLY_TYPES,
        )
        assert not _animation_present(result.content)


# ---------------------------------------------------------------------------
# motion="particles" — Phase 1 falls back to "subtle"
# ---------------------------------------------------------------------------


class TestMotionParticlesFallback:
    def test_particles_falls_back_to_subtle_for_flow_types(self) -> None:
        gen = InteractiveHtmlGenerator()
        result = gen.generate(
            _SAMPLE_DIAGRAM,
            motion="particles",
            diagram_types=_FLOW_TYPES,
        )
        assert _animation_present(result.content)

    def test_particles_respects_relationship_only_gate(self) -> None:
        gen = InteractiveHtmlGenerator()
        result = gen.generate(
            _SAMPLE_DIAGRAM,
            motion="particles",
            diagram_types=_RELATIONSHIP_ONLY_TYPES,
        )
        assert not _animation_present(result.content)


# ---------------------------------------------------------------------------
# Invalid motion value — defensively treated as "off"
# ---------------------------------------------------------------------------


class TestMotionInvalid:
    def test_invalid_value_emits_no_animation_for_flow(self) -> None:
        gen = InteractiveHtmlGenerator()
        result = gen.generate(
            _SAMPLE_DIAGRAM,
            motion="bogus",
            diagram_types=_FLOW_TYPES,
        )
        assert not _animation_present(result.content)

    def test_invalid_value_emits_no_animation_for_relationship(self) -> None:
        gen = InteractiveHtmlGenerator()
        result = gen.generate(
            _SAMPLE_DIAGRAM,
            motion="bogus",
            diagram_types=_RELATIONSHIP_ONLY_TYPES,
        )
        assert not _animation_present(result.content)


# ---------------------------------------------------------------------------
# Print-media disable hook
# ---------------------------------------------------------------------------


class TestPrintDisablesAnimation:
    def test_print_block_disables_animation(self) -> None:
        gen = InteractiveHtmlGenerator()
        result = gen.generate(
            _SAMPLE_DIAGRAM,
            motion="subtle",
            diagram_types=_FLOW_TYPES,
        )
        # Print block is in _VIEWER_CSS regardless of motion. Find it and
        # assert the animation-disable selectors live inside it.
        print_idx = result.content.find("@media print")
        assert print_idx != -1
        # Closing brace of the @media print block (first '}' after the
        # opening '{' that follows '@media print', at nesting depth 0
        # relative to the rule's body).
        body_start = result.content.find("{", print_idx)
        depth = 0
        end = -1
        for i in range(body_start, len(result.content)):
            ch = result.content[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        assert end > body_start
        block = result.content[body_start:end]
        assert "animation: none" in block
        assert ".edgePath path" in block
        assert ".flowchart-link" in block


# ---------------------------------------------------------------------------
# Determinism — emitted CSS is byte-identical across calls
# ---------------------------------------------------------------------------


class TestMotionDeterminism:
    def test_two_runs_produce_identical_motion_css(self) -> None:
        gen = InteractiveHtmlGenerator()
        a = gen.generate(
            _SAMPLE_DIAGRAM,
            motion="subtle",
            diagram_types=_FLOW_TYPES,
        )
        b = gen.generate(
            _SAMPLE_DIAGRAM,
            motion="subtle",
            diagram_types=_FLOW_TYPES,
        )
        assert a.content == b.content


# ---------------------------------------------------------------------------
# Particle JS layer (TAP-1039) — opt-in for motion="particles"
# ---------------------------------------------------------------------------


class TestParticleJsLayer:
    """Particle JS is present only for ``motion="particles"``."""

    def test_particles_emits_particle_js_for_flow_types(self) -> None:
        gen = InteractiveHtmlGenerator()
        result = gen.generate(
            _SAMPLE_DIAGRAM,
            motion="particles",
            diagram_types=_FLOW_TYPES,
        )
        assert _particle_js_present(result.content)
        # CSS marching-ants is also still emitted (particles is additive).
        assert _animation_present(result.content)

    def test_subtle_emits_no_particle_js(self) -> None:
        gen = InteractiveHtmlGenerator()
        result = gen.generate(
            _SAMPLE_DIAGRAM,
            motion="subtle",
            diagram_types=_FLOW_TYPES,
        )
        assert not _particle_js_present(result.content)

    def test_off_emits_no_particle_js(self) -> None:
        gen = InteractiveHtmlGenerator()
        result = gen.generate(
            _SAMPLE_DIAGRAM,
            motion="off",
            diagram_types=_FLOW_TYPES,
        )
        assert not _particle_js_present(result.content)

    def test_invalid_motion_emits_no_particle_js(self) -> None:
        gen = InteractiveHtmlGenerator()
        result = gen.generate(
            _SAMPLE_DIAGRAM,
            motion="bogus",
            diagram_types=_FLOW_TYPES,
        )
        assert not _particle_js_present(result.content)

    def test_particles_suppressed_for_relationship_only_types(self) -> None:
        gen = InteractiveHtmlGenerator()
        result = gen.generate(
            _SAMPLE_DIAGRAM,
            motion="particles",
            diagram_types=_RELATIONSHIP_ONLY_TYPES,
        )
        # No CSS animation AND no particle JS for relationship-only diagrams.
        assert not _animation_present(result.content)
        assert not _particle_js_present(result.content)

    def test_particles_per_edge_constant_inlined(self) -> None:
        gen = InteractiveHtmlGenerator()
        result = gen.generate(
            _SAMPLE_DIAGRAM,
            motion="particles",
            diagram_types=_FLOW_TYPES,
        )
        assert _PARTICLES_PER_EDGE == 3
        assert f"const PARTICLES_PER_EDGE = {_PARTICLES_PER_EDGE};" in result.content

    def test_particle_speed_constant_inlined(self) -> None:
        gen = InteractiveHtmlGenerator()
        result = gen.generate(
            _SAMPLE_DIAGRAM,
            motion="particles",
            diagram_types=_FLOW_TYPES,
        )
        assert f"const PARTICLE_SPEED = {_PARTICLE_SPEED_UNITS_PER_S};" in result.content

    def test_particle_js_skips_under_reduced_motion(self) -> None:
        gen = InteractiveHtmlGenerator()
        result = gen.generate(
            _SAMPLE_DIAGRAM,
            motion="particles",
            diagram_types=_FLOW_TYPES,
        )
        # The IIFE early-returns if matchMedia('(prefers-reduced-motion: reduce)') matches.
        assert "prefers-reduced-motion: reduce" in result.content
        assert "matchMedia" in result.content

    def test_particle_js_uses_mutation_observer(self) -> None:
        gen = InteractiveHtmlGenerator()
        result = gen.generate(
            _SAMPLE_DIAGRAM,
            motion="particles",
            diagram_types=_FLOW_TYPES,
        )
        # Mermaid re-render hook: MutationObserver on each .diagram-wrapper.
        assert "MutationObserver" in result.content
        assert ".diagram-wrapper" in result.content

    def test_particle_js_no_random_or_clock_seeds(self) -> None:
        gen = InteractiveHtmlGenerator()
        result = gen.generate(
            _SAMPLE_DIAGRAM,
            motion="particles",
            diagram_types=_FLOW_TYPES,
        )
        # Determinism guard: no Math.random / Date.now / performance.now()
        # used as a seed in the particle JS body. (They may legitimately
        # appear elsewhere in the page; we look only inside the IIFE.)
        idx = result.content.find("(function() {")
        assert idx != -1
        end = result.content.find("})();", idx)
        assert end != -1
        body = result.content[idx:end]
        assert "Math.random" not in body
        assert "Date.now" not in body
        assert "performance.now" not in body

    def test_particles_two_runs_produce_identical_html(self) -> None:
        gen = InteractiveHtmlGenerator()
        a = gen.generate(
            _SAMPLE_DIAGRAM,
            motion="particles",
            diagram_types=_FLOW_TYPES,
        )
        b = gen.generate(
            _SAMPLE_DIAGRAM,
            motion="particles",
            diagram_types=_FLOW_TYPES,
        )
        assert a.content == b.content

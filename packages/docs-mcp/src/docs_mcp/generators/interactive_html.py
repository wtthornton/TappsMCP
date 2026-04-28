"""Interactive HTML diagram renderer using Mermaid.js (Epic 81.3).

Wraps Mermaid diagram content in a self-contained HTML file with
interactive pan/zoom controls via Mermaid.js and panzoom.js.
"""

from __future__ import annotations

from typing import ClassVar

import structlog
from pydantic import BaseModel

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class InteractiveHtmlResult(BaseModel):
    """Result of interactive HTML generation."""

    content: str
    diagram_count: int
    title: str


# Mermaid.js CDN URL (pinned version for stability)
_MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs"

# Motion configuration (deterministic — never derived from time/random/env).
_VALID_MOTION_VALUES: frozenset[str] = frozenset({"off", "subtle", "particles"})
_MOTION_DURATION_S: float = 1.2
_MOTION_DASHARRAY: str = "4 8"
_MOTION_DASHOFFSET_END: int = -12

# Particle-layer constants for motion="particles". All values are deterministic
# module-level constants — never derive from `Date.now()`, `Math.random()`,
# or any wall-clock value. Particle phase is staggered by index, not random.
_PARTICLES_PER_EDGE: int = 3
_PARTICLE_SPEED_UNITS_PER_S: float = 60.0
_PARTICLE_RADIUS: int = 2
_PARTICLE_FILL: str = "#fafafa"
_PARTICLE_CLASS: str = "tapps-particle"

# Diagram-type gating: motion is only meaningful for flow-direction diagrams.
_FLOW_DIAGRAM_TYPES: frozenset[str] = frozenset(
    {"dependency", "module_map", "sequence", "c4_container"}
)
_RELATIONSHIP_ONLY_TYPES: frozenset[str] = frozenset(
    {"class_hierarchy", "er_diagram", "c4_context"}
)

# Marching-ants CSS injected when motion is enabled. The animation is wrapped
# in `@media (prefers-reduced-motion: no-preference)` so users with reduced-
# motion preferences see a static diagram. Module-level constants keep the
# CSS deterministic — never derive duration/dasharray from time or env.
_MOTION_CSS = f"""\
@media (prefers-reduced-motion: no-preference) {{
    .edgePath path, .flowchart-link {{
        stroke-dasharray: {_MOTION_DASHARRAY};
        animation: tapps-marching-ants {_MOTION_DURATION_S}s linear infinite;
    }}
}}
@keyframes tapps-marching-ants {{
    to {{ stroke-dashoffset: {_MOTION_DASHOFFSET_END}; }}
}}
"""

# Inline CSS for the interactive viewer
_VIEWER_CSS = """\
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #f8f9fa; color: #1a1a2e;
}
.header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white; padding: 2rem; text-align: center;
}
.header h1 { font-size: 1.8rem; margin-bottom: 0.5rem; }
.header p { opacity: 0.9; font-size: 1rem; }
.controls {
    display: flex; gap: 1rem; padding: 1rem 2rem;
    background: white; border-bottom: 1px solid #e0e0e0;
    flex-wrap: wrap; align-items: center;
}
.controls button {
    padding: 0.5rem 1rem; border: 1px solid #ddd; border-radius: 6px;
    background: white; cursor: pointer; font-size: 0.9rem;
    transition: all 0.2s;
}
.controls button:hover { background: #f0f0f0; border-color: #999; }
.controls button.active { background: #667eea; color: white; border-color: #667eea; }
.toc {
    padding: 1rem 2rem; background: white; border-bottom: 1px solid #e0e0e0;
}
.toc h3 { font-size: 1rem; margin-bottom: 0.5rem; }
.toc a {
    display: inline-block; margin: 0.25rem 0.5rem; color: #667eea;
    text-decoration: none; font-size: 0.9rem;
}
.toc a:hover { text-decoration: underline; }
.diagram-section {
    margin: 2rem; background: white; border-radius: 12px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08); overflow: hidden;
}
.diagram-section h2 {
    padding: 1rem 1.5rem; background: #f8f9fa;
    border-bottom: 1px solid #e0e0e0; font-size: 1.2rem;
}
.diagram-wrapper {
    padding: 2rem; overflow: auto; min-height: 200px;
    cursor: grab; position: relative;
}
.diagram-wrapper:active { cursor: grabbing; }
.diagram-wrapper .mermaid { display: flex; justify-content: center; }
@media print {
    .controls, .toc { display: none; }
    .diagram-section { break-inside: avoid; box-shadow: none; }
    .edgePath path, .flowchart-link {
        animation: none !important;
        stroke-dasharray: none !important;
    }
}
"""

# JavaScript for zoom/pan and toggle controls
_VIEWER_JS = """\
// Initialize Mermaid
import mermaid from '%(mermaid_cdn)s';
mermaid.initialize({
    startOnLoad: true,
    theme: 'default',
    securityLevel: 'loose',
    flowchart: { useMaxWidth: true },
});

// Toggle diagram visibility
document.querySelectorAll('.toggle-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const targetId = btn.dataset.target;
        const section = document.getElementById(targetId);
        if (section) {
            const isHidden = section.style.display === 'none';
            section.style.display = isHidden ? 'block' : 'none';
            btn.classList.toggle('active', isHidden);
        }
    });
});

// Zoom controls
let scale = 1;
document.getElementById('zoom-in')?.addEventListener('click', () => {
    scale = Math.min(scale * 1.2, 5);
    document.querySelectorAll('.diagram-wrapper .mermaid svg').forEach(svg => {
        svg.style.transform = `scale(${scale})`;
        svg.style.transformOrigin = 'center top';
    });
});
document.getElementById('zoom-out')?.addEventListener('click', () => {
    scale = Math.max(scale / 1.2, 0.2);
    document.querySelectorAll('.diagram-wrapper .mermaid svg').forEach(svg => {
        svg.style.transform = `scale(${scale})`;
        svg.style.transformOrigin = 'center top';
    });
});
document.getElementById('zoom-reset')?.addEventListener('click', () => {
    scale = 1;
    document.querySelectorAll('.diagram-wrapper .mermaid svg').forEach(svg => {
        svg.style.transform = 'scale(1)';
    });
});
"""

# Opt-in JS particle layer for motion="particles". Walks every Mermaid
# `.edgePath path` element after render, calls `getTotalLength()`, then
# spawns N=`_PARTICLES_PER_EDGE` particles per edge that advance via
# `requestAnimationFrame`. Skipped entirely when the user prefers reduced
# motion. A `MutationObserver` on each diagram wrapper re-spawns particles
# when Mermaid re-renders the SVG. All speed/count values are constants.
_PARTICLE_JS = (
    "(function() {\n"
    "    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {\n"
    "        return;\n"
    "    }\n"
    f"    const PARTICLES_PER_EDGE = {_PARTICLES_PER_EDGE};\n"
    f"    const PARTICLE_SPEED = {_PARTICLE_SPEED_UNITS_PER_S};\n"
    f"    const PARTICLE_RADIUS = {_PARTICLE_RADIUS};\n"
    f"    const PARTICLE_FILL = '{_PARTICLE_FILL}';\n"
    f"    const PARTICLE_CLASS = '{_PARTICLE_CLASS}';\n"
    "    const SVG_NS = 'http://www.w3.org/2000/svg';\n"
    "    function spawnParticles(svg) {\n"
    "        svg.querySelectorAll('.' + PARTICLE_CLASS).forEach(p => p.remove());\n"
    "        const edges = svg.querySelectorAll('.edgePath path, .flowchart-link');\n"
    "        const states = [];\n"
    "        edges.forEach(path => {\n"
    "            let length;\n"
    "            try { length = path.getTotalLength(); } catch (e) { return; }\n"
    "            if (!length) return;\n"
    "            for (let i = 0; i < PARTICLES_PER_EDGE; i++) {\n"
    "                const c = document.createElementNS(SVG_NS, 'circle');\n"
    "                c.setAttribute('r', PARTICLE_RADIUS);\n"
    "                c.setAttribute('fill', PARTICLE_FILL);\n"
    "                c.classList.add(PARTICLE_CLASS);\n"
    "                path.parentNode.appendChild(c);\n"
    "                states.push({\n"
    "                    circle: c,\n"
    "                    path: path,\n"
    "                    length: length,\n"
    "                    phase: i / PARTICLES_PER_EDGE,\n"
    "                });\n"
    "            }\n"
    "        });\n"
    "        if (states.length === 0) return;\n"
    "        let last = null;\n"
    "        function step(now) {\n"
    "            if (last === null) { last = now; }\n"
    "            const dt = (now - last) / 1000;\n"
    "            last = now;\n"
    "            states.forEach(s => {\n"
    "                s.phase = (s.phase + dt * PARTICLE_SPEED / s.length) % 1;\n"
    "                const pt = s.path.getPointAtLength(s.phase * s.length);\n"
    "                s.circle.setAttribute('cx', pt.x);\n"
    "                s.circle.setAttribute('cy', pt.y);\n"
    "            });\n"
    "            requestAnimationFrame(step);\n"
    "        }\n"
    "        requestAnimationFrame(step);\n"
    "    }\n"
    "    document.querySelectorAll('.diagram-wrapper').forEach(wrapper => {\n"
    "        const svg = wrapper.querySelector('svg');\n"
    "        if (svg) { spawnParticles(svg); }\n"
    "        const observer = new MutationObserver(() => {\n"
    "            const newSvg = wrapper.querySelector('svg');\n"
    "            if (newSvg) { spawnParticles(newSvg); }\n"
    "        });\n"
    "        observer.observe(wrapper, { childList: true, subtree: true });\n"
    "    });\n"
    "})();\n"
)


class InteractiveHtmlGenerator:
    """Generates self-contained interactive HTML with Mermaid.js diagrams.

    Takes one or more Mermaid diagram strings and wraps them in an
    interactive HTML page with pan/zoom controls, diagram toggling,
    and a table of contents.
    """

    VALID_THEMES: ClassVar[frozenset[str]] = frozenset(
        {
            "default",
            "dark",
            "forest",
            "neutral",
        }
    )

    def generate(
        self,
        diagrams: list[tuple[str, str]],
        *,
        title: str = "Architecture Diagrams",
        subtitle: str = "",
        theme: str = "default",
        motion: str = "subtle",
        diagram_types: list[str] | None = None,
    ) -> InteractiveHtmlResult:
        """Generate interactive HTML from Mermaid diagrams.

        Args:
            diagrams: List of (section_title, mermaid_content) tuples.
            title: Page title.
            subtitle: Page subtitle.
            theme: Mermaid theme (default, dark, forest, neutral).
            motion: Motion intensity for edge animations.
                ``"off"`` emits no animation CSS or JS. ``"subtle"`` (default)
                adds a CSS marching-ants effect on Mermaid edge paths via
                ``stroke-dashoffset``. ``"particles"`` keeps the marching-ants
                CSS and additionally injects a JS particle layer that walks
                each ``.edgePath path``, calls ``getTotalLength()``, and
                advances ``_PARTICLES_PER_EDGE`` particles per edge via
                ``requestAnimationFrame``. The particle setup is skipped
                entirely when the browser reports
                ``prefers-reduced-motion: reduce``.
            diagram_types: Optional list of canonical diagram-type identifiers
                (e.g. ``"dependency"``, ``"class_hierarchy"``) used to gate
                motion. When every requested type is relationship-only
                (``class_hierarchy``, ``er_diagram``, ``c4_context``), motion
                CSS is suppressed entirely. ``None`` disables the gate.

        Returns:
            InteractiveHtmlResult with the self-contained HTML.
        """
        if theme not in self.VALID_THEMES:
            theme = "default"

        if not diagrams:
            return InteractiveHtmlResult(
                content="<html><body><p>No diagrams to display.</p></body></html>",
                diagram_count=0,
                title=title,
            )

        motion_css = _resolve_motion_css(motion, diagram_types)
        particle_js = _resolve_particle_js(motion, diagram_types)

        parts: list[str] = []

        # HTML head
        parts.append("<!DOCTYPE html>")
        parts.append('<html lang="en">')
        parts.append("<head>")
        parts.append(f"<title>{_escape(title)}</title>")
        parts.append('<meta charset="utf-8">')
        parts.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
        parts.append(f"<style>{_VIEWER_CSS}{motion_css}</style>")
        parts.append("</head>")
        parts.append("<body>")

        # Header
        parts.append('<div class="header">')
        parts.append(f"<h1>{_escape(title)}</h1>")
        if subtitle:
            parts.append(f"<p>{_escape(subtitle)}</p>")
        parts.append("</div>")

        # Controls
        parts.append('<div class="controls">')
        parts.append('<button id="zoom-in">Zoom In (+)</button>')
        parts.append('<button id="zoom-out">Zoom Out (-)</button>')
        parts.append('<button id="zoom-reset">Reset</button>')
        parts.append('<span style="margin-left: 1rem; color: #666;">Toggle:</span>')
        for i, (section_title, _) in enumerate(diagrams):
            section_id = f"diagram-{i}"
            parts.append(
                f'<button class="toggle-btn active" data-target="{section_id}">'
                f"{_escape(section_title)}</button>"
            )
        parts.append("</div>")

        # Table of contents
        parts.append('<div class="toc">')
        parts.append("<h3>Diagrams</h3>")
        for i, (section_title, _) in enumerate(diagrams):
            parts.append(f'<a href="#diagram-{i}">{_escape(section_title)}</a>')
        parts.append("</div>")

        # Diagram sections
        for i, (section_title, mermaid_content) in enumerate(diagrams):
            section_id = f"diagram-{i}"
            parts.append(f'<div class="diagram-section" id="{section_id}">')
            parts.append(f"<h2>{_escape(section_title)}</h2>")
            parts.append('<div class="diagram-wrapper">')
            parts.append(f'<pre class="mermaid">\n{_escape(mermaid_content)}\n</pre>')
            parts.append("</div>")
            parts.append("</div>")

        # JavaScript (module script for Mermaid ESM)
        js = _VIEWER_JS % {"mermaid_cdn": _MERMAID_CDN}
        parts.append(f'<script type="module">{js}</script>')

        # Opt-in particle layer for motion="particles". Plain script (no
        # imports) so it runs in any browser; the IIFE handles its own
        # reduced-motion gate.
        if particle_js:
            parts.append(f"<script>{particle_js}</script>")

        parts.append("</body>")
        parts.append("</html>")

        content = "\n".join(parts)

        return InteractiveHtmlResult(
            content=content,
            diagram_count=len(diagrams),
            title=title,
        )


def _escape(text: str) -> str:
    """HTML-escape text for safe embedding."""
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _resolve_motion_css(motion: str, diagram_types: list[str] | None) -> str:
    """Resolve which motion CSS block (if any) to inject into the page.

    Returns the marching-ants CSS block when motion is enabled and at least
    one requested diagram type carries direction-of-flow. Returns ``""``
    when motion is off, the value is unrecognized, or every requested type
    is relationship-only.
    """
    if motion not in _VALID_MOTION_VALUES or motion == "off":
        return ""
    if diagram_types is not None:
        requested = {dt.strip() for dt in diagram_types if dt.strip()}
        if requested and not (requested & _FLOW_DIAGRAM_TYPES):
            return ""
    return _MOTION_CSS


def _resolve_particle_js(motion: str, diagram_types: list[str] | None) -> str:
    """Return the particle-layer JS when ``motion == "particles"``.

    Returns ``""`` for any other motion value, or when every requested
    diagram type is relationship-only (gating mirrors ``_resolve_motion_css``
    so the JS never runs on a page that has no flow edges to trace).
    """
    if motion != "particles":
        return ""
    if diagram_types is not None:
        requested = {dt.strip() for dt in diagram_types if dt.strip()}
        if requested and not (requested & _FLOW_DIAGRAM_TYPES):
            return ""
    return _PARTICLE_JS

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
    ) -> InteractiveHtmlResult:
        """Generate interactive HTML from Mermaid diagrams.

        Args:
            diagrams: List of (section_title, mermaid_content) tuples.
            title: Page title.
            subtitle: Page subtitle.
            theme: Mermaid theme (default, dark, forest, neutral).

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

        parts: list[str] = []

        # HTML head
        parts.append("<!DOCTYPE html>")
        parts.append('<html lang="en">')
        parts.append("<head>")
        parts.append(f"<title>{_escape(title)}</title>")
        parts.append('<meta charset="utf-8">')
        parts.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
        parts.append(f"<style>{_VIEWER_CSS}</style>")
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

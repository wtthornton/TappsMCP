"""Architecture pattern poster generator (STORY-100.8 / 100.9 / 100.10).

Produces self-contained HTML pages with animated SVG topology diagrams for
each of the six architectural archetypes.  Each archetype is rendered using
its *canonical structural shape* — not a generic node chain:

* ``layered``       — full-width horizontal bands stacked top-to-bottom
* ``event_driven``  — central EventBus, publishers left, consumers right
* ``hexagonal``     — domain hexagon at centre, adapter ring around it
* ``microservice``  — isolated service boxes each with their own datastore
* ``monolith``      — single large container enclosing all module nodes
* ``pipeline``      — left-to-right sequential stages with flow arrows

Animations use CSS ``@keyframes`` (not SVG SMIL) so they respect the
``prefers-reduced-motion`` media feature without JavaScript.

Public API
----------
``generate_single(packages, archetype_result)``
    One-panel HTML page for the detected archetype.

``generate_comparison(detected_archetype)``
    2×3 HTML page showing all six archetypes side-by-side (the poster view).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, ClassVar

import structlog

if TYPE_CHECKING:
    from docs_mcp.analyzers.pattern import ArchetypeResult

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Palette — mirrors diagrams.py _ROLE_COLORS so every visual speaks the same
# language.  Do NOT import from diagrams.py to avoid circular imports.
# ---------------------------------------------------------------------------

_ROLE_COLORS: dict[str, str] = {
    "presentation": "#F5A9D0",
    "business": "#14B8A6",
    "data": "#9333EA",
    "infra": "#6B7280",
}
_ROLE_TEXT: dict[str, str] = {
    "presentation": "#111",
    "business": "#fff",
    "data": "#fff",
    "infra": "#fff",
}
_ROLE_LABELS: dict[str, str] = {
    "presentation": "Presentation",
    "business": "Business / App",
    "data": "Data Access",
    "infra": "Persistence / Infra",
}

# Ordered list used by the comparison grid (2 columns × 3 rows).
_GRID_ORDER: list[str] = [
    "event_driven",
    "layered",
    "monolith",
    "microservice",
    "pipeline",
    "hexagonal",
]

_ARCHETYPE_LABELS: dict[str, str] = {
    "event_driven": "EVENT DRIVEN",
    "layered": "LAYERED",
    "monolith": "MONOLITH",
    "microservice": "MICROSERVICE",
    "pipeline": "PIPELINE",
    "hexagonal": "HEXAGONAL",
    "unknown": "UNKNOWN",
}

# Badge colours per archetype.
_BADGE_BG: dict[str, str] = {
    "layered": "#14B8A6",
    "event_driven": "#14B8A6",
    "hexagonal": "#0d9488",
    "microservice": "#d4a847",
    "monolith": "#6B7280",
    "pipeline": "#9333EA",
    "unknown": "#374151",
}
_BADGE_FG: dict[str, str] = {
    "layered": "#fff",
    "event_driven": "#fff",
    "hexagonal": "#fff",
    "microservice": "#111",
    "monolith": "#fff",
    "pipeline": "#fff",
    "unknown": "#fff",
}

# ---------------------------------------------------------------------------
# SVG panel constants
# ---------------------------------------------------------------------------

_W = 280  # panel width (SVG units)
_H = 200  # panel height (SVG units)


class ArchPatternPosterGenerator:
    """Generates animated SVG topology diagrams for architectural archetypes.

    Each archetype panel is a ``_W × _H`` SVG with a dark background and a
    CSS ``@keyframes`` animation showing canonical data flow.
    """

    # Exposed for tests.
    PANEL_W: ClassVar[int] = _W
    PANEL_H: ClassVar[int] = _H
    ALL_ARCHETYPES: ClassVar[list[str]] = list(_GRID_ORDER)

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def generate_single(
        self,
        packages: list[tuple[str, str]],
        archetype_result: ArchetypeResult,
        adr_link: str | None = None,
    ) -> str:
        """Return a self-contained HTML page for *archetype_result*."""
        arch = str(archetype_result.archetype)
        label = _ARCHETYPE_LABELS.get(arch, arch.upper())
        pct = f"{archetype_result.confidence * 100:.0f}%"
        svg = self._panel_svg(arch, packages, w=600, h=430)
        badge_bg = _BADGE_BG.get(arch, "#374151")
        badge_fg = _BADGE_FG.get(arch, "#fff")
        adr_html = (
            f'  <p class="adr-link">See ADR: <a href="{adr_link}">{adr_link}</a></p>'
            if adr_link
            else ""
        )
        body = f"""
<div class="poster-single">
  <div class="poster-header">
    <span class="arch-badge" style="background:{badge_bg};color:{badge_fg}">{label}</span>
    <span class="confidence">{pct} confidence</span>
  </div>
  {svg}
  {self._legend_html()}
{adr_html}
</div>"""
        return self._html_page(title=f"{label} Architecture", body=body, detected=arch)

    def generate_comparison(self, detected_archetype: str = "") -> str:
        """Return a self-contained HTML page with all six archetypes in a 2×3 grid."""
        panels: list[str] = []
        for arch in _GRID_ORDER:
            label = _ARCHETYPE_LABELS.get(arch, arch.upper())
            cls = "panel highlighted" if arch == detected_archetype else "panel"
            svg = self._panel_svg(arch, [], w=_W, h=_H)
            panels.append(
                f'<div class="{cls}" data-arch="{arch}">'
                f'<div class="panel-title">{label}</div>'
                f"{svg}"
                f"</div>"
            )
        grid = "\n".join(panels)
        body = f"""
<div class="poster-comparison">
  <div class="poster-banner">
    <span class="site-tag">docs-mcp</span>
    <h1>SOFTWARE ARCHITECTURAL <span class="accent">PATTERNS</span></h1>
  </div>
  <div class="pattern-grid">{grid}</div>
  {self._legend_html()}
</div>"""
        return self._html_page(
            title="Software Architectural Patterns",
            body=body,
            detected=detected_archetype,
        )

    # ------------------------------------------------------------------
    # SVG panel
    # ------------------------------------------------------------------

    def _panel_svg(
        self,
        archetype: str,
        packages: list[tuple[str, str]],
        *,
        w: int = _W,
        h: int = _H,
    ) -> str:
        """Return an inline ``<svg>`` element for one archetype panel."""
        dispatch = {
            "layered": self._svg_layered,
            "event_driven": self._svg_event_driven,
            "hexagonal": self._svg_hexagonal,
            "microservice": self._svg_microservice,
            "monolith": self._svg_monolith,
            "pipeline": self._svg_pipeline,
        }
        renderer = dispatch.get(archetype, self._svg_layered)
        inner = renderer(packages)
        label = _ARCHETYPE_LABELS.get(archetype, archetype)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg"'
            f' viewBox="0 0 {_W} {_H}"'
            f' width="{w}" height="{h}"'
            f' class="pattern-svg"'
            f' aria-label="{label} architecture diagram">'
            f"<defs>{_DEFS}</defs>"
            f"{inner}"
            f"</svg>"
        )

    # ------------------------------------------------------------------
    # SVG topology renderers
    # ------------------------------------------------------------------

    def _svg_layered(self, packages: list[tuple[str, str]]) -> str:
        """Four horizontal bands stacked top-to-bottom."""
        bands = [
            ("presentation", "Presentation", "#F5A9D0", "#111"),
            ("business", "Business / Application", "#14B8A6", "#fff"),
            ("data", "Data Access", "#9333EA", "#fff"),
            ("infra", "Persistence / Infra", "#6B7280", "#fff"),
        ]
        role_pkgs: dict[str, list[str]] = {b[0]: [] for b in bands}
        for name, role in packages:
            role_pkgs.setdefault(role, []).append(name)

        band_h, gap, x0, bw = 38, 6, 12, 256
        y0 = 12
        lines: list[str] = [f'<rect width="{_W}" height="{_H}" rx="10" fill="#0a0a0f"/>']

        for i, (role, label, color, tc) in enumerate(bands):
            y = y0 + i * (band_h + gap)
            lines.append(
                f'<rect x="{x0}" y="{y}" width="{bw}" height="{band_h}"'
                f' rx="6" fill="{color}" opacity="0.92" filter="url(#pp-shadow)"/>'
            )
            lines.append(
                f'<text x="{x0 + 10}" y="{y + 14}" fill="{tc}"'
                f' font-size="9" font-weight="700" font-family="system-ui,sans-serif">'
                f"{label}</text>"
            )
            for j, pkg in enumerate(role_pkgs.get(role, [])[:4]):
                cx2 = x0 + 12 + j * 58
                cy2 = y + 26
                short = (pkg[:7] + "\u2026") if len(pkg) > 7 else pkg
                lines.append(
                    f'<rect x="{cx2}" y="{cy2 - 8}" width="54" height="14"'
                    f' rx="3" fill="rgba(0,0,0,0.25)"/>'
                )
                lines.append(
                    f'<text x="{cx2 + 27}" y="{cy2 + 2}" fill="{tc}"'
                    f' font-size="7" text-anchor="middle"'
                    f' font-family="system-ui,sans-serif">{short}</text>'
                )
            if i < len(bands) - 1:
                ax = x0 + bw // 2
                ay = y + band_h
                lines.append(
                    f'<line x1="{ax}" y1="{ay}" x2="{ax}" y2="{ay + gap}"'
                    f' stroke="#a1a1aa" stroke-width="1.5" marker-end="url(#pp-arr)"/>'
                )

        # Animated dot (positioned at origin; CSS moves it)
        lines.append('<circle class="flow-dot dot-lyr" r="4" fill="#fff"/>')
        return "\n".join(lines)

    def _svg_event_driven(self, packages: list[tuple[str, str]]) -> str:
        """Central EventBus, publishers left, consumers right."""
        lines: list[str] = [f'<rect width="{_W}" height="{_H}" rx="10" fill="#0a0a0f"/>']

        # Bus (centre)
        bx, by, bw2, bh = 103, 75, 74, 50
        bcx = bx + bw2 // 2
        bcy = by + bh // 2
        lines.append(
            f'<rect x="{bx}" y="{by}" width="{bw2}" height="{bh}"'
            f' rx="8" fill="#14B8A6" filter="url(#pp-shadow)"/>'
        )
        lines.append(
            f'<text x="{bcx}" y="{bcy - 5}" fill="#fff" font-size="9"'
            f' font-weight="700" text-anchor="middle" font-family="system-ui,sans-serif">'
            f"Event</text>"
        )
        lines.append(
            f'<text x="{bcx}" y="{bcy + 7}" fill="#fff" font-size="9"'
            f' font-weight="700" text-anchor="middle" font-family="system-ui,sans-serif">'
            f"Bus</text>"
        )

        pub_positions = [(14, 55), (14, 95), (14, 135)]
        pub_labels = [
            (packages[0][0] if len(packages) > 0 else "Publisher"),
            (packages[1][0] if len(packages) > 1 else "Publisher"),
            "Publisher",
        ]
        pw, ph = 54, 22
        for (px, py), lbl in zip(pub_positions, pub_labels, strict=True):
            short = (lbl[:9] + "\u2026") if len(lbl) > 9 else lbl
            lines.append(
                f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}"'
                f' rx="5" fill="#F5A9D0" filter="url(#pp-shadow)"/>'
            )
            lines.append(
                f'<text x="{px + pw // 2}" y="{py + 14}" fill="#111"'
                f' font-size="7.5" text-anchor="middle"'
                f' font-family="system-ui,sans-serif">{short}</text>'
            )
            lines.append(
                f'<line x1="{px + pw}" y1="{py + ph // 2}"'
                f' x2="{bx}" y2="{bcy}"'
                f' stroke="#a1a1aa" stroke-width="1.2" marker-end="url(#pp-arr)"/>'
            )

        cons_positions = [(212, 55), (212, 95), (212, 135)]
        cons_labels = [
            (packages[2][0] if len(packages) > 2 else "Consumer"),
            (packages[3][0] if len(packages) > 3 else "Consumer"),
            "Consumer",
        ]
        cw, ch = 54, 22
        for (cx3, cy3), lbl in zip(cons_positions, cons_labels, strict=True):
            short = (lbl[:9] + "\u2026") if len(lbl) > 9 else lbl
            lines.append(
                f'<rect x="{cx3}" y="{cy3}" width="{cw}" height="{ch}"'
                f' rx="5" fill="#9333EA" filter="url(#pp-shadow)"/>'
            )
            lines.append(
                f'<text x="{cx3 + cw // 2}" y="{cy3 + 14}" fill="#fff"'
                f' font-size="7.5" text-anchor="middle"'
                f' font-family="system-ui,sans-serif">{short}</text>'
            )
            lines.append(
                f'<line x1="{bx + bw2}" y1="{bcy}"'
                f' x2="{cx3}" y2="{cy3 + ch // 2}"'
                f' stroke="#a1a1aa" stroke-width="1.2" marker-end="url(#pp-arr)"/>'
            )

        lines.append(
            '<text x="140" y="185" fill="#555" font-size="7"'
            ' text-anchor="middle" font-family="system-ui,sans-serif">'
            "Publishers \u2192 Bus \u2192 Consumers</text>"
        )
        lines.append('<circle class="flow-dot dot-evt" r="4" fill="#14B8A6"/>')
        return "\n".join(lines)

    def _svg_hexagonal(self, packages: list[tuple[str, str]]) -> str:
        """Domain hexagon at centre, adapter ring around it."""
        lines: list[str] = [f'<rect width="{_W}" height="{_H}" rx="10" fill="#0a0a0f"/>']

        cx, cy, r = 140, 98, 38
        pts = " ".join(
            f"{cx + r * math.cos(math.radians(60 * k - 30)):.1f},"
            f"{cy + r * math.sin(math.radians(60 * k - 30)):.1f}"
            for k in range(6)
        )
        lines.append(
            f'<polygon points="{pts}" fill="#14B8A6"'
            f' stroke="#0d9488" stroke-width="2" filter="url(#pp-shadow)"/>'
        )
        lines.append(
            f'<text x="{cx}" y="{cy - 4}" fill="#fff" font-size="9"'
            f' font-weight="700" text-anchor="middle" font-family="system-ui,sans-serif">'
            f"Domain</text>"
        )
        lines.append(
            f'<text x="{cx}" y="{cy + 8}" fill="#fff" font-size="7"'
            f' text-anchor="middle" font-family="system-ui,sans-serif">Core</text>'
        )

        adapters = [
            (0, "REST API"),
            (60, "CLI"),
            (120, "DB Repo"),
            (180, "Events"),
            (240, "gRPC"),
            (300, "Cache"),
        ]
        ring_r = 82
        aw, ah = 42, 18
        for i, (deg, default_label) in enumerate(adapters):
            angle = math.radians(deg - 30)
            ax = cx + ring_r * math.cos(angle)
            ay = cy + ring_r * math.sin(angle)
            lbl = packages[i][0] if i < len(packages) else default_label
            short = (lbl[:9] + "\u2026") if len(lbl) > 9 else lbl
            lines.append(
                f'<rect x="{ax - aw / 2:.1f}" y="{ay - ah / 2:.1f}"'
                f' width="{aw}" height="{ah}" rx="4"'
                f' fill="#6B7280" filter="url(#pp-shadow)"/>'
            )
            lines.append(
                f'<text x="{ax:.1f}" y="{ay + 4:.1f}" fill="#fff" font-size="7"'
                f' text-anchor="middle" font-family="system-ui,sans-serif">{short}</text>'
            )
            hx = cx + (r + 2) * math.cos(angle)
            hy = cy + (r + 2) * math.sin(angle)
            lines.append(
                f'<line x1="{ax:.1f}" y1="{ay:.1f}"'
                f' x2="{hx:.1f}" y2="{hy:.1f}"'
                f' stroke="#a1a1aa" stroke-width="1" marker-end="url(#pp-arr)" opacity="0.7"/>'
            )

        lines.append('<circle class="flow-dot dot-hex" r="3.5" fill="#14B8A6"/>')
        return "\n".join(lines)

    def _svg_microservice(self, packages: list[tuple[str, str]]) -> str:
        """Isolated service boxes each with own datastore."""
        lines: list[str] = [f'<rect width="{_W}" height="{_H}" rx="10" fill="#0a0a0f"/>']

        svc_names = [
            (packages[0][0] if len(packages) > 0 else "Catalog"),
            (packages[1][0] if len(packages) > 1 else "Ordering"),
            (packages[2][0] if len(packages) > 2 else "Shipping"),
        ]
        svc_colors = ["#14B8A6", "#F5A9D0", "#9333EA"]
        svc_fgs = ["#fff", "#111", "#fff"]
        svc_xs = [20, 106, 192]
        svc_w, svc_h = 68, 30
        svc_y = 52
        db_w2, db_h2 = 40, 18
        db_y = svc_y + svc_h + 18

        # API Gateway
        gw_w, gw_h = 70, 22
        gw_x = (_W - gw_w) // 2
        gw_y = 14
        gw_cx = gw_x + gw_w // 2
        lines.append(
            f'<rect x="{gw_x}" y="{gw_y}" width="{gw_w}" height="{gw_h}"'
            f' rx="5" fill="#d4a847" filter="url(#pp-shadow)"/>'
        )
        lines.append(
            f'<text x="{gw_cx}" y="{gw_y + 14}" fill="#111"'
            f' font-size="8.5" font-weight="700" text-anchor="middle"'
            f' font-family="system-ui,sans-serif">API Gateway</text>'
        )

        for _i, (sx, color, fg, name) in enumerate(
            zip(svc_xs, svc_colors, svc_fgs, svc_names, strict=True)
        ):
            scx = sx + svc_w // 2
            short = (name[:8] + "\u2026") if len(name) > 8 else name
            # Arrow from gateway
            lines.append(
                f'<line x1="{gw_cx}" y1="{gw_y + gw_h}"'
                f' x2="{scx}" y2="{svc_y}"'
                f' stroke="#d4a847" stroke-width="1"'
                f' marker-end="url(#pp-arr-gold)" opacity="0.7"/>'
            )
            # Service box
            lines.append(
                f'<rect x="{sx}" y="{svc_y}" width="{svc_w}" height="{svc_h}"'
                f' rx="6" fill="{color}" filter="url(#pp-shadow)"/>'
            )
            lines.append(
                f'<text x="{scx}" y="{svc_y + 13}" fill="{fg}"'
                f' font-size="8" font-weight="700" text-anchor="middle"'
                f' font-family="system-ui,sans-serif">{short}</text>'
            )
            lines.append(
                f'<text x="{scx}" y="{svc_y + 24}" fill="{fg}"'
                f' font-size="6.5" text-anchor="middle"'
                f' font-family="system-ui,sans-serif">Service</text>'
            )
            # DB cylinder
            dbx = sx + (svc_w - db_w2) // 2
            lines.append(
                f'<rect x="{dbx}" y="{db_y + 5}" width="{db_w2}" height="{db_h2 - 5}"'
                f' fill="#374151"/>'
            )
            lines.append(
                f'<ellipse cx="{dbx + db_w2 // 2}" cy="{db_y + 5}" rx="{db_w2 // 2}" ry="5"'
                f' fill="#4B5563"/>'
            )
            lines.append(
                f'<ellipse cx="{dbx + db_w2 // 2}" cy="{db_y + db_h2}" rx="{db_w2 // 2}" ry="5"'
                f' fill="#2d3748"/>'
            )
            lines.append(
                f'<text x="{dbx + db_w2 // 2}" y="{db_y + 14}" fill="#9ca3af"'
                f' font-size="6.5" text-anchor="middle"'
                f' font-family="system-ui,sans-serif">DB</text>'
            )
            # Connector svc → db
            lines.append(
                f'<line x1="{scx}" y1="{svc_y + svc_h}"'
                f' x2="{scx}" y2="{db_y + 5}"'
                f' stroke="#4B5563" stroke-width="1.5" stroke-dasharray="3,2"/>'
            )

        # Horizontal arrows between services
        for i in range(len(svc_xs) - 1):
            y_mid = svc_y + svc_h // 2
            x_from = svc_xs[i] + svc_w
            x_to = svc_xs[i + 1]
            lines.append(
                f'<line x1="{x_from}" y1="{y_mid}"'
                f' x2="{x_to}" y2="{y_mid}"'
                f' stroke="#a1a1aa" stroke-width="1.5" marker-end="url(#pp-arr)"/>'
            )

        lines.append('<circle class="flow-dot dot-ms" r="3.5" fill="#d4a847"/>')
        return "\n".join(lines)

    def _svg_monolith(self, packages: list[tuple[str, str]]) -> str:
        """Single large container with all module nodes inside."""
        lines: list[str] = [f'<rect width="{_W}" height="{_H}" rx="10" fill="#0a0a0f"/>']

        cx_cont, cy_cont = 16, 16
        cw, ch = 248, 150
        lines.append(
            f'<rect x="{cx_cont}" y="{cy_cont}" width="{cw}" height="{ch}"'
            f' rx="10" fill="#1e1e2a" stroke="#374151" stroke-width="2"/>'
        )
        lines.append(
            f'<text x="{cx_cont + 10}" y="{cy_cont + 14}" fill="#6B7280"'
            f' font-size="8" font-weight="700" font-family="system-ui,sans-serif">'
            f"APPLICATION</text>"
        )

        module_defaults = [
            ("UI", "presentation"),
            ("API", "presentation"),
            ("Service", "business"),
            ("Domain", "business"),
            ("Repo", "data"),
            ("DB", "infra"),
        ]
        modules: list[tuple[str, str]] = (
            packages[:6] if packages else module_defaults  # type: ignore[assignment]
        )
        mw, mh = 54, 26
        positions = [
            (cx_cont + 12, cy_cont + 22),
            (cx_cont + 78, cy_cont + 22),
            (cx_cont + 144, cy_cont + 22),
            (cx_cont + 12, cy_cont + 60),
            (cx_cont + 78, cy_cont + 60),
            (cx_cont + 144, cy_cont + 60),
        ]
        for (mx, my), (name, role) in zip(positions, modules, strict=True):
            color = _ROLE_COLORS.get(role, "#6B7280")
            text_col = _ROLE_TEXT.get(role, "#fff")
            short = (name[:6] + "\u2026") if len(name) > 6 else name
            mcx = mx + mw // 2
            lines.append(
                f'<rect x="{mx}" y="{my}" width="{mw}" height="{mh}"'
                f' rx="5" fill="{color}" filter="url(#pp-shadow)"/>'
            )
            lines.append(
                f'<text x="{mcx}" y="{my + 16}" fill="{text_col}"'
                f' font-size="8" font-weight="600" text-anchor="middle"'
                f' font-family="system-ui,sans-serif">{short}</text>'
            )

        # Internal arrows
        for (x1, y1), (x2, y2) in [
            (positions[0], positions[1]),
            (positions[1], positions[2]),
            (positions[2], positions[5]),
        ]:
            lx1, ly1 = x1 + mw, y1 + mh // 2
            lx2, ly2 = x2, y2 + mh // 2
            if abs(ly1 - ly2) > 10:  # diagonal — simplified
                lx1, ly1 = x1 + mw // 2, y1 + mh
                lx2, ly2 = x2 + mw // 2, y2
            lines.append(
                f'<line x1="{lx1}" y1="{ly1}" x2="{lx2}" y2="{ly2}"'
                f' stroke="#4B5563" stroke-width="1"'
                f' marker-end="url(#pp-arr)" opacity="0.8"/>'
            )

        # Shared DB at bottom of container
        db_x = cx_cont + (cw - 60) // 2
        db_y = cy_cont + ch - 30
        lines.append(f'<ellipse cx="{db_x + 30}" cy="{db_y + 5}" rx="30" ry="6" fill="#374151"/>')
        lines.append(f'<rect x="{db_x}" y="{db_y + 5}" width="60" height="14" fill="#374151"/>')
        lines.append(f'<ellipse cx="{db_x + 30}" cy="{db_y + 19}" rx="30" ry="6" fill="#2d3748"/>')
        lines.append(
            f'<text x="{db_x + 30}" y="{db_y + 14}" fill="#9ca3af"'
            f' font-size="7" text-anchor="middle" font-family="system-ui,sans-serif">'
            f"Shared DB</text>"
        )

        # Pulsing ring animation (two staggered rings at container centre)
        pcx = cx_cont + cw // 2
        pcy = cy_cont + 68
        lines.append(
            f'<circle cx="{pcx}" cy="{pcy}" r="8"'
            f' fill="none" stroke="#14B8A6" stroke-width="1.5" class="mono-ring"/>'
        )
        lines.append(
            f'<circle cx="{pcx}" cy="{pcy}" r="8"'
            f' fill="none" stroke="#14B8A6" stroke-width="1" class="mono-ring mono-ring-b"/>'
        )

        lines.append(
            '<text x="140" y="185" fill="#555" font-size="7"'
            ' text-anchor="middle" font-family="system-ui,sans-serif">'
            "All components in one deployable unit</text>"
        )
        return "\n".join(lines)

    def _svg_pipeline(self, packages: list[tuple[str, str]]) -> str:
        """Left-to-right sequential stages."""
        lines: list[str] = [f'<rect width="{_W}" height="{_H}" rx="10" fill="#0a0a0f"/>']

        default_stages = [
            ("Input", "#6B7280"),
            ("Validate", "#F5A9D0"),
            ("Process", "#14B8A6"),
            ("Transform", "#9333EA"),
            ("Output", "#d4a847"),
        ]
        stage_colors = [c for _, c in default_stages]
        stage_names: list[str]
        if packages:
            stage_names = [
                (packages[i][0] if i < len(packages) else default_stages[i][0]) for i in range(5)
            ]
        else:
            stage_names = [n for n, _ in default_stages]

        stg_w, stg_h = 38, 30
        inter = 16  # gap + arrow space
        total_w = len(stage_names) * stg_w + (len(stage_names) - 1) * inter
        x0 = (_W - total_w) // 2
        y0 = 75

        stage_xs: list[int] = []
        for i, (name, color) in enumerate(zip(stage_names, stage_colors, strict=True)):
            sx = x0 + i * (stg_w + inter)
            sy = y0
            scx = sx + stg_w // 2
            stage_xs.append(scx)
            short = (name[:5] + "\u2026") if len(name) > 5 else name
            lines.append(
                f'<rect x="{sx}" y="{sy}" width="{stg_w}" height="{stg_h}"'
                f' rx="5" fill="{color}" filter="url(#pp-shadow)"/>'
            )
            lines.append(
                f'<text x="{scx}" y="{sy + 18}" fill="#fff" font-size="7.5"'
                f' font-weight="600" text-anchor="middle"'
                f' font-family="system-ui,sans-serif">{short}</text>'
            )
            if i < len(stage_names) - 1:
                ax = sx + stg_w
                ay = sy + stg_h // 2
                lines.append(
                    f'<line x1="{ax}" y1="{ay}" x2="{ax + inter}" y2="{ay}"'
                    f' stroke="#a1a1aa" stroke-width="1.5" marker-end="url(#pp-arr)"/>'
                )

        # Header label
        mid_x = x0 + total_w // 2
        lines.append(
            f'<text x="{mid_x}" y="{y0 - 12}" fill="#6B7280" font-size="8"'
            f' font-weight="700" text-anchor="middle" font-family="system-ui,sans-serif">'
            f"Data Pipeline</text>"
        )

        lines.append('<circle class="flow-dot dot-pipe" r="4" fill="#fff"/>')
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # HTML scaffolding
    # ------------------------------------------------------------------

    def _legend_html(self) -> str:
        items = "".join(
            f'<span class="leg-item"'
            f' style="background:{color};color:{_ROLE_TEXT[role]}">'
            f"{_ROLE_LABELS[role]}</span>"
            for role, color in _ROLE_COLORS.items()
        )
        return f'<div class="legend">{items}</div>'

    def _html_page(self, title: str, body: str, detected: str = "") -> str:
        return (
            "<!DOCTYPE html>\n"
            '<html lang="en">\n'
            "<head>\n"
            '<meta charset="UTF-8"/>\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1"/>\n'
            f"<title>{title}</title>\n"
            f"<style>{_CSS}</style>\n"
            "</head>\n"
            f"<body>\n{body}\n</body>\n"
            "</html>"
        )


# ---------------------------------------------------------------------------
# Shared SVG <defs> block (markers, drop-shadow filter)
# ---------------------------------------------------------------------------

_DEFS = """
  <marker id="pp-arr" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
    <path d="M0,0 L8,3 L0,6 Z" fill="#a1a1aa"/>
  </marker>
  <marker id="pp-arr-teal" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
    <path d="M0,0 L8,3 L0,6 Z" fill="#14B8A6"/>
  </marker>
  <marker id="pp-arr-gold" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
    <path d="M0,0 L8,3 L0,6 Z" fill="#d4a847"/>
  </marker>
  <filter id="pp-shadow" x="-10%" y="-10%" width="120%" height="130%">
    <feDropShadow dx="0" dy="2" stdDeviation="2" flood-opacity="0.4"/>
  </filter>
"""

# ---------------------------------------------------------------------------
# CSS — animations + layout
# Coordinates are in SVG units (pixels at 1× scale).
#
# LAYERED  bands: y = 12, 56, 100, 144 (band_h=38, gap=6)
#   flow path: x=140, top=12 → bottom of band3 = 144+38 = 182
#
# EVENT_DRIVEN  bus_cx=140, bus_cy=100; pub[0] right edge=(68,66); cons[0] left=(212,66)
#
# HEXAGONAL  domain=(140,98); ring_r=82
#   adapter 0 angle=radians(-30): x=140+82*cos(-30°)≈211, y=98+82*sin(-30°)≈57
#   adapter 3 angle=radians(150): x=140+82*cos(150°)≈69,  y=98+82*sin(150°)≈139
#
# MICROSERVICE  gw_cx=140, gw bottom=36; svc centres: (54,67),(140,67),(226,67)
#
# PIPELINE  stg_w=38, inter=16, x0=13, y0=75; centres: 32,86,140,194,248; cy=90
# ---------------------------------------------------------------------------

_CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: #0a0a0f;
  color: #fafafa;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
  min-height: 100vh;
  padding: 24px;
}

/* ── single panel ─────────────────────────────────────── */
.poster-single { max-width: 680px; margin: 0 auto; }
.poster-header {
  display: flex; align-items: center; gap: 12px; margin-bottom: 20px;
}
.arch-badge {
  padding: 5px 14px; border-radius: 6px;
  font-weight: 700; font-size: 0.85rem; letter-spacing: 0.06em;
  text-transform: uppercase;
}
.confidence { font-size: 0.8rem; color: #6B7280; }

/* ── comparison grid ──────────────────────────────────── */
.poster-comparison { max-width: 960px; margin: 0 auto; }
.poster-banner {
  text-align: center; padding: 20px 0 24px;
  border-bottom: 1px solid #1e1e2a; margin-bottom: 24px;
}
.poster-banner h1 {
  font-size: 1.5rem; font-weight: 800;
  letter-spacing: 0.06em; color: #fafafa;
}
.accent { color: #14B8A6; }
.site-tag {
  display: inline-block; background: #1e1e2a;
  color: #14B8A6; border: 1px solid #14B8A6;
  border-radius: 4px; font-size: 0.65rem; font-weight: 700;
  padding: 2px 8px; margin-bottom: 8px; letter-spacing: 0.08em;
}
.pattern-grid {
  display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px;
}
.panel {
  background: #12121a; border: 1px solid #1e1e2a;
  border-radius: 10px; padding: 12px;
}
.panel.highlighted {
  border-color: #14B8A6;
  box-shadow: 0 0 0 1px #14B8A6, 0 0 20px rgba(20,184,166,0.15);
}
.panel-title {
  font-size: 0.7rem; font-weight: 800; letter-spacing: 0.1em;
  color: #9ca3af; text-transform: uppercase; margin-bottom: 8px;
}
.panel.highlighted .panel-title { color: #14B8A6; }
.pattern-svg { width: 100%; height: auto; display: block; }

/* ── legend ───────────────────────────────────────────── */
.legend { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
.leg-item {
  padding: 3px 10px; border-radius: 4px;
  font-size: 0.68rem; font-weight: 600;
}

/* ── animated dots ────────────────────────────────────── */
.flow-dot { opacity: 0; }

/* LAYERED: dot falls through four bands */
.dot-lyr {
  animation: flow-lyr 2.6s linear infinite;
}
@keyframes flow-lyr {
  0%   { transform: translate(140px,  12px); opacity: 0; }
  6%   { opacity: 0.95; }
  25%  { transform: translate(140px,  56px); }
  50%  { transform: translate(140px, 100px); }
  75%  { transform: translate(140px, 144px); }
  94%  { transform: translate(140px, 182px); opacity: 0.95; }
  100% { transform: translate(140px, 182px); opacity: 0; }
}

/* EVENT_DRIVEN: pulse publisher → bus → consumer */
.dot-evt {
  animation: flow-evt 2.2s ease-in-out infinite;
}
@keyframes flow-evt {
  0%   { transform: translate( 68px,  66px); opacity: 0; }
  5%   { opacity: 0.95; }
  40%  { transform: translate(140px, 100px); opacity: 0.95; }
  80%  { transform: translate(212px,  66px); opacity: 0.95; }
  95%  { opacity: 0; }
  100% { transform: translate( 68px,  66px); opacity: 0; }
}

/* HEXAGONAL: request enters adapter, crosses domain, exits far adapter */
.dot-hex {
  animation: flow-hex 2.4s ease-in-out infinite;
}
@keyframes flow-hex {
  0%   { transform: translate(211px,  57px); opacity: 0; }
  8%   { opacity: 0.95; }
  50%  { transform: translate(140px,  98px); opacity: 0.95; }
  92%  { transform: translate( 69px, 139px); opacity: 0.95; }
  100% { transform: translate( 69px, 139px); opacity: 0; }
}

/* MICROSERVICE: request gateway → svc0 → svc1 → svc2 */
.dot-ms {
  animation: flow-ms 2.6s ease-in-out infinite;
}
@keyframes flow-ms {
  0%   { transform: translate(140px, 36px); opacity: 0; }
  5%   { opacity: 0.95; }
  30%  { transform: translate( 54px, 67px); opacity: 0.95; }
  58%  { transform: translate(140px, 67px); opacity: 0.95; }
  88%  { transform: translate(226px, 67px); opacity: 0.95; }
  100% { transform: translate(226px, 67px); opacity: 0; }
}

/* MONOLITH: expanding ring pulse from container centre */
.mono-ring {
  transform-box: view-box;
  transform-origin: 140px 84px;
  animation: mono-pulse 2.8s ease-out infinite;
}
.mono-ring-b {
  animation-delay: 1.4s;
}
@keyframes mono-pulse {
  0%   { transform: scale(0.4); opacity: 0.7; }
  100% { transform: scale(6.0); opacity: 0;   }
}

/* PIPELINE: token slides left to right */
.dot-pipe {
  animation: flow-pipe 2.4s linear infinite;
}
@keyframes flow-pipe {
  0%   { transform: translate( 32px, 90px); opacity: 0; }
  5%   { opacity: 0.95; }
  25%  { transform: translate( 86px, 90px); }
  50%  { transform: translate(140px, 90px); }
  75%  { transform: translate(194px, 90px); }
  95%  { transform: translate(248px, 90px); opacity: 0.95; }
  100% { transform: translate(248px, 90px); opacity: 0; }
}

/* ── accessibility ────────────────────────────────────── */
@media (prefers-reduced-motion: reduce) {
  .flow-dot,
  .mono-ring {
    animation: none !important;
    opacity: 0 !important;
  }
}
"""

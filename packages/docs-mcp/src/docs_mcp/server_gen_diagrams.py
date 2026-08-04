"""Diagram and architecture-report DocsMCP generation tools.

Mermaid/PlantUML/D2 diagrams, the self-contained HTML architecture
report, and the interactive diagram viewer. Split out of
``server_gen_tools.py`` under TAP-5608 — that module is now a
registration facade that re-exports these handlers.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import structlog

from docs_mcp.server_gen_helpers import (
    get_settings as _get_settings,
)
from docs_mcp.server_gen_helpers import (
    record_call as _record_call,
)
from docs_mcp.server_helpers import (
    error_response,
    finalize_output,
    success_response,
)

logger = structlog.get_logger(__name__)


async def docs_generate_diagram(
    diagram_type: str = "dependency",
    scope: str = "project",
    depth: int = 2,
    format: str = "",
    direction: str = "TD",
    show_external: bool = False,
    flow_spec: str = "",
    theme: str = "default",
    project_root: str = "",
) -> dict[str, Any]:
    """Generate Mermaid, PlantUML, or D2 diagrams from code analysis.

    Diagram types:
    - "dependency": Module import dependency flowchart
    - "class_hierarchy": Class inheritance diagram
    - "module_map": Package/module architecture overview
    - "er_diagram": Entity-relationship diagram from Pydantic/dataclass models
    - "c4_context": C4 System Context diagram showing external actors
    - "c4_container": C4 Container diagram showing high-level building blocks
    - "c4_component": C4 Component diagram showing internal components
    - "sequence": Sequence diagram showing request flows and call chains
    - "pattern_card": Single-page archetype poster (layered/hexagonal/etc.)
      with packages colored by semantic role — README-embeddable.

    Args:
        diagram_type: Type of diagram to generate.
        scope: "project" for full project, or a file path for single-file scope.
            For c4_component, scope can be a package path to focus on.
        depth: Max traversal depth for dependency/module/sequence diagrams (default: 2).
        format: Output format - "mermaid", "plantuml", or "d2" (default: from config).
        direction: Graph direction - "TD" (top-down) or "LR" (left-right).
        show_external: Include external dependencies in dependency diagrams.
        flow_spec: JSON string defining a manual sequence flow. When provided with
            diagram_type="sequence", uses this spec instead of auto-detection.
            Expected: {"participants": [...], "messages": [{"from": ..., "to": ...,
            "label": ...}]}. Optional fields: "title", "notes", "groups".
        theme: D2 theme - "default", "sketch", or "terminal". Ignored for
            mermaid/plantuml formats.
        project_root: Override project root path (default: configured root).
    """
    _record_call("docs_generate_diagram")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_generate_diagram",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.generators.diagrams import DiagramGenerator

    output_format = format or getattr(settings, "diagram_format", "mermaid")

    generator = DiagramGenerator()
    try:
        result = generator.generate(
            root,
            diagram_type=diagram_type,
            output_format=output_format,
            scope=scope,
            depth=depth,
            direction=direction,
            show_external=show_external,
            flow_spec=flow_spec,
            theme=theme,
        )
    except Exception as exc:
        return error_response(
            "docs_generate_diagram",
            "GENERATION_ERROR",
            f"Failed to generate diagram: {exc}",
        )

    if not result.content:
        return error_response(
            "docs_generate_diagram",
            "NO_CONTENT",
            f"No content generated for diagram type '{diagram_type}'.",
        )

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "diagram_type": result.diagram_type,
        "format": result.format,
        "node_count": result.node_count,
        "edge_count": result.edge_count,
        "content": result.content,
    }

    return success_response("docs_generate_diagram", elapsed_ms, data)


async def docs_generate_architecture(
    title: str = "",
    subtitle: str = "",
    output_path: str = "",
    project_root: str = "",
    motion: str = "off",
) -> dict[str, Any]:
    """Generate a comprehensive, self-contained HTML architecture report.

    Produces a visually rich document with embedded SVG diagrams, detailed
    component descriptions, dependency flow visualizations, and API surface
    summary. The output is a single HTML file with no external dependencies.

    Sections included:
    - Project purpose and executive summary with key metrics
    - High-level architecture diagram (SVG with gradient-styled component boxes)
    - Component deep-dive with per-package descriptions and module listings
    - Dependency flow diagram (SVG with curved arrows showing import relationships)
    - Public API surface (classes, methods, docstrings)
    - Technology stack (runtime and development dependencies)

    Args:
        title: Custom report title (default: project name from metadata).
        subtitle: Custom subtitle / tagline (default: project description).
        output_path: File path to write the HTML report to. If empty, content
            is returned in the response without writing to disk.
        project_root: Override project root path (default: configured root).
        motion: Motion intensity for SVG flow diagrams. ``"off"`` (default)
            keeps the printable report static — important for PDF export.
            ``"subtle"`` / ``"particles"`` add SVG-native ``<animateMotion>``
            particles tracing each dependency-flow edge and each pipeline /
            layered pattern-panel edge. All motion is gated by
            ``prefers-reduced-motion``.
    """
    _record_call("docs_generate_architecture")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_generate_architecture",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.generators.architecture import ArchitectureGenerator

    generator = ArchitectureGenerator()
    try:
        result = generator.generate(
            root,
            title=title,
            subtitle=subtitle,
            motion=motion,
        )
    except Exception as exc:
        return error_response(
            "docs_generate_architecture",
            "GENERATION_ERROR",
            f"Failed to generate architecture report: {exc}",
        )

    if not result.content:
        return error_response(
            "docs_generate_architecture",
            "NO_CONTENT",
            "No content generated for architecture report.",
        )

    # Auto-compute output_path when not provided
    target = output_path.strip() or "docs/architecture.html"

    # Three-tier output: write-first / inline / manifest
    out_data = await finalize_output(
        "docs_generate_architecture",
        result.content,
        target,
        root,
        description="Architecture report (HTML with SVG diagrams).",
    )
    if not out_data.get("success", True):
        return out_data

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "format": result.format,
        "package_count": result.package_count,
        "module_count": result.module_count,
        "edge_count": result.edge_count,
        "class_count": result.class_count,
        **out_data,
    }

    # EPIC-102: write architecture facts to tapps-brain (opt-in)
    if settings.brain_write_enabled:
        from docs_mcp.integrations.brain_writer import ArchitectureBrainWriter

        writer = ArchitectureBrainWriter(root)
        project_name = root.name
        bw = await writer.write_from_architecture_result(result, project_name)
        data.update(bw.to_dict())

    return success_response(
        "docs_generate_architecture",
        elapsed_ms,
        data,
        next_steps=[
            "Open the HTML file in a browser for the full visual experience",
            "Use docs_generate_diagram for additional specific diagram types",
        ],
    )


async def docs_generate_interactive_diagrams(
    diagram_types: str = "dependency,module_map",
    title: str = "",
    output_path: str = "",
    project_root: str = "",
    motion: str = "subtle",
) -> dict[str, Any]:
    """Generate an interactive HTML page with Mermaid.js diagrams.

    Creates a self-contained HTML file with pan/zoom controls, diagram
    toggling, and a table of contents. Each requested diagram type is
    generated in Mermaid format and embedded in the interactive viewer.

    Args:
        diagram_types: Comma-separated diagram types to include.
            Valid types: dependency, class_hierarchy, module_map, er_diagram,
            c4_context, c4_container, c4_component.
        title: Page title (default: project name + " Architecture").
        output_path: File path to write HTML (relative to project root).
            When empty, returns content only.
        project_root: Override project root path (default: configured root).
        motion: Motion intensity for edge animations. ``"off"`` disables
            all motion CSS. ``"subtle"`` (default) emits CSS marching-ants
            on Mermaid edge paths, gated by ``prefers-reduced-motion``.
            ``"particles"`` falls back to ``"subtle"`` until the JS particle
            layer ships in a follow-up. Motion is suppressed automatically
            when every requested ``diagram_types`` value is relationship-only
            (``class_hierarchy``, ``er_diagram``, ``c4_context``).
    """
    _record_call("docs_generate_interactive_diagrams")
    start = time.perf_counter_ns()

    settings = _get_settings()
    root = Path(project_root) if project_root else Path(settings.project_root)

    if not root.is_dir():
        return error_response(
            "docs_generate_interactive_diagrams",
            "INVALID_ROOT",
            f"Project root does not exist: {root}",
        )

    from docs_mcp.generators.diagrams import DiagramGenerator
    from docs_mcp.generators.interactive_html import InteractiveHtmlGenerator

    types_list = [t.strip() for t in diagram_types.split(",") if t.strip()]
    if not types_list:
        return error_response(
            "docs_generate_interactive_diagrams",
            "NO_TYPES",
            "At least one diagram_type is required.",
        )

    # Generate each diagram in Mermaid format
    diagram_gen = DiagramGenerator()
    diagrams: list[tuple[str, str]] = []
    type_labels = {
        "dependency": "Dependency Graph",
        "class_hierarchy": "Class Hierarchy",
        "module_map": "Module Map",
        "er_diagram": "ER Diagram",
        "c4_context": "C4 System Context",
        "c4_container": "C4 Container",
        "c4_component": "C4 Component",
    }

    for dt in types_list:
        if dt not in DiagramGenerator.VALID_TYPES:
            continue
        try:
            result = diagram_gen.generate(root, diagram_type=dt, output_format="mermaid")
            if result.content:
                label = type_labels.get(dt, dt.replace("_", " ").title())
                diagrams.append((label, result.content))
        except Exception:
            logger.debug("interactive_diagram_failed", diagram_type=dt)

    if not diagrams:
        return error_response(
            "docs_generate_interactive_diagrams",
            "NO_DIAGRAMS",
            "No diagrams could be generated for the requested types.",
        )

    # Build interactive HTML
    page_title = title or f"{root.name} Architecture"
    html_gen = InteractiveHtmlGenerator()
    html_result = html_gen.generate(
        diagrams,
        title=page_title,
        subtitle=f"Generated from {root.name}",
        motion=motion,
        diagram_types=types_list,
    )
    content = html_result.content

    # Auto-compute output_path when not provided
    target = output_path.strip() or "docs/architecture-diagrams.html"

    # Three-tier output: write-first / inline / manifest
    out = await finalize_output(
        "docs_generate_interactive_diagrams",
        content,
        target,
        root,
        description="Interactive HTML architecture diagrams with Mermaid.js.",
    )
    if not out.get("success", True):
        return out

    elapsed_ms = (time.perf_counter_ns() - start) // 1_000_000

    data: dict[str, Any] = {
        "diagram_count": html_result.diagram_count,
        "title": html_result.title,
        **out,
    }

    return success_response(
        "docs_generate_interactive_diagrams",
        elapsed_ms,
        data,
        next_steps=[
            "Open the HTML file in a browser to explore the interactive diagrams.",
            "Use the zoom and toggle controls to navigate complex architectures.",
        ],
    )

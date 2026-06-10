"""Vol 8 — NLT Memory deep dive (TAP-3503)."""

from __future__ import annotations

from pathlib import Path

from report_studio.brand import BrandPack
from report_studio.styles import StyleBundle, build_styles
from report_studio.templates import ReportTemplate

from reports._deep_dive import ComponentSpec, build_component_story

# packages/tapps-mcp/src/tapps_mcp/server_memory_tools.py::register_memory_tools


def build_story(
    *,
    brand: BrandPack | None = None,
    bundle: StyleBundle | None = None,
    template: ReportTemplate | None = None,
):
    spec = ComponentSpec(
        cover_title="NLT Memory Deep Dive",
        cover_subtitle="Cross-session memory and knowledge graph",
        component_name="NLT Memory",
        role_paragraphs=(
            "NLT Memory is the shared recall authority. Consumers reach it over HTTP "
            "through the tapps-mcp memory bridge — never as an in-process embed.",
        ),
        architecture_bullets=(
            "FastAPI HTTP API — recall, save, reinforce, experience, hive.",
            "Postgres + embeddings + tiered retention.",
            "tapps-mcp bridge enforces profile filtering and auth.",
        ),
        workflow_rows=(
            ("tapps_memory search", "Session recall via MCP bridge"),
            ("POST /v1/recall", "Native brain recall endpoint"),
            ("hive_propagate", "Cross-agent knowledge sharing"),
        ),
        operations_bullets=(
            "TAPPS_BRAIN_AUTH_TOKEN for authenticated bridge mode.",
            "brain_bridge_health in tapps_session_start response.",
        ),
        cross_link_rows=(
            ("Vol 4", "Memory bridge control-flow sequence"),
            ("Vol 10", "Tapps Platform ops guide"),
        ),
        checkout_note=f"Package root: {Path(__file__).resolve().parents[2]}",
    )
    resolved_brand = brand or BrandPack.from_id("nlt-v3.2")
    resolved_bundle = bundle or build_styles(resolved_brand, has_dejavu=False)
    return build_component_story(spec, brand=resolved_brand, bundle=resolved_bundle, template=template)

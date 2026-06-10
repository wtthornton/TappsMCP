"""Vol 10 — Tapps Platform builder ops (TAP-3505)."""

from __future__ import annotations

from report_studio.brand import BrandPack
from report_studio.styles import StyleBundle, build_styles
from report_studio.templates import ReportTemplate

from reports._builder_ops import BuilderOpsSpec, build_builder_ops_story


def build_story(
    *,
    brand: BrandPack | None = None,
    bundle: StyleBundle | None = None,
    template: ReportTemplate | None = None,
):
    spec = BuilderOpsSpec(
        cover_title="Tapps Platform Builder Ops",
        cover_subtitle="tapps-mcp · docs-mcp · quality pipeline",
        foreword=(
            "Tapps Platform is the dev-time quality layer. Runtime memory for agents "
            "is NLT Memory (Vol 8) — reached over HTTP, not embedded in-process."
        ),
        install_bullets=(
            "tapps-mcp upgrade --host auto refreshes MCP config in consumer repos.",
            "with_report_studio in tapps_init wires Report Studio scaffold.",
            "Brain bridge HTTP only — no direct tapps-brain in .mcp.json.",
        ),
        cli_rows=(
            ("tapps_session_start", "Bootstrap session + brain_bridge_health"),
            ("tapps_quick_check", "Score + gate after Python edits"),
            ("tapps_validate_changed", "Batch gate on explicit file_paths"),
            ("tapps_memory", "Cross-session recall via NLT Memory bridge"),
        ),
        template_bullets=(
            "AGENTS.md documents the seven Tapps rules per consumer repo.",
            "Engagement levels: high / medium / low.",
        ),
        verify_bullets=(
            "Pre-commit: tapps-mcp validate-changed --quick on staged Python.",
            "CI: tapps-quality.yml on pull requests.",
        ),
        plugin_bullets=(
            "/tapps-finish-task — validate + checklist bundle.",
            "/tapps-handoff-session — cross-chat handoff.",
        ),
    )
    resolved_brand = brand or BrandPack.from_id("nlt-v3.2")
    resolved_bundle = bundle or build_styles(resolved_brand, has_dejavu=False)
    return build_builder_ops_story(spec, brand=resolved_brand, bundle=resolved_bundle, template=template)

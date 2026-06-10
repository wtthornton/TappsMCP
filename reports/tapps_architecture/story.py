"""TappsMCP architecture smoke report (TAP-3445)."""

from __future__ import annotations

import os
from pathlib import Path

from reportlab.lib.units import inch
from reportlab.platypus import PageBreak

from report_studio import components
from report_studio.brand import BrandPack
from report_studio.document import CoverBackground, CoverSpec
from report_studio.styles import StyleBundle, build_styles
from report_studio.templates import ReportTemplate


def _tapps_root() -> Path:
    raw = os.environ.get("TAPPS_MCP_ROOT")
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parents[2]


# Citations for report-studio verify (paths relative to tapps-mcp root):
# packages/tapps-mcp/src/tapps_mcp/cli.py::main
# packages/tapps-mcp/src/tapps_mcp/server.py::run_server


def build_story(
    *,
    brand: BrandPack | None = None,
    bundle: StyleBundle | None = None,
    template: ReportTemplate | None = None,
):
    resolved_brand = brand or BrandPack.from_id("nlt-v3.2")
    resolved_bundle = bundle or build_styles(resolved_brand, has_dejavu=False)
    root = _tapps_root()
    cli = "packages/tapps-mcp/src/tapps_mcp/cli.py"
    server = "packages/tapps-mcp/src/tapps_mcp/server.py"

    return [
        CoverBackground(
            resolved_brand,
            spec=CoverSpec(title="TappsMCP Architecture", subtitle="Quality pipeline smoke report"),
            has_dejavu=False,
        ),
        PageBreak(),
        components.H("Surface area", resolved_bundle, level=1),
        components.P(
            "Consumer report proving nlt-report-studio outside AgentForge. "
            f"Checkout: {root}",
            resolved_bundle,
        ),
        components.vspace(),
        components.make_table(
            [
                ["Component", "Source anchor"],
                ["CLI entry", f"{cli}::main"],
                ["MCP server", f"{server}::run_server"],
            ],
            [1.5 * inch, 4.0 * inch],
            resolved_bundle,
        ),
        PageBreak(),
        components.H("Pipeline", resolved_bundle, level=1),
        *components.bullets(
            [
                "Session start bootstraps checker environment and brain bridge.",
                "Quick check scores edited Python before merge.",
                "Validate changed batches git-changed files at task completion.",
                "Memory bridge reaches tapps-brain over HTTP — no in-process brain.",
            ],
            resolved_bundle,
        ),
        components.vspace(),
        components.make_table(
            [
                ["Stage", "Tool", "When"],
                ["Discover", "tapps_session_start", "First call each session"],
                ["Edit", "tapps_quick_check", "After each Python file change"],
                ["Complete", "tapps_validate_changed", "Before declaring task done"],
                ["Verify", "tapps_checklist", "Final pipeline gate"],
            ],
            [1.2 * inch, 2.0 * inch, 2.3 * inch],
            resolved_bundle,
        ),
        PageBreak(),
        components.H("Memory and brain bridge", resolved_bundle, level=1),
        components.P(
            "tapps-mcp never embeds tapps-brain in-process for consumer repos. "
            "Memory tools negotiate HTTP against the brain service; auth uses "
            "TAPPS_BRAIN_AUTH_TOKEN when configured.",
            resolved_bundle,
        ),
        components.vspace(),
        components.P(
            "Quality presets (standard, strict) gate overall score, security scan, "
            "and lint categories. CI and pre-commit hooks reuse the same validators.",
            resolved_bundle,
        ),
        PageBreak(),
        components.H("Verification", resolved_bundle, level=1),
        components.P(
            "Run verify after editing this story: "
            "report-studio verify --builders reports/tapps_architecture/story.py "
            "--root . --prefix packages/tapps-mcp/src/",
            resolved_bundle,
        ),
        components.vspace(),
        components.P(
            "Smoke report before investing in a full tapps-mcp architecture narrative. "
            "Built via report-studio build CLI with nlt-report-studio path dependency.",
            resolved_bundle,
        ),
    ]

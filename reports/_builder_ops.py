"""Shared section builders for builder_operations meta ops guides."""

from __future__ import annotations

from dataclasses import dataclass

from reportlab.lib.units import inch
from reportlab.platypus import PageBreak

from report_studio import components
from report_studio.brand import BrandPack
from report_studio.document import CoverBackground, CoverSpec
from report_studio.styles import StyleBundle
from report_studio.templates import ReportTemplate

from reports.suite_sections import section_title


@dataclass(frozen=True)
class BuilderOpsSpec:
    cover_title: str
    cover_subtitle: str
    foreword: str
    install_bullets: tuple[str, ...]
    cli_rows: tuple[tuple[str, str], ...]
    template_bullets: tuple[str, ...]
    verify_bullets: tuple[str, ...]
    plugin_bullets: tuple[str, ...]


def build_builder_ops_story(
    spec: BuilderOpsSpec,
    *,
    brand: BrandPack,
    bundle: StyleBundle,
    template: ReportTemplate | None,
) -> list:
    return [
        CoverBackground(
            brand,
            spec=CoverSpec(title=spec.cover_title, subtitle=spec.cover_subtitle),
            has_dejavu=False,
        ),
        PageBreak(),
        components.H(section_title(template, "foreword", "Foreword"), bundle, level=1),
        components.P(spec.foreword, bundle),
        PageBreak(),
        components.H(section_title(template, "install", "Install and pin"), bundle, level=1),
        *components.bullets(list(spec.install_bullets), bundle),
        PageBreak(),
        components.H(section_title(template, "cli", "CLI commands"), bundle, level=1),
        components.make_table(
            [["Command", "Purpose"], *list(spec.cli_rows)],
            [2.0 * inch, 3.5 * inch],
            bundle,
        ),
        PageBreak(),
        components.H(section_title(template, "verify", "Verify and CI"), bundle, level=1),
        *components.bullets(list(spec.verify_bullets), bundle),
    ]

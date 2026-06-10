"""Shared section builders for component_deep_dive consumers."""

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
class ComponentSpec:
    cover_title: str
    cover_subtitle: str
    component_name: str
    role_paragraphs: tuple[str, ...]
    architecture_bullets: tuple[str, ...]
    workflow_rows: tuple[tuple[str, str], ...]
    operations_bullets: tuple[str, ...]
    cross_link_rows: tuple[tuple[str, str], ...]
    checkout_note: str = ""


def build_component_story(
    spec: ComponentSpec,
    *,
    brand: BrandPack,
    bundle: StyleBundle,
    template: ReportTemplate | None,
) -> list:
    story: list = [
        CoverBackground(
            brand,
            spec=CoverSpec(title=spec.cover_title, subtitle=spec.cover_subtitle),
            has_dejavu=False,
        ),
        PageBreak(),
        components.H(section_title(template, "foreword", "Foreword"), bundle, level=1),
        components.P(
            f"This volume is the technical deep dive for {spec.component_name}.",
            bundle,
        ),
        PageBreak(),
        components.H(section_title(template, "role", "Role in the platform"), bundle, level=1),
    ]
    for paragraph in spec.role_paragraphs:
        story.append(components.P(paragraph, bundle))
    if spec.checkout_note:
        story.append(components.P(spec.checkout_note, bundle))
    story.append(PageBreak())
    story.extend(
        [
            components.H(section_title(template, "architecture", "Architecture"), bundle, level=1),
            *components.bullets(list(spec.architecture_bullets), bundle),
            PageBreak(),
            components.H(section_title(template, "workflows", "Key workflows"), bundle, level=1),
        ],
    )
    if spec.workflow_rows:
        rows = [["Workflow / surface", "Purpose"], *list(spec.workflow_rows)]
        story.append(components.make_table(rows, [2.2 * inch, 3.3 * inch], bundle))
    story.append(PageBreak())
    story.extend(
        [
            components.H(
                section_title(template, "operations", "Operations and boundaries"),
                bundle,
                level=1,
            ),
            *components.bullets(list(spec.operations_bullets), bundle),
            PageBreak(),
            components.H(section_title(template, "cross_links", "Related volumes"), bundle, level=1),
        ],
    )
    if spec.cross_link_rows:
        rows = [["Volume", "Topic"], *list(spec.cross_link_rows)]
        story.append(components.make_table(rows, [1.2 * inch, 4.3 * inch], bundle))
    return story

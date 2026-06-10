"""Template section title helper for document suite consumers."""

from __future__ import annotations

from report_studio.templates import ReportTemplate


def section_title(template: ReportTemplate | None, part_id: str, fallback: str) -> str:
    if template is None:
        return fallback
    for part in template.parts:
        if part.id == part_id:
            return part.title
    return fallback

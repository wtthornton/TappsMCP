"""Smoke tests for reports/memory_platform (TAP-3503)."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from report_studio.build import run_build


def test_memory_platform_builds(tmp_path: Path) -> None:
    out = tmp_path / "memory.pdf"
    rc = run_build(
        brand_id="nlt-v3.2",
        module_spec="reports.memory_platform.story:build_story",
        out_path=out,
        template_id="component_deep_dive",
        bookmarks=False,
    )
    assert rc == 0
    text = "\n".join((page.extract_text() or "") for page in PdfReader(str(out)).pages)
    assert "NLT Memory" in text

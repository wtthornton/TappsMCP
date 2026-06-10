"""Smoke tests for reports/tapps_architecture (TAP-3445)."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from report_studio.build import run_build
from report_studio.verify import verify_citations


def test_tapps_architecture_builds_five_pages(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    out = tmp_path / "tapps-architecture.pdf"
    rc = run_build(
        brand_id="nlt-v3.2",
        module_spec="reports.tapps_architecture.story:build_story",
        out_path=out,
        bookmarks=False,
    )
    assert rc == 0
    assert len(PdfReader(str(out)).pages) >= 5


def test_tapps_story_citations_resolve() -> None:
    root = Path(__file__).resolve().parents[2]
    story_path = root / "reports" / "tapps_architecture" / "story.py"
    result = verify_citations(
        [story_path],
        source_roots=[root],
        path_prefixes=["packages/tapps-mcp/src/"],
    )
    assert result.ok, [f"{b.citation.rel_path}::{b.citation.symbol}: {b.reason}" for b in result.broken]

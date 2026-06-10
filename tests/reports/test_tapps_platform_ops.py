"""Smoke tests for reports/tapps_platform_ops (TAP-3505)."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader

from report_studio.build import run_build


def test_tapps_platform_ops_builds(tmp_path: Path) -> None:
    out = tmp_path / "platform-ops.pdf"
    rc = run_build(
        brand_id="nlt-v3.2",
        module_spec="reports.tapps_platform_ops.story:build_story",
        out_path=out,
        template_id="builder_operations",
        bookmarks=False,
    )
    assert rc == 0
    text = "\n".join((page.extract_text() or "") for page in PdfReader(str(out)).pages)
    assert "Tapps Platform" in text or "tapps" in text.lower()

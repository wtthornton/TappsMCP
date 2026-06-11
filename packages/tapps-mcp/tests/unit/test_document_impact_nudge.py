"""Tests for document layout impact-analysis nudges."""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.pipeline.document_judges import is_document_layout_path


class TestDocumentLayoutPath:
    def test_reports_path_matches(self, tmp_path: Path) -> None:
        path = tmp_path / "reports" / "annual" / "page.tsx"
        assert is_document_layout_path(path, tmp_path) is True

    def test_src_path_does_not_match(self, tmp_path: Path) -> None:
        path = tmp_path / "src" / "service.py"
        path.parent.mkdir(parents=True)
        path.touch()
        assert is_document_layout_path(path, tmp_path) is False


@pytest.mark.asyncio
async def test_impact_analysis_adds_rebuild_nudge_for_layout_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tapps_mcp.project.models import ImpactReport
    from tapps_mcp.server_analysis_tools import tapps_impact_analysis

    monkeypatch.chdir(tmp_path)
    target = tmp_path / "reports" / "chapter.py"
    target.parent.mkdir(parents=True)
    target.write_text("def render() -> None: pass\n", encoding="utf-8")

    report = ImpactReport(
        changed_file="reports/chapter.py",
        change_type="modified",
        severity="low",
        total_affected=0,
        recommendations=[],
    )

    monkeypatch.setattr(
        "tapps_mcp.server_analysis_tools._validate_file_path_lazy",
        lambda p: Path(p),
    )
    monkeypatch.setattr(
        "tapps_mcp.project.impact_analyzer.analyze_impact",
        lambda *_a, **_k: report,
    )
    monkeypatch.setattr(
        "tapps_mcp.server_analysis_tools.build_impact_memory_context",
        lambda *_a, **_k: {},
    )
    monkeypatch.setattr("tapps_mcp.server_analysis_tools._with_nudges", lambda _t, r: r)
    monkeypatch.setattr("tapps_mcp.server_analysis_tools._record_call", lambda *_a, **_k: None)
    monkeypatch.setattr("tapps_mcp.server_analysis_tools._record_execution", lambda *_a, **_k: None)

    result = await tapps_impact_analysis(str(target))
    recs = result["data"]["recommendations"]
    assert any("rebuild" in r.lower() for r in recs)


@pytest.mark.asyncio
async def test_impact_analysis_no_rebuild_nudge_for_src_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tapps_mcp.project.models import ImpactReport
    from tapps_mcp.server_analysis_tools import tapps_impact_analysis

    monkeypatch.chdir(tmp_path)
    target = tmp_path / "src" / "service.py"
    target.parent.mkdir(parents=True)
    target.write_text("x = 1\n", encoding="utf-8")

    report = ImpactReport(
        changed_file="src/service.py",
        change_type="modified",
        severity="low",
        total_affected=0,
        recommendations=[],
    )

    monkeypatch.setattr(
        "tapps_mcp.server_analysis_tools._validate_file_path_lazy",
        lambda p: Path(p),
    )
    monkeypatch.setattr(
        "tapps_mcp.project.impact_analyzer.analyze_impact",
        lambda *_a, **_k: report,
    )
    monkeypatch.setattr(
        "tapps_mcp.server_analysis_tools.build_impact_memory_context",
        lambda *_a, **_k: {},
    )
    monkeypatch.setattr("tapps_mcp.server_analysis_tools._with_nudges", lambda _t, r: r)
    monkeypatch.setattr("tapps_mcp.server_analysis_tools._record_call", lambda *_a, **_k: None)
    monkeypatch.setattr("tapps_mcp.server_analysis_tools._record_execution", lambda *_a, **_k: None)

    result = await tapps_impact_analysis(str(target))
    recs = result["data"]["recommendations"]
    assert not any("rebuild shipped PDFs" in r for r in recs)

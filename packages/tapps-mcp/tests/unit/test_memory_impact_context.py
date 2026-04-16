"""Impact analysis memory_context enrichment (Epic M4.4 / CHUNK-G)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tapps_mcp.config.settings import MemorySettings, TappsMCPSettings


def test_build_impact_memory_context_skips_when_memory_disabled(tmp_path: Path) -> None:
    from tapps_mcp.server_helpers import build_impact_memory_context

    settings = TappsMCPSettings(
        project_root=tmp_path,
        memory=MemorySettings(enabled=False, enrich_impact_analysis=True),
    )
    f = tmp_path / "pkg" / "mod.py"
    f.parent.mkdir(parents=True)
    f.write_text("x = 1\n", encoding="utf-8")
    out = build_impact_memory_context(f, tmp_path, settings)
    assert out["memory_context"] == []
    assert out["memory_context_enrichment"] == "skipped"
    assert out["memory_context_skip"] == "memory_disabled"


def test_build_impact_memory_context_skips_when_enrich_off(tmp_path: Path) -> None:
    from tapps_mcp.server_helpers import build_impact_memory_context

    settings = TappsMCPSettings(
        project_root=tmp_path,
        memory=MemorySettings(enabled=True, enrich_impact_analysis=False),
    )
    f = tmp_path / "a.py"
    f.write_text("pass\n", encoding="utf-8")
    out = build_impact_memory_context(f, tmp_path, settings)
    assert out["memory_context"] == []
    assert out["memory_context_skip"] == "enrich_impact_analysis_disabled"


def test_build_impact_memory_context_search_results(tmp_path: Path) -> None:
    from tapps_mcp.server_helpers import _reset_memory_store_cache, build_impact_memory_context

    _reset_memory_store_cache()
    settings = TappsMCPSettings(
        project_root=tmp_path,
        memory=MemorySettings(enabled=True, enrich_impact_analysis=True),
    )
    f = tmp_path / "src" / "app.py"
    f.parent.mkdir(parents=True)
    f.write_text("def main() -> None: ...\n", encoding="utf-8")

    hits = [
        SimpleNamespace(
            key="k1",
            value="Uses app.py for entrypoint",
            tier="pattern",
            confidence=0.85,
        ),
        SimpleNamespace(
            key="k2",
            value="Low confidence",
            tier="context",
            confidence=0.1,
        ),
    ]
    mock_store = SimpleNamespace(search=lambda q: hits if "app.py" in q else [])

    with patch("tapps_mcp.server_helpers._get_memory_store", return_value=mock_store):
        out = build_impact_memory_context(f, tmp_path, settings)

    assert out["memory_context_enrichment"] == "ok"
    assert out["memory_context_query"] == "src/app.py app.py"
    assert len(out["memory_context"]) == 1
    assert out["memory_context"][0]["key"] == "k1"
    assert out["memory_context"][0]["tier"] == "pattern"
    assert out["memory_context"][0]["source"] == "memory"


@pytest.mark.asyncio
async def test_tapps_impact_analysis_merges_memory_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tapps_mcp.project.models import ImpactReport
    from tapps_mcp.server_analysis_tools import tapps_impact_analysis

    monkeypatch.chdir(tmp_path)
    target = tmp_path / "t.py"
    target.write_text("x = 1\n", encoding="utf-8")

    report = ImpactReport(
        changed_file="t.py",
        change_type="modified",
        severity="low",
        total_affected=0,
        recommendations=[],
    )

    def _fake_analyze(*_a: object, **_k: object) -> ImpactReport:
        return report

    mem_ctx = {
        "memory_context": [{"key": "x", "summary": "hi", "tier": "pattern", "confidence": 0.9}],
        "memory_context_enrichment": "ok",
        "memory_context_query": "t.py",
    }

    def _vp(p: str) -> Path:
        return Path(p)

    monkeypatch.setattr(
        "tapps_mcp.server_analysis_tools._validate_file_path_lazy",
        _vp,
    )
    monkeypatch.setattr(
        "tapps_mcp.project.impact_analyzer.analyze_impact",
        _fake_analyze,
    )
    monkeypatch.setattr(
        "tapps_mcp.server_analysis_tools.build_impact_memory_context",
        lambda *_a, **_k: mem_ctx,
    )
    monkeypatch.setattr("tapps_mcp.server_analysis_tools._with_nudges", lambda _t, r: r)
    monkeypatch.setattr("tapps_mcp.server_analysis_tools._record_call", lambda *_a, **_k: None)
    monkeypatch.setattr("tapps_mcp.server_analysis_tools._record_execution", lambda *_a, **_k: None)

    result = await tapps_impact_analysis(str(target))
    assert result["success"] is True
    data = result["data"]
    assert data["memory_context"][0]["key"] == "x"
    assert data["memory_context_enrichment"] == "ok"
    assert result.get("structuredContent", {}).get("memory_context") == mem_ctx["memory_context"]

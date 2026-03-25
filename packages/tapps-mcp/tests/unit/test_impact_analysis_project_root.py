"""Tests for project_root parameter in tapps_impact_analysis (Story 89.1)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tapps_mcp.server_analysis_tools import tapps_impact_analysis


def _make_impact_report(changed_file: str = "mod.py") -> object:
    """Create a minimal ImpactReport-like object for testing."""
    return SimpleNamespace(
        changed_file=changed_file,
        change_type="modified",
        severity="low",
        total_affected=0,
        direct_dependents=[],
        transitive_dependents=[],
        test_files=[],
        recommendations=["Review dependents"],
    )


@pytest.fixture()
def _patch_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch recording and nudge helpers so tests don't need full server state."""
    monkeypatch.setattr("tapps_mcp.server_analysis_tools._record_call", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "tapps_mcp.server_analysis_tools._record_execution", lambda *_a, **_k: None
    )
    monkeypatch.setattr("tapps_mcp.server_analysis_tools._with_nudges", lambda _t, r: r)
    monkeypatch.setattr(
        "tapps_mcp.server_analysis_tools.build_impact_memory_context",
        lambda *_a, **_k: {"memory_context": [], "memory_context_enrichment": "skipped"},
    )


@pytest.mark.asyncio()
@pytest.mark.usefixtures("_patch_helpers")
async def test_default_uses_settings_project_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without project_root, behavior uses settings.project_root (backward compat)."""
    target = tmp_path / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")

    report = _make_impact_report(str(target))
    monkeypatch.setattr(
        "tapps_mcp.project.impact_analyzer.analyze_impact",
        lambda *_a, **_k: report,
    )
    # Patch _validate_file_path_lazy (default path, no project_root)
    monkeypatch.setattr(
        "tapps_mcp.server_analysis_tools._validate_file_path_lazy",
        lambda p: Path(p),
    )
    # Patch settings to return tmp_path as project_root
    monkeypatch.setattr(
        "tapps_mcp.server_analysis_tools.load_settings",
        lambda: SimpleNamespace(project_root=tmp_path),
    )

    result = await tapps_impact_analysis(str(target))
    assert result["success"] is True
    assert result["data"]["changed_file"] == str(target)


@pytest.mark.asyncio()
@pytest.mark.usefixtures("_patch_helpers")
async def test_explicit_project_root_resolves_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Explicit project_root resolves files against that root."""
    ext_project = tmp_path / "external"
    ext_project.mkdir()
    target = ext_project / "lib" / "foo.py"
    target.parent.mkdir(parents=True)
    target.write_text("y = 2\n", encoding="utf-8")

    report = _make_impact_report("lib/foo.py")
    monkeypatch.setattr(
        "tapps_mcp.project.impact_analyzer.analyze_impact",
        lambda *_a, **_k: report,
    )
    monkeypatch.setattr(
        "tapps_mcp.server_analysis_tools.load_settings",
        lambda: SimpleNamespace(project_root=tmp_path),
    )

    result = await tapps_impact_analysis(
        "lib/foo.py", project_root=str(ext_project)
    )
    assert result["success"] is True
    assert result["data"]["changed_file"] == "lib/foo.py"


@pytest.mark.asyncio()
@pytest.mark.usefixtures("_patch_helpers")
async def test_file_outside_custom_project_root_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """File outside the custom project_root returns path_denied error."""
    ext_project = tmp_path / "external"
    ext_project.mkdir()
    outside = tmp_path / "other" / "secret.py"
    outside.parent.mkdir(parents=True)
    outside.write_text("z = 3\n", encoding="utf-8")

    monkeypatch.setattr(
        "tapps_mcp.server_analysis_tools.load_settings",
        lambda: SimpleNamespace(project_root=tmp_path),
    )

    result = await tapps_impact_analysis(
        str(outside), project_root=str(ext_project)
    )
    assert result["success"] is False
    assert result["error_code"] == "path_denied"


@pytest.mark.asyncio()
@pytest.mark.usefixtures("_patch_helpers")
async def test_nonexistent_project_root_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-existent project_root returns invalid_project_root error."""
    monkeypatch.setattr(
        "tapps_mcp.server_analysis_tools.load_settings",
        lambda: SimpleNamespace(project_root=tmp_path),
    )

    result = await tapps_impact_analysis(
        "foo.py", project_root=str(tmp_path / "does_not_exist")
    )
    assert result["success"] is False
    assert result["error_code"] == "invalid_project_root"
    assert "not an existing directory" in result["error"]

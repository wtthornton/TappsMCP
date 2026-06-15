"""MCP handler tests for Epic 114 call-graph tools."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tapps_mcp.project.call_graph import build_call_graph_index


def _write_pkg(root: Path, rel: str, source: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_tapps_call_graph_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tapps_mcp.server_analysis_tools import tapps_call_graph

    _write_pkg(
        tmp_path,
        "demo/calls.py",
        """
def callee():
    return 1

def caller():
    callee()
""",
    )
    build_call_graph_index(tmp_path, force_rebuild=True)

    mock_settings = MagicMock()
    mock_settings.project_root = tmp_path

    recorded: list[dict[str, object]] = []

    def _capture_execution(tool_name: str, start_ns: int, **kwargs: object) -> None:
        recorded.append({"tool": tool_name, **kwargs})

    monkeypatch.setattr("tapps_mcp.server_analysis_tools.load_settings", lambda: mock_settings)
    monkeypatch.setattr(
        "tapps_mcp.server_analysis_tools.resolve_effective_project_root",
        lambda _root, _override: MagicMock(error_code=None, root=tmp_path),
    )
    monkeypatch.setattr("tapps_mcp.server_analysis_tools._record_call", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "tapps_mcp.server_analysis_tools._record_execution",
        _capture_execution,
    )
    monkeypatch.setattr("tapps_mcp.server_analysis_tools._with_nudges", lambda _t, r, *_a: r)

    result = await tapps_call_graph(
        symbol="demo.calls.caller",
        query="callers",
        project_root=str(tmp_path),
    )

    assert result["success"] is True
    assert result["data"]["symbol"] == "demo.calls.caller"
    assert recorded == [{"tool": "tapps_call_graph", "degraded": False}]


@pytest.mark.asyncio
async def test_tapps_diff_impact_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tapps_mcp.server_analysis_tools import tapps_diff_impact

    target = tmp_path / "pkg" / "mod.py"
    target.parent.mkdir(parents=True)
    target.write_text("def foo():\n    pass\n", encoding="utf-8")
    build_call_graph_index(tmp_path, force_rebuild=True)

    mock_settings = MagicMock()
    mock_settings.project_root = tmp_path

    recorded: list[dict[str, object]] = []

    def _capture_execution(tool_name: str, start_ns: int, **kwargs: object) -> None:
        recorded.append({"tool": tool_name, **kwargs})

    monkeypatch.setattr("tapps_mcp.server_analysis_tools.load_settings", lambda: mock_settings)
    monkeypatch.setattr(
        "tapps_mcp.server_analysis_tools.resolve_effective_project_root",
        lambda _root, _override: MagicMock(error_code=None, root=tmp_path),
    )
    monkeypatch.setattr(
        "tapps_mcp.server_analysis_tools.validate_read_path_under_root",
        lambda fp, root: (root / fp).resolve(),
    )
    monkeypatch.setattr("tapps_mcp.server_analysis_tools._record_call", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "tapps_mcp.server_analysis_tools._record_execution",
        _capture_execution,
    )
    monkeypatch.setattr("tapps_mcp.server_analysis_tools._with_nudges", lambda _t, r, *_a: r)

    result = await tapps_diff_impact(
        file_paths="pkg/mod.py",
        project_root=str(tmp_path),
    )

    assert result["success"] is True
    assert "affected_tests" in result["data"]
    assert recorded[0]["tool"] == "tapps_diff_impact"
    assert "file_path" in recorded[0]

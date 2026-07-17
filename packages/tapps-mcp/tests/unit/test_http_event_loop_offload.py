"""Regression: shared HTTP fleet must not starve Cursor handshakes.

CPU-bound sync work inside async MCP handlers blocks uvicorn's event loop so
``initialize`` / ``tools/list`` time out while TCP still accepts connections
(Cursor "Loading tools"). Heavy bodies must run via ``asyncio.to_thread``.
"""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from tapps_mcp.server_analysis_tools import tapps_impact_analysis


def _make_impact_report(changed_file: str) -> object:
    return SimpleNamespace(
        changed_file=changed_file,
        change_type="modified",
        severity="low",
        total_affected=0,
        direct_dependents=[],
        transitive_dependents=[],
        test_files=[],
        recommendations=[],
    )


@pytest.fixture()
def _patch_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tapps_mcp.server_analysis_tools._record_call", lambda *_a, **_k: None)
    monkeypatch.setattr("tapps_mcp.server_analysis_tools._record_execution", lambda *_a, **_k: None)
    monkeypatch.setattr("tapps_mcp.server_analysis_tools._with_nudges", lambda *_a, **_k: _a[1])
    monkeypatch.setattr(
        "tapps_mcp.server_analysis_tools.build_impact_memory_context",
        lambda *_a, **_k: {"memory_context": [], "memory_context_enrichment": "skipped"},
    )
    monkeypatch.setattr(
        "tapps_mcp.tools.procedural_patterns.fire_refactor_sequence",
        lambda *_a, **_k: None,
    )


@pytest.mark.asyncio()
@pytest.mark.usefixtures("_patch_helpers")
async def test_impact_analysis_keeps_event_loop_responsive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """While sync impact analysis runs in a worker thread, the loop still ticks."""
    target = tmp_path / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")
    report = _make_impact_report(str(target))
    started = asyncio.Event()
    ticks = 0

    def _slow_analyze(*_a: Any, **_k: Any) -> object:
        started.set()
        time.sleep(0.2)
        return report

    async def _ticker() -> None:
        nonlocal ticks
        await started.wait()
        deadline = time.monotonic() + 0.15
        while time.monotonic() < deadline:
            ticks += 1
            await asyncio.sleep(0)

    monkeypatch.setattr(
        "tapps_mcp.project.impact_analyzer.analyze_impact",
        _slow_analyze,
    )
    monkeypatch.setattr(
        "tapps_mcp.server_analysis_tools._validate_file_path_lazy",
        lambda p: Path(p),
    )
    monkeypatch.setattr(
        "tapps_mcp.server_analysis_tools.load_settings",
        lambda: SimpleNamespace(project_root=tmp_path),
    )

    ticker = asyncio.create_task(_ticker())
    result = await tapps_impact_analysis(str(target))
    await ticker

    assert result["success"] is True
    assert ticks > 0, "event loop was blocked during impact analysis"


@pytest.mark.asyncio()
async def test_radon_direct_fallback_runs_off_event_loop_thread() -> None:
    """Empty-subprocess radon fallback must execute on a worker thread."""
    from tapps_mcp.tools.radon import run_radon_cc_async
    from tapps_mcp.tools.subprocess_runner import CommandResult

    main_ident = threading.get_ident()
    worker_idents: list[int] = []

    def _direct(_path: str) -> list[dict[str, object]]:
        worker_idents.append(threading.get_ident())
        time.sleep(0.05)
        return [{"name": "f", "complexity": 1}]

    with (
        patch(
            "tapps_mcp.tools.radon.run_command_async",
            return_value=CommandResult(returncode=0, stdout="", stderr=""),
        ),
        patch("tapps_mcp.tools.radon._radon_cc_direct", side_effect=_direct),
    ):
        result = await run_radon_cc_async("x.py")

    assert result == [{"name": "f", "complexity": 1}]
    assert worker_idents
    assert worker_idents[0] != main_ident

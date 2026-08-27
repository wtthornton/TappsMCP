"""TAP-6441: tapps_memory must record execution metrics.

Before this fix, ``server_memory_tools.py`` called ``_record_call`` in 11
places (checklist bookkeeping) but never ``_record_execution`` (MetricsHub
persistence) — zero ``tapps_memory`` rows across 125,201 metric records.
Every return path in ``tapps_memory`` now funnels through a ``_finish()``
helper that calls ``_record_execution`` with the sub-``action`` so
per-action counts are recoverable from ``tool_calls_*.jsonl``.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_core.metrics.collector import MetricsHub
from tapps_mcp import server_analysis_tools, server_memory_tools

pytestmark = pytest.mark.asyncio


def _record_execution_capture() -> tuple[list[dict[str, object]], MagicMock]:
    """Return a (records, mock) pair capturing each ``_record_execution`` call."""
    records: list[dict[str, object]] = []

    def fake(tool_name: str, _start_ns: int, **kwargs: object) -> None:
        records.append({"tool_name": tool_name, **kwargs})

    mock = MagicMock(side_effect=fake)
    return records, mock


async def test_invalid_action_records_execution_failure() -> None:
    records, fake_record_execution = _record_execution_capture()

    with (
        patch("tapps_mcp.server_memory_tools._record_execution", fake_record_execution),
        patch("tapps_mcp.server_memory_tools._record_call", MagicMock()),
        patch(
            "tapps_mcp.server_memory_tools.ensure_session_initialized",
            AsyncMock(return_value=None),
        ),
    ):
        resp = await server_memory_tools.tapps_memory(action="not_an_action")

    assert resp["success"] is False
    assert records == [
        {
            "tool_name": "tapps_memory",
            "status": "failed",
            "action": "not_an_action",
            "error_code": "invalid_action",
        }
    ]


async def test_dispatch_crash_records_execution_failure() -> None:
    records, fake_record_execution = _record_execution_capture()

    async def _crashing_handler(_store: object, _params: object) -> object:
        raise RuntimeError("simulated dispatch failure")

    with (
        patch("tapps_mcp.server_memory_tools._record_execution", fake_record_execution),
        patch("tapps_mcp.server_memory_tools._record_call", MagicMock()),
        patch(
            "tapps_mcp.server_memory_tools.ensure_session_initialized",
            AsyncMock(return_value=None),
        ),
        patch(
            "tapps_mcp.server_memory_tools._get_memory_store",
            return_value=MagicMock(),
        ),
        patch.dict(
            server_memory_tools._ASYNC_DISPATCH,
            {"session_start_capture": _crashing_handler},
            clear=False,
        ),
    ):
        resp = await server_memory_tools.tapps_memory(action="session_start_capture")

    assert resp["success"] is False
    assert records == [
        {
            "tool_name": "tapps_memory",
            "status": "failed",
            "action": "session_start_capture",
            "error_code": "action_failed",
        }
    ]


async def test_successful_lifecycle_call_records_execution_success() -> None:
    records, fake_record_execution = _record_execution_capture()

    with (
        patch("tapps_mcp.server_memory_tools._record_execution", fake_record_execution),
        patch("tapps_mcp.server_memory_tools._record_call", MagicMock()),
        patch(
            "tapps_mcp.server_memory_tools.ensure_session_initialized",
            AsyncMock(return_value=None),
        ),
        patch(
            "tapps_mcp.server_memory_tools._get_memory_store",
            return_value=MagicMock(),
        ),
        patch.dict(
            server_memory_tools._ASYNC_DISPATCH,
            {"session_start_capture": AsyncMock(return_value={"indexed": True})},
            clear=False,
        ),
    ):
        resp = await server_memory_tools.tapps_memory(action="session_start_capture")

    assert resp["success"] is True
    assert records == [
        {
            "tool_name": "tapps_memory",
            "status": "success",
            "action": "session_start_capture",
            "error_code": None,
        }
    ]


async def test_save_and_search_produce_execution_metric_rows(tmp_path: Path) -> None:
    """VAL-13: a save and a search each land a ``tapps_memory`` row in
    ``tool_calls_*.jsonl`` under a hermetic tmp project root — never the
    live repo's metrics dir."""
    hub = MetricsHub(tmp_path)
    fake_store = MagicMock()

    with (
        patch("tapps_mcp.server_memory_tools._MCP_MEMORY_MODE", "slim"),
        patch("tapps_mcp.server_memory_tools._record_call", MagicMock()),
        patch(
            "tapps_mcp.server_memory_tools.ensure_session_initialized",
            AsyncMock(return_value=None),
        ),
        patch("tapps_mcp.server_memory_tools._get_memory_store", return_value=fake_store),
        patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=None),
        patch("tapps_mcp.server._get_metrics_hub", return_value=hub),
        patch.dict(
            server_memory_tools._DISPATCH,
            {
                "save": lambda _store, params: {"status": "saved", "key": params.key},
                "search": lambda _store, _params: {"returned_count": 0, "results": []},
            },
            clear=False,
        ),
    ):
        save_resp = await server_memory_tools.tapps_memory(action="save", key="k1", value="v1")
        search_resp = await server_memory_tools.tapps_memory(action="search", query="k1")

    assert save_resp["success"] is True
    assert search_resp["success"] is True

    metrics_files = sorted((tmp_path / ".tapps-mcp" / "metrics").glob("tool_calls_*.jsonl"))
    assert metrics_files, "expected tapps_memory execution metrics to be written to disk"

    rows = [
        json.loads(line)
        for f in metrics_files
        for line in f.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    memory_rows = [r for r in rows if r["tool_name"] == "tapps_memory"]
    assert {r["action"] for r in memory_rows} == {"save", "search"}
    assert all(r["status"] == "success" for r in memory_rows)


# ---------------------------------------------------------------------------
# TAP-6441 item 5 — nlt-memory surface sweep found tapps_session_notes with
# the same gap: only its success path called _record_execution.
# ---------------------------------------------------------------------------


def _analysis_record_execution_capture() -> tuple[list[dict[str, object]], MagicMock]:
    records: list[dict[str, object]] = []

    def fake(tool_name: str, _start_ns: int, **kwargs: object) -> None:
        records.append({"tool_name": tool_name, **kwargs})

    mock = MagicMock(side_effect=fake)
    return records, mock


async def test_session_notes_invalid_action_records_execution_failure() -> None:
    records, fake_record_execution = _analysis_record_execution_capture()

    with (
        patch("tapps_mcp.server_analysis_tools._record_execution", fake_record_execution),
        patch("tapps_mcp.server_analysis_tools._record_call", MagicMock()),
        patch(
            "tapps_mcp.server_analysis_tools._get_session_store",
            return_value=MagicMock(),
        ),
    ):
        resp = await server_analysis_tools.tapps_session_notes(action="bogus")

    assert resp["success"] is False
    assert records == [
        {
            "tool_name": "tapps_session_notes",
            "status": "failed",
            "error_code": "invalid_action",
            "action": "bogus",
        }
    ]


async def test_session_notes_missing_params_records_execution_failure() -> None:
    records, fake_record_execution = _analysis_record_execution_capture()

    with (
        patch("tapps_mcp.server_analysis_tools._record_execution", fake_record_execution),
        patch("tapps_mcp.server_analysis_tools._record_call", MagicMock()),
        patch(
            "tapps_mcp.server_analysis_tools._get_session_store",
            return_value=MagicMock(),
        ),
    ):
        resp = await server_analysis_tools.tapps_session_notes(action="save", key="", value="")

    assert resp["success"] is False
    assert records == [
        {
            "tool_name": "tapps_session_notes",
            "status": "failed",
            "error_code": "missing_params",
            "action": "save",
        }
    ]


async def test_session_notes_success_records_execution_with_action() -> None:
    records, fake_record_execution = _analysis_record_execution_capture()
    fake_store = MagicMock()
    fake_store.list_all.return_value = []
    fake_store.metadata.return_value = {}

    with (
        patch("tapps_mcp.server_analysis_tools._record_execution", fake_record_execution),
        patch("tapps_mcp.server_analysis_tools._record_call", MagicMock()),
        patch(
            "tapps_mcp.server_analysis_tools._get_session_store",
            return_value=fake_store,
        ),
    ):
        resp = await server_analysis_tools.tapps_session_notes(action="list")

    assert resp["success"] is True
    assert records == [
        {"tool_name": "tapps_session_notes", "action": "list"},
    ]

"""Tests for session-start call graph background rebuild (TAP-4266)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from tapps_mcp.project.call_graph_cache import save_call_graph_index
from tapps_mcp.project.call_graph_types import CallGraphIndex, INDEX_VERSION
from tapps_mcp.tools.session_start_helpers import _schedule_call_graph_rebuild


def test_schedule_call_graph_rebuild_skips_fresh_cache(tmp_path: Path) -> None:
    result = _schedule_call_graph_rebuild(
        tmp_path,
        {"status": "ready", "stale": False},
    )
    assert result["scheduled"] is False
    assert result["skipped"] == "cache_fresh"


@pytest.mark.asyncio
async def test_schedule_call_graph_rebuild_runs_for_stale_cache(tmp_path: Path) -> None:
    from tapps_mcp import server_pipeline_tools as host

    host._reset_background_tasks()
    save_call_graph_index(
        tmp_path,
        CallGraphIndex(
            project_root=str(tmp_path),
            fingerprint="stale",
            version=INDEX_VERSION,
        ),
    )
    with patch(
        "tapps_mcp.project.call_graph.build_call_graph_index",
        autospec=True,
    ) as mock_build:
        scheduled = _schedule_call_graph_rebuild(
            tmp_path,
            {"status": "stale", "stale": True},
        )
        assert scheduled["scheduled"] is True
        await asyncio.gather(*host._background_tasks)
        mock_build.assert_called_once_with(tmp_path)

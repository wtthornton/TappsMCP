"""tapps_memory Hive actions (Epic M3 / CHUNK-C)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tapps_mcp.server_memory_tools import (
    _handle_agent_register,
    _handle_hive_propagate,
    _handle_hive_search,
    _Params,
    tapps_memory,
)


def _minimal_params(**kwargs: object) -> _Params:
    """Build _Params with defaults for hive handler tests."""
    base: dict[str, object] = {
        "key": "",
        "value": "",
        "tier": "pattern",
        "source": "agent",
        "source_agent": "unknown",
        "scope": "project",
        "tag_list": [],
        "branch": "",
        "query": "",
        "confidence": -1.0,
        "ranked": True,
        "limit": 0,
        "include_summary": True,
        "file_path": "",
        "overwrite": False,
        "entries": "",
        "entry_ids": [],
        "dry_run": False,
        "include_sources": False,
        "project_id": "",
        "sources": [],
        "min_confidence": 0.5,
        "include_hub": True,
        "stale_only": False,
        "max_entries": 10,
        "export_format": "json",
        "include_frontmatter": True,
        "export_group_by": "tier",
        "include_session_index": False,
        "session_id": "",
        "chunks": "",
        "safety_bypass": False,
    }
    base.update(kwargs)
    return _Params(**base)


@pytest.fixture
def mock_memory_store() -> MagicMock:
    store = MagicMock()
    snap = MagicMock()
    snap.total_count = 0
    snap.tier_counts = {}
    snap.entries = []
    store.snapshot.return_value = snap
    return store


def _fake_bridge_with_hive(hive: Any | None) -> Any:
    """Build a fake BrainBridge wrapping a brain whose .hive is *hive*.

    Used to exercise hive handlers without a real Postgres DSN.
    """
    from types import SimpleNamespace

    from tapps_core.brain_bridge import BrainBridge

    fake_brain = SimpleNamespace(
        store=MagicMock(),
        hive=hive,
        recall=lambda query, max_results=10: [],
        close=lambda: None,
    )
    return BrainBridge(fake_brain)


@pytest.mark.asyncio
async def test_handle_hive_search_missing_query(mock_memory_store: MagicMock) -> None:
    out = await _handle_hive_search(mock_memory_store, _minimal_params())
    assert out["error"] == "missing_query"


@pytest.mark.asyncio
async def test_handle_hive_search_disabled_env(
    mock_memory_store: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", raising=False)
    out = await _handle_hive_search(
        mock_memory_store,
        _minimal_params(query="auth"),
    )
    assert out["enabled"] is False
    assert out["result_count"] == 0


@pytest.mark.asyncio
async def test_handle_hive_search_degraded_when_hive_missing(
    mock_memory_store: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1")
    bridge = _fake_bridge_with_hive(None)

    with patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge):
        out = await _handle_hive_search(
            mock_memory_store,
            _minimal_params(query="x"),
        )
    assert out.get("degraded") is True


@pytest.mark.asyncio
async def test_handle_hive_search_happy_path(
    mock_memory_store: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1")
    hive = MagicMock()
    hive.search.return_value = [{"key": "k1", "namespace": "universal"}]
    bridge = _fake_bridge_with_hive(hive)

    with patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge):
        out = await _handle_hive_search(
            mock_memory_store,
            _minimal_params(query="jwt", limit=5, tag_list=["universal"]),
        )
    assert out["degraded"] is False
    assert out["result_count"] == 1
    hive.search.assert_called_once()
    call_args = hive.search.call_args
    assert call_args[0][0] == "jwt"
    assert call_args[1]["namespaces"] == ["universal"]
    assert call_args[1]["limit"] == 5


@pytest.mark.asyncio
async def test_handle_hive_propagate_skips_private(
    mock_memory_store: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1")
    entry = MagicMock()
    entry.key = "k1"
    entry.value = "v1"
    entry.agent_scope = "private"
    entry.tier = "pattern"
    entry.confidence = 0.7
    entry.source = MagicMock()
    entry.source.value = "agent"
    entry.tags = []

    snap = MagicMock()
    snap.entries = [entry]
    mock_memory_store.snapshot.return_value = snap

    hive = MagicMock()
    bridge = _fake_bridge_with_hive(hive)

    with (
        patch("tapps_mcp.server_memory_tools._get_brain_bridge", return_value=bridge),
        patch("tapps_core.config.settings.load_settings") as ls,
        patch("tapps_brain.backends.PropagationEngine.propagate", return_value=None),
    ):
        mset = MagicMock()
        mset.memory.profile = "repo-brain"
        mset.project_root = Path("/tmp")
        ls.return_value = mset
        out = await _handle_hive_propagate(mock_memory_store, _minimal_params(limit=10))
    assert out["propagated"] == 0
    assert out["skipped_private"] == 1


@pytest.mark.asyncio
async def test_handle_agent_register_missing_key(mock_memory_store: MagicMock) -> None:
    out = await _handle_agent_register(mock_memory_store, _minimal_params())
    assert out.get("error") == "missing_key"


@pytest.mark.asyncio
async def test_tapps_memory_hive_status_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", raising=False)
    from tapps_mcp.server_helpers import _reset_hive_store_cache

    _reset_hive_store_cache()

    # TAP-408: _get_memory_store() now requires TAPPS_BRAIN_DATABASE_URL via BrainBridge.
    # Mock the bridge singleton so this integration test doesn't need a real DB.
    mock_store = MagicMock()
    snap = MagicMock()
    snap.total_count = 0
    snap.tier_counts = {}
    mock_store.snapshot.return_value = snap

    mock_bridge = MagicMock()
    mock_bridge.store = mock_store

    with patch("tapps_mcp.server_helpers._get_brain_bridge", return_value=mock_bridge):
        result = await tapps_memory(action="hive_status")

    assert result["success"] is True
    assert result["data"]["action"] == "hive_status"
    assert result["data"]["enabled"] is False
    assert "propagation_config" not in result["data"]

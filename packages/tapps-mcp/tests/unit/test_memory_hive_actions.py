"""tapps_memory Hive actions (Epic M3 / CHUNK-C)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tapps_mcp.server_memory_tools import (
    _Params,
    _handle_agent_register,
    _handle_hive_propagate,
    _handle_hive_search,
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


def test_handle_hive_search_missing_query(mock_memory_store: MagicMock) -> None:
    out = _handle_hive_search(mock_memory_store, _minimal_params())
    assert out["error"] == "missing_query"


def test_handle_hive_search_disabled_env(mock_memory_store: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", raising=False)
    out = _handle_hive_search(
        mock_memory_store,
        _minimal_params(query="auth"),
    )
    assert out["enabled"] is False
    assert out["result_count"] == 0


def test_handle_hive_search_degraded_on_import(
    mock_memory_store: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1")

    def _fail() -> tuple[None, None, str]:
        return None, None, "no hive"

    with patch("tapps_mcp.server_memory_tools._ensure_hive_singletons", _fail):
        out = _handle_hive_search(
            mock_memory_store,
            _minimal_params(query="x"),
        )
    assert out.get("degraded") is True
    assert "no hive" in (out.get("message") or "")


def test_handle_hive_search_happy_path(
    mock_memory_store: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "1")
    hive = MagicMock()
    hive.search.return_value = [{"key": "k1", "namespace": "universal"}]

    def _ok() -> tuple[MagicMock, None, None]:
        return hive, None, None

    with patch("tapps_mcp.server_memory_tools._ensure_hive_singletons", _ok):
        out = _handle_hive_search(
            mock_memory_store,
            _minimal_params(query="jwt", limit=5, tag_list=["universal"]),
        )
    assert out["degraded"] is False
    assert out["result_count"] == 1
    hive.search.assert_called_once()
    call_kw = hive.search.call_args
    assert call_kw[0][0] == "jwt"
    assert call_kw[1]["namespaces"] == ["universal"]
    assert call_kw[1]["limit"] == 5


def test_handle_hive_propagate_skips_private(
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

    def _ok() -> tuple[MagicMock, None, None]:
        return hive, None, None

    with (
        patch("tapps_mcp.server_memory_tools._ensure_hive_singletons", _ok),
        patch("tapps_core.config.settings.load_settings") as ls,
    ):
        mset = MagicMock()
        mset.memory.profile = "repo-brain"
        mset.project_root = Path("/tmp")
        ls.return_value = mset
        out = _handle_hive_propagate(mock_memory_store, _minimal_params(limit=10))
    assert out["propagated"] == 0
    assert out["skipped_private"] == 1


def test_handle_agent_register_missing_key(mock_memory_store: MagicMock) -> None:
    out = _handle_agent_register(mock_memory_store, _minimal_params())
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
    pc = result["data"].get("propagation_config")
    assert isinstance(pc, dict)
    assert pc.get("profile_sourced") is False

"""Tests for server_linear_tools (TAP-964).

Post-rework: tapps-mcp is a cache, not a Linear client. These tests
cover the ``_get`` / ``_put`` / ``_invalidate`` tool surface and the
cache primitives.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from tapps_mcp.server_linear_tools import (
    _cache_dir,
    _cache_key,
    _cache_read,
    _cache_write,
    _filter_hash,
    _resolve_cache_key,
    _ttl_for_state,
    tapps_linear_snapshot_get,
    tapps_linear_snapshot_invalidate,
    tapps_linear_snapshot_put,
)


@pytest.fixture
def fake_settings(tmp_path: Path) -> Any:
    """Return a settings-like stub with a tmp_path project_root."""

    class _Stub:
        project_root = tmp_path
        linear_cache_ttl_open_seconds: int = 300
        linear_cache_ttl_closed_seconds: int = 3600

    return _Stub()


@pytest.fixture
def mock_load_settings(fake_settings: Any) -> Any:
    with patch(
        "tapps_mcp.server_linear_tools.load_settings", return_value=fake_settings
    ) as m:
        yield m


# ---------------------------------------------------------------------------
# Cache-primitive tests
# ---------------------------------------------------------------------------


def test_filter_hash_is_order_independent() -> None:
    a = _filter_hash(state="backlog", label="bug", limit=50)
    b = _filter_hash(limit=50, label="bug", state="backlog")
    assert a == b


def test_filter_hash_ignores_empty_values() -> None:
    a = _filter_hash(state="backlog", label="", limit=50)
    b = _filter_hash(state="backlog", label=None, limit=50)
    assert a == b


def test_cache_key_includes_all_dims() -> None:
    key = _cache_key("myteam", "myproject", "backlog", "abc123")
    assert key == "myteam__myproject__backlog__abc123"


def test_cache_key_handles_slashes_and_none_state() -> None:
    key = _cache_key("my/team", "my/project", None, "xyz")
    assert "/" not in key
    assert "any" in key


def test_resolve_cache_key_is_deterministic() -> None:
    a = _resolve_cache_key("T", "P", "backlog", "bug", 50)
    b = _resolve_cache_key("T", "P", "backlog", "bug", 50)
    assert a == b


def test_resolve_cache_key_differs_on_any_input() -> None:
    base = _resolve_cache_key("T", "P", "backlog", "", 50)
    assert _resolve_cache_key("OTHER", "P", "backlog", "", 50) != base
    assert _resolve_cache_key("T", "OTHER", "backlog", "", 50) != base
    assert _resolve_cache_key("T", "P", "unstarted", "", 50) != base
    assert _resolve_cache_key("T", "P", "backlog", "bug", 50) != base
    assert _resolve_cache_key("T", "P", "backlog", "", 100) != base


def test_ttl_for_state_picks_correct_bucket() -> None:
    assert _ttl_for_state("backlog", 300, 3600) == 300
    assert _ttl_for_state("unstarted", 300, 3600) == 300
    assert _ttl_for_state("completed", 300, 3600) == 3600
    assert _ttl_for_state("canceled", 300, 3600) == 3600
    assert _ttl_for_state(None, 300, 3600) == 300
    assert _ttl_for_state("unknown", 300, 3600) == 300


def test_cache_read_returns_none_on_expired(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    _cache_write(
        cache_dir,
        "k",
        {"issues": [{"id": "x"}], "expires_at": time.time() - 1, "cached_at": 0},
    )
    assert _cache_read(cache_dir, "k") is None


def test_cache_read_returns_payload_when_fresh(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    _cache_write(
        cache_dir,
        "k",
        {
            "issues": [{"id": "x"}],
            "expires_at": time.time() + 600,
            "cached_at": time.time(),
        },
    )
    got = _cache_read(cache_dir, "k")
    assert got is not None
    assert got["issues"] == [{"id": "x"}]


def test_cache_read_returns_none_on_corrupt_file(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "k.json").write_text("{not json", encoding="utf-8")
    assert _cache_read(cache_dir, "k") is None


# ---------------------------------------------------------------------------
# _get tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_requires_team_and_project(mock_load_settings: Any) -> None:
    result = await tapps_linear_snapshot_get(team="", project="P")
    assert result["success"] is False
    assert result["error"]["code"] == "invalid_input"


@pytest.mark.asyncio
async def test_get_miss_returns_hint(mock_load_settings: Any) -> None:
    result = await tapps_linear_snapshot_get(team="T", project="P", state="backlog")
    assert result["success"] is True
    assert result["data"]["cached"] is False
    assert "list_issues" in result["data"]["hint"]
    assert "tapps_linear_snapshot_put" in result["data"]["hint"]
    assert result["data"]["cache_key"]


@pytest.mark.asyncio
async def test_get_hit_returns_stored_issues(
    tmp_path: Path, mock_load_settings: Any
) -> None:
    cache_dir = _cache_dir(tmp_path)
    key = _resolve_cache_key("T", "P", "backlog", "", 50)
    stored = [{"id": "LIN-42", "title": "Cached"}]
    _cache_write(
        cache_dir,
        key,
        {
            "issues": stored,
            "expires_at": time.time() + 600,
            "cached_at": time.time() - 5,
            "team": "T",
            "project": "P",
            "state": "backlog",
        },
    )

    result = await tapps_linear_snapshot_get(team="T", project="P", state="backlog")
    assert result["success"] is True
    assert result["data"]["cached"] is True
    assert result["data"]["issues"] == stored
    assert result["data"]["age_seconds"] is not None
    assert result["data"]["age_seconds"] >= 4


@pytest.mark.asyncio
async def test_get_treats_expired_as_miss(
    tmp_path: Path, mock_load_settings: Any
) -> None:
    cache_dir = _cache_dir(tmp_path)
    key = _resolve_cache_key("T", "P", "backlog", "", 50)
    _cache_write(
        cache_dir,
        key,
        {
            "issues": [{"id": "stale"}],
            "expires_at": time.time() - 60,
            "cached_at": time.time() - 1000,
        },
    )

    result = await tapps_linear_snapshot_get(team="T", project="P", state="backlog")
    assert result["success"] is True
    assert result["data"]["cached"] is False


# ---------------------------------------------------------------------------
# _put tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_requires_team_and_project(mock_load_settings: Any) -> None:
    result = await tapps_linear_snapshot_put(
        team="", project="P", issues_json="[]"
    )
    assert result["success"] is False
    assert result["error"]["code"] == "invalid_input"


@pytest.mark.asyncio
async def test_put_rejects_invalid_json(mock_load_settings: Any) -> None:
    result = await tapps_linear_snapshot_put(
        team="T", project="P", issues_json="not json"
    )
    assert result["success"] is False
    assert result["error"]["code"] == "invalid_input"
    assert "JSON" in result["error"]["message"]


@pytest.mark.asyncio
async def test_put_rejects_non_list_payload(mock_load_settings: Any) -> None:
    result = await tapps_linear_snapshot_put(
        team="T", project="P", issues_json='{"foo": "bar"}'
    )
    assert result["success"] is False
    assert result["error"]["code"] == "invalid_input"
    assert "list" in result["error"]["message"].lower()


@pytest.mark.asyncio
async def test_put_stores_issues_and_get_reads_them(
    tmp_path: Path, mock_load_settings: Any
) -> None:
    issues = [{"id": "LIN-1", "title": "One"}, {"id": "LIN-2", "title": "Two"}]
    put_result = await tapps_linear_snapshot_put(
        team="T",
        project="P",
        issues_json=json.dumps(issues),
        state="backlog",
    )
    assert put_result["success"] is True
    assert put_result["data"]["stored"] is True
    assert put_result["data"]["issue_count"] == 2
    assert put_result["data"]["ttl_seconds"] == 300

    get_result = await tapps_linear_snapshot_get(team="T", project="P", state="backlog")
    assert get_result["data"]["cached"] is True
    assert get_result["data"]["issues"] == issues


@pytest.mark.asyncio
async def test_put_uses_closed_ttl_for_completed_state(
    mock_load_settings: Any,
) -> None:
    result = await tapps_linear_snapshot_put(
        team="T", project="P", issues_json="[]", state="completed"
    )
    assert result["success"] is True
    assert result["data"]["ttl_seconds"] == 3600


@pytest.mark.asyncio
async def test_put_with_zero_ttl_skips_write(
    tmp_path: Path, fake_settings: Any
) -> None:
    fake_settings.linear_cache_ttl_open_seconds = 0
    with patch(
        "tapps_mcp.server_linear_tools.load_settings", return_value=fake_settings
    ):
        result = await tapps_linear_snapshot_put(
            team="T", project="P", issues_json="[]", state="backlog"
        )
    assert result["success"] is True
    assert result["data"]["stored"] is False
    assert "disabled" in result["data"]["hint"].lower()


@pytest.mark.asyncio
async def test_put_empty_issues_json_stores_empty_list(
    mock_load_settings: Any,
) -> None:
    result = await tapps_linear_snapshot_put(
        team="T", project="P", issues_json="", state="backlog"
    )
    assert result["success"] is True
    assert result["data"]["stored"] is True
    assert result["data"]["issue_count"] == 0


# ---------------------------------------------------------------------------
# _invalidate tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalidate_removes_team_project_entries(
    tmp_path: Path, mock_load_settings: Any
) -> None:
    cache_dir = _cache_dir(tmp_path)
    for name in ("T__P__backlog__abc", "T__P__unstarted__def", "OTHER__P__backlog__xyz"):
        (cache_dir / f"{name}.json").write_text(
            json.dumps({"issues": [], "expires_at": time.time() + 600}),
            encoding="utf-8",
        )

    result = await tapps_linear_snapshot_invalidate(team="T", project="P")
    assert result["success"] is True
    assert result["data"]["removed"] == 2
    remaining = {p.name for p in cache_dir.glob("*.json")}
    assert remaining == {"OTHER__P__backlog__xyz.json"}


@pytest.mark.asyncio
async def test_invalidate_all_when_no_args(
    tmp_path: Path, mock_load_settings: Any
) -> None:
    cache_dir = _cache_dir(tmp_path)
    for name in ("A__B__x__y", "C__D__x__y"):
        (cache_dir / f"{name}.json").write_text(
            json.dumps({"issues": [], "expires_at": time.time() + 600}),
            encoding="utf-8",
        )

    result = await tapps_linear_snapshot_invalidate()
    assert result["success"] is True
    assert result["data"]["removed"] == 2
    assert list(cache_dir.glob("*.json")) == []


@pytest.mark.asyncio
async def test_invalidate_then_get_returns_miss(
    tmp_path: Path, mock_load_settings: Any
) -> None:
    await tapps_linear_snapshot_put(
        team="T",
        project="P",
        issues_json=json.dumps([{"id": "x"}]),
        state="backlog",
    )
    hit = await tapps_linear_snapshot_get(team="T", project="P", state="backlog")
    assert hit["data"]["cached"] is True

    await tapps_linear_snapshot_invalidate(team="T", project="P")
    miss = await tapps_linear_snapshot_get(team="T", project="P", state="backlog")
    assert miss["data"]["cached"] is False

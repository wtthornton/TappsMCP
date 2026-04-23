"""Tests for server_linear_tools (TAP-964)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pydantic import SecretStr

from tapps_mcp.server_linear_tools import (
    _cache_dir,
    _cache_key,
    _cache_read,
    _cache_write,
    _filter_hash,
    _ttl_for_state,
    tapps_linear_snapshot,
    tapps_linear_snapshot_invalidate,
)


@pytest.fixture
def fake_settings(tmp_path: Path) -> Any:
    """Return a settings-like stub with a tmp_path project_root."""

    class _Stub:
        project_root = tmp_path
        linear_api_key: SecretStr | None = SecretStr("lin_api_test_token")
        linear_api_url: str = "https://api.linear.app/graphql"
        linear_cache_ttl_open_seconds: int = 300
        linear_cache_ttl_closed_seconds: int = 3600
        tool_timeout: int = 30

    return _Stub()


@pytest.fixture
def mock_load_settings(fake_settings: Any) -> Any:
    with patch(
        "tapps_mcp.server_linear_tools.load_settings", return_value=fake_settings
    ) as m:
        yield m


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


@pytest.mark.asyncio
async def test_snapshot_requires_team_and_project(mock_load_settings: Any) -> None:
    result = await tapps_linear_snapshot(team="", project="myproj")
    assert result["success"] is False
    assert result["error"]["code"] == "invalid_input"


@pytest.mark.asyncio
async def test_snapshot_degrades_when_api_key_missing(
    tmp_path: Path, fake_settings: Any
) -> None:
    fake_settings.linear_api_key = None
    with patch(
        "tapps_mcp.server_linear_tools.load_settings", return_value=fake_settings
    ):
        result = await tapps_linear_snapshot(team="T", project="P")
    assert result["success"] is True
    assert result["degraded"] is True
    assert "Set TAPPS_MCP_LINEAR_API_KEY" in result["data"]["hint"]


@pytest.mark.asyncio
async def test_snapshot_cache_miss_fetches_and_caches(
    tmp_path: Path, mock_load_settings: Any
) -> None:
    fake_nodes = [{"id": "LIN-1", "identifier": "TAP-1", "title": "Test"}]
    mock_response = AsyncMock()
    mock_response.raise_for_status = lambda: None
    mock_response.json = lambda: {"data": {"issues": {"nodes": fake_nodes}}}

    class _MockClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> _MockClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def post(self, *args: Any, **kwargs: Any) -> Any:
            return mock_response

    with patch("tapps_mcp.server_linear_tools.httpx.AsyncClient", _MockClient):
        result = await tapps_linear_snapshot(team="T", project="P", state="backlog")

    assert result["success"] is True
    assert result["data"]["from_cache"] is False
    assert result["data"]["issues"] == fake_nodes
    cache_dir = _cache_dir(tmp_path)
    cache_files = list(cache_dir.glob("*.json"))
    assert len(cache_files) == 1


@pytest.mark.asyncio
async def test_snapshot_cache_hit_skips_http(
    tmp_path: Path, mock_load_settings: Any
) -> None:
    cached_issues = [{"id": "LIN-42", "title": "Already cached"}]
    cache_dir = _cache_dir(tmp_path)
    fhash = _filter_hash(state="backlog", label="", limit=50)
    key = _cache_key("T", "P", "backlog", fhash)
    _cache_write(
        cache_dir,
        key,
        {
            "issues": cached_issues,
            "expires_at": time.time() + 600,
            "cached_at": time.time(),
        },
    )

    async def _fail_post(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("HTTP should not be called on cache hit")

    class _NoHttpClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> _NoHttpClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        post = _fail_post

    with patch("tapps_mcp.server_linear_tools.httpx.AsyncClient", _NoHttpClient):
        result = await tapps_linear_snapshot(team="T", project="P", state="backlog")

    assert result["success"] is True
    assert result["data"]["from_cache"] is True
    assert result["data"]["issues"] == cached_issues


@pytest.mark.asyncio
async def test_snapshot_expired_cache_refetches(
    tmp_path: Path, mock_load_settings: Any
) -> None:
    cache_dir = _cache_dir(tmp_path)
    fhash = _filter_hash(state="backlog", label="", limit=50)
    key = _cache_key("T", "P", "backlog", fhash)
    _cache_write(
        cache_dir,
        key,
        {
            "issues": [{"id": "stale"}],
            "expires_at": time.time() - 60,
            "cached_at": time.time() - 1000,
        },
    )

    fresh_nodes = [{"id": "LIN-99", "identifier": "TAP-99", "title": "Fresh"}]
    mock_response = AsyncMock()
    mock_response.raise_for_status = lambda: None
    mock_response.json = lambda: {"data": {"issues": {"nodes": fresh_nodes}}}

    class _MockClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> _MockClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def post(self, *args: Any, **kwargs: Any) -> Any:
            return mock_response

    with patch("tapps_mcp.server_linear_tools.httpx.AsyncClient", _MockClient):
        result = await tapps_linear_snapshot(team="T", project="P", state="backlog")

    assert result["success"] is True
    assert result["data"]["from_cache"] is False
    assert result["data"]["issues"] == fresh_nodes


@pytest.mark.asyncio
async def test_snapshot_http_error_degrades_gracefully(
    mock_load_settings: Any,
) -> None:
    class _ErrClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> _ErrClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def post(self, *args: Any, **kwargs: Any) -> Any:
            raise httpx.ConnectError("connection refused")

    with patch("tapps_mcp.server_linear_tools.httpx.AsyncClient", _ErrClient):
        result = await tapps_linear_snapshot(team="T", project="P")

    assert result["success"] is True
    assert result["degraded"] is True
    assert result["data"]["fetch_error"]
    assert result["data"]["from_cache"] is False


@pytest.mark.asyncio
async def test_invalidate_removes_team_project_entries(
    tmp_path: Path, mock_load_settings: Any
) -> None:
    cache_dir = _cache_dir(tmp_path)
    # Seed two entries for team T project P, one for a different team.
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

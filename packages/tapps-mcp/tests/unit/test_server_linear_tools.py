"""Tests for server_linear_tools (TAP-964).

Post-rework: tapps-mcp is a cache, not a Linear client. These tests
cover the ``_get`` / ``_put`` / ``_invalidate`` tool surface and the
cache primitives.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from tapps_mcp.server_linear_tools import (
    _CACHE_MAX_FILES,
    _COMPACT_FIELDS,
    _cache_dir,
    _cache_key,
    _cache_read,
    _cache_write,
    _compact_issue,
    _filter_hash,
    _prune_linear_snapshot_cache,
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


def test_resolve_cache_key_differs_on_identity_inputs() -> None:
    # team, project, and label still change the key (slice identity).
    base = _resolve_cache_key("T", "P", "backlog", "", 50)
    assert _resolve_cache_key("OTHER", "P", "backlog", "", 50) != base
    assert _resolve_cache_key("T", "OTHER", "backlog", "", 50) != base
    assert _resolve_cache_key("T", "P", "backlog", "bug", 50) != base


def test_resolve_cache_key_collapses_open_aliases() -> None:
    # TAP-4588: every open-bucket alias resolves to ONE canonical key so the
    # payload cache self-hits regardless of which alias the caller used.
    base = _resolve_cache_key("T", "P", "backlog", "", 50)
    for alias in ("", "open", "unstarted", "started", "triage", "BACKLOG"):
        assert _resolve_cache_key("T", "P", alias, "", 50) == base


def test_resolve_cache_key_ignores_limit() -> None:
    # TAP-4588: limit is enforced at read time (superset fallback), not baked
    # into the key — so a larger-limit write and a smaller-limit read share it.
    base = _resolve_cache_key("T", "P", "backlog", "", 50)
    assert _resolve_cache_key("T", "P", "backlog", "", 100) == base
    assert _resolve_cache_key("T", "P", "backlog", "", 25) == base


def test_resolve_cache_key_isolates_closed_buckets() -> None:
    # TAP-4588: completed / canceled stay distinct from open and each other.
    open_key = _resolve_cache_key("T", "P", "open", "", 50)
    completed = _resolve_cache_key("T", "P", "completed", "", 50)
    canceled = _resolve_cache_key("T", "P", "canceled", "", 50)
    assert completed != open_key
    assert canceled != open_key
    assert completed != canceled


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


def test_prune_removes_files_older_than_ttl_multiplier(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    ttl_open = 300
    stale_path = cache_dir / "stale.json"
    stale_path.write_text("{}", encoding="utf-8")
    old = time.time() - (ttl_open * 10 + 60)
    os.utime(stale_path, (old, old))
    assert time.time() - stale_path.stat().st_mtime > ttl_open * 10

    fresh_path = cache_dir / "fresh.json"
    fresh_path.write_text("{}", encoding="utf-8")

    removed = _prune_linear_snapshot_cache(cache_dir, ttl_open=ttl_open, ttl_closed=3600)
    assert removed == 1
    assert not stale_path.exists()
    assert fresh_path.exists()


def test_prune_lru_evicts_beyond_cap(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    now = time.time()
    paths: list[Path] = []
    for i in range(_CACHE_MAX_FILES + 1):
        path = cache_dir / f"entry_{i:04d}.json"
        path.write_text("{}", encoding="utf-8")
        os.utime(path, (now - i, now - i))
        paths.append(path)

    removed = _prune_linear_snapshot_cache(cache_dir, ttl_open=300, ttl_closed=3600)
    assert removed == 1
    assert len(list(cache_dir.glob("*.json"))) == _CACHE_MAX_FILES
    assert not paths[-1].exists()


@pytest.mark.asyncio
async def test_get_prunes_stale_files_on_access(
    tmp_path: Path, mock_load_settings: Any
) -> None:
    cache_dir = _cache_dir(tmp_path)
    stale_path = cache_dir / "old_slice.json"
    stale_path.write_text("{}", encoding="utf-8")
    old = time.time() - (mock_load_settings.linear_cache_ttl_open_seconds * 10 + 5)
    os.utime(stale_path, (old, old))

    await tapps_linear_snapshot_get(team="T", project="P", state="backlog")
    assert not stale_path.exists()


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


# ---------------------------------------------------------------------------
# compact projection tests (TAP-2437)
# ---------------------------------------------------------------------------

_HEAVY_ISSUE: dict[str, Any] = {
    "id": "LIN-99",
    "identifier": "TAP-99",
    "title": "Heavy issue",
    "state": {"name": "Backlog", "type": "backlog"},
    "priority": {"value": 2, "name": "High"},
    "estimate": {"value": 3, "name": "3 Points"},
    "assignee": {"name": "Alice"},
    "parent": None,
    # Heavy fields that compact projection must strip:
    "description": "## Long description\n\n" + "x" * 1000,
    "comments": [{"body": "comment"} for _ in range(10)],
    "attachments": [{"url": "https://example.com"}],
    "history": [{"event": "created"}],
    "labels": ["Bug", "P2"],
    "url": "https://linear.app/...",
    "createdAt": "2026-01-01T00:00:00Z",
    "updatedAt": "2026-01-02T00:00:00Z",
}


def test_compact_issue_returns_only_allowed_fields() -> None:
    result = _compact_issue(_HEAVY_ISSUE)
    assert set(result.keys()) == _COMPACT_FIELDS & set(_HEAVY_ISSUE.keys())
    for key in result:
        assert key in _COMPACT_FIELDS


def test_compact_issue_preserves_allowed_field_values() -> None:
    result = _compact_issue(_HEAVY_ISSUE)
    assert result["id"] == "LIN-99"
    assert result["identifier"] == "TAP-99"
    assert result["title"] == "Heavy issue"
    assert result["state"] == {"name": "Backlog", "type": "backlog"}


def test_compact_issue_excludes_heavy_fields() -> None:
    result = _compact_issue(_HEAVY_ISSUE)
    for heavy in ("description", "comments", "attachments", "history"):
        assert heavy not in result


@pytest.mark.asyncio
async def test_get_compact_projection_returns_projected_issues(
    tmp_path: Path, mock_load_settings: Any
) -> None:
    """snapshot_get with projection="compact" strips heavy fields."""
    cache_dir = _cache_dir(tmp_path)
    key = _resolve_cache_key("T", "P", "backlog", "", 50)
    _cache_write(
        cache_dir,
        key,
        {
            "issues": [_HEAVY_ISSUE],
            "expires_at": time.time() + 600,
            "cached_at": time.time() - 1,
        },
    )

    result = await tapps_linear_snapshot_get(
        team="T", project="P", state="backlog", projection="compact"
    )
    assert result["success"] is True
    assert result["data"]["cached"] is True
    assert result["data"]["projection"] == "compact"
    returned = result["data"]["issues"]
    assert len(returned) == 1
    issue = returned[0]
    for heavy in ("description", "comments", "attachments", "history"):
        assert heavy not in issue
    assert issue["id"] == "LIN-99"
    assert issue["title"] == "Heavy issue"


@pytest.mark.asyncio
async def test_get_full_projection_preserves_all_fields(
    tmp_path: Path, mock_load_settings: Any
) -> None:
    """snapshot_get with projection="full" (default) returns issues unchanged."""
    cache_dir = _cache_dir(tmp_path)
    key = _resolve_cache_key("T", "P", "backlog", "", 50)
    _cache_write(
        cache_dir,
        key,
        {
            "issues": [_HEAVY_ISSUE],
            "expires_at": time.time() + 600,
            "cached_at": time.time() - 1,
        },
    )

    result = await tapps_linear_snapshot_get(
        team="T", project="P", state="backlog", projection="full"
    )
    assert result["success"] is True
    assert result["data"]["issues"][0]["description"] == _HEAVY_ISSUE["description"]
    assert result["data"]["issues"][0]["comments"] == _HEAVY_ISSUE["comments"]


@pytest.mark.asyncio
async def test_get_default_projection_is_full(
    tmp_path: Path, mock_load_settings: Any
) -> None:
    """snapshot_get with no projection kwarg returns full issues (no data loss)."""
    cache_dir = _cache_dir(tmp_path)
    key = _resolve_cache_key("T", "P", "backlog", "", 50)
    _cache_write(
        cache_dir,
        key,
        {
            "issues": [_HEAVY_ISSUE],
            "expires_at": time.time() + 600,
            "cached_at": time.time() - 1,
        },
    )

    result = await tapps_linear_snapshot_get(team="T", project="P", state="backlog")
    assert result["success"] is True
    # Default path returns raw issues — projection key may be absent or "full".
    assert "description" in result["data"]["issues"][0]


@pytest.mark.asyncio
async def test_get_compact_byte_budget_50_issues(
    tmp_path: Path, mock_load_settings: Any
) -> None:
    """A 50-issue compact snapshot must serialise to under 48,000 bytes."""
    fifty_issues = [dict(_HEAVY_ISSUE, id=f"LIN-{i}", identifier=f"TAP-{i}") for i in range(50)]
    cache_dir = _cache_dir(tmp_path)
    key = _resolve_cache_key("T", "P", "backlog", "", 50)
    _cache_write(
        cache_dir,
        key,
        {
            "issues": fifty_issues,
            "expires_at": time.time() + 600,
            "cached_at": time.time() - 1,
        },
    )

    result = await tapps_linear_snapshot_get(
        team="T", project="P", state="backlog", projection="compact"
    )
    assert result["success"] is True
    issues_json = json.dumps(result["data"]["issues"])
    assert len(issues_json) < 48_000, (
        f"Compact 50-issue payload too large: {len(issues_json)} bytes (limit 48,000)"
    )


# ---------------------------------------------------------------------------
# TAP-4588: reader/writer key convergence (canonicalization, superset limit,
# poisoning guard). These prove the payload cache actually self-hits.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_open_hits_put_under_concrete_open_state(
    tmp_path: Path, mock_load_settings: Any
) -> None:
    """get(state='open') HITS a put made under state='' / 'started'.

    Before TAP-4588 each alias wrote a distinct file, so this missed.
    """
    stored = json.dumps([{"id": "LIN-1", "title": "open work"}])
    # Writer uses the empty / concrete-open aliases the auto-populate hook and
    # skills actually produce.
    put_empty = await tapps_linear_snapshot_put(
        team="T", project="P", issues_json=stored, state=""
    )
    assert put_empty["data"]["stored"] is True

    got = await tapps_linear_snapshot_get(team="T", project="P", state="open")
    assert got["data"]["cached"] is True
    assert got["data"]["issues"] == [{"id": "LIN-1", "title": "open work"}]

    # And the reverse: a put under a concrete open state also serves get('open').
    put_started = await tapps_linear_snapshot_put(
        team="T", project="P", issues_json=stored, state="started"
    )
    assert put_started["data"]["cache_key"] == got["data"]["cache_key"]


@pytest.mark.asyncio
async def test_get_smaller_limit_hits_larger_cached_superset(
    tmp_path: Path, mock_load_settings: Any
) -> None:
    """get(limit=50) HITS a cached limit=150 snapshot, truncated."""
    issues = [{"id": f"LIN-{i}"} for i in range(150)]
    put = await tapps_linear_snapshot_put(
        team="T", project="P", issues_json=json.dumps(issues), state="open", limit=150
    )
    assert put["data"]["stored"] is True

    got = await tapps_linear_snapshot_get(
        team="T", project="P", state="open", limit=50
    )
    assert got["data"]["cached"] is True
    assert got["data"]["served_from_superset"] is True
    assert len(got["data"]["issues"]) == 50
    assert got["data"]["issues"][0]["id"] == "LIN-0"


@pytest.mark.asyncio
async def test_get_larger_limit_misses_smaller_cached(
    tmp_path: Path, mock_load_settings: Any
) -> None:
    """get(limit=150) MISSES a cached limit=50 snapshot (can't serve larger)."""
    issues = [{"id": f"LIN-{i}"} for i in range(50)]
    await tapps_linear_snapshot_put(
        team="T", project="P", issues_json=json.dumps(issues), state="open", limit=50
    )

    got = await tapps_linear_snapshot_get(
        team="T", project="P", state="open", limit=150
    )
    assert got["data"]["cached"] is False


@pytest.mark.asyncio
async def test_get_exact_limit_hits_not_flagged_superset(
    tmp_path: Path, mock_load_settings: Any
) -> None:
    """Equal stored/requested limit hits without the superset flag."""
    issues = [{"id": f"LIN-{i}"} for i in range(50)]
    await tapps_linear_snapshot_put(
        team="T", project="P", issues_json=json.dumps(issues), state="open", limit=50
    )
    got = await tapps_linear_snapshot_get(
        team="T", project="P", state="open", limit=50
    )
    assert got["data"]["cached"] is True
    assert got["data"]["served_from_superset"] is False


@pytest.mark.asyncio
async def test_closed_buckets_isolated_from_open(
    tmp_path: Path, mock_load_settings: Any
) -> None:
    """A completed-state snapshot never satisfies an open-slice get."""
    closed = json.dumps([{"id": "LIN-done", "title": "done"}])
    await tapps_linear_snapshot_put(
        team="T", project="P", issues_json=closed, state="completed"
    )
    # get for the open slice must MISS — different canonical key.
    got_open = await tapps_linear_snapshot_get(team="T", project="P", state="open")
    assert got_open["data"]["cached"] is False
    # completed and canceled are isolated from each other too.
    got_canceled = await tapps_linear_snapshot_get(
        team="T", project="P", state="canceled"
    )
    assert got_canceled["data"]["cached"] is False
    # but the completed get itself hits.
    got_completed = await tapps_linear_snapshot_get(
        team="T", project="P", state="completed"
    )
    assert got_completed["data"]["cached"] is True


@pytest.mark.asyncio
async def test_auto_populated_empty_payload_is_miss_not_false_hit(
    tmp_path: Path, mock_load_settings: Any
) -> None:
    """An auto_populated payload with issues==[] returns a miss, not 0 issues.

    Guards against poisoning: list_issues(state='open') returns [] (invalid
    Linear state); the hook may cache that empty list. A later get must not
    report a confident empty hit off it.
    """
    cache_dir = _cache_dir(tmp_path)
    key = _resolve_cache_key("T", "P", "open", "", 50)
    _cache_write(
        cache_dir,
        key,
        {
            "issues": [],
            "expires_at": time.time() + 600,
            "cached_at": time.time() - 1,
            "state": "open",
            "team": "T",
            "project": "P",
            "auto_populated": True,
            "limit": 50,
        },
    )
    got = await tapps_linear_snapshot_get(team="T", project="P", state="open")
    assert got["data"]["cached"] is False


@pytest.mark.asyncio
async def test_manual_empty_put_is_still_a_hit(
    tmp_path: Path, mock_load_settings: Any
) -> None:
    """A manual (non-auto) empty put is a legitimate empty hit.

    The poisoning guard only distrusts auto_populated empties — an agent that
    explicitly put([]) for a genuinely-empty slice should still self-hit.
    """
    put = await tapps_linear_snapshot_put(
        team="T", project="P", issues_json="[]", state="completed"
    )
    assert put["data"]["stored"] is True
    got = await tapps_linear_snapshot_get(team="T", project="P", state="completed")
    assert got["data"]["cached"] is True
    assert got["data"]["issues"] == []

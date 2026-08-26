"""``snapshot_get`` projection honesty (TAP-6581).

``tapps_linear_snapshot_get`` used to echo the caller's requested ``projection``
straight back into the response. A cache auto-populated from a narrow
``list_issues(fields=["id"])`` call was therefore served as
``projection: "full"`` with 36 rows of ``{"id": ...}`` and nothing else,
``cached: true``, for the whole 30-minute open-bucket TTL.

These tests pin the honest contract: the response names the projection the
STORED ROWS actually satisfy, and rows that satisfy none of them MISS. Kept in
its own module rather than appended to ``test_server_linear_tools.py``, which is
already over the maintainability gate.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from tapps_mcp.server_linear_tools import (
    _cache_dir,
    _cache_write,
    _resolve_cache_key,
    _stored_projection,
    tapps_linear_snapshot_get,
)

pytestmark = pytest.mark.usefixtures("envelope_guard")

_HEAVY_ISSUE: dict[str, Any] = {
    "id": "LIN-99",
    "identifier": "TAP-99",
    "title": "Heavy issue",
    "priority": 2,
    "description": "x" * 4000,
    "comments": [{"body": "y" * 500}],
    "attachments": [{"url": "https://example.test/a"}],
    "history": [{"event": "created"}],
}


@pytest.fixture
def mock_load_settings(tmp_path: Path) -> Any:
    class _Stub:
        project_root = tmp_path
        linear_cache_ttl_open_seconds = 1800
        linear_cache_ttl_closed_seconds = 3600

    with patch("tapps_mcp.server_linear_tools.load_settings", return_value=_Stub()) as m:
        yield m


def _write_open_snapshot(tmp_path: Path, issues: list[dict[str, Any]]) -> None:
    """Plant a live-TTL open-bucket snapshot the way the auto-populate hook does."""
    now = time.time()
    _cache_write(
        _cache_dir(tmp_path),
        _resolve_cache_key("T", "P", "open", "", 50),
        {
            "issues": issues,
            "cached_at": now,
            "expires_at": now + 1800,
            "auto_populated": True,
            "limit": 50,
        },
    )


@pytest.mark.asyncio
async def test_id_only_cache_is_never_reported_as_full(
    tmp_path: Path, mock_load_settings: Any
) -> None:
    """VAL-09 — the live repro.

    36 rows of ``{"id": ...}`` satisfy no projection at all, so the only honest
    answer is a miss; the caller must not be told ``full``.
    """
    _write_open_snapshot(tmp_path, [{"id": f"uuid-{n}"} for n in range(36)])

    got = await tapps_linear_snapshot_get(team="T", project="P", state="open")

    assert got["data"]["cached"] is False
    assert "projection" not in got["data"]
    assert got["data"]["miss_reason"] == "degraded_rows"


@pytest.mark.asyncio
async def test_full_request_over_compact_rows_reports_compact(
    tmp_path: Path, mock_load_settings: Any
) -> None:
    """Rows made only of compact fields cannot evidence a ``full`` projection."""
    _write_open_snapshot(
        tmp_path,
        [{"id": "u1", "identifier": "TAP-1", "title": "alpha", "priority": 2}],
    )

    got = await tapps_linear_snapshot_get(team="T", project="P", state="open", projection="full")

    assert got["data"]["cached"] is True
    assert got["data"]["projection"] == "compact"
    assert got["data"]["requested_projection"] == "full"
    assert got["data"]["projection_downgraded"] is True


@pytest.mark.asyncio
async def test_full_request_over_heavy_rows_still_reports_full(
    tmp_path: Path, mock_load_settings: Any
) -> None:
    """Negative path: an unpruned payload must not be downgraded."""
    _write_open_snapshot(tmp_path, [_HEAVY_ISSUE])

    got = await tapps_linear_snapshot_get(team="T", project="P", state="open", projection="full")

    assert got["data"]["projection"] == "full"
    assert got["data"]["projection_downgraded"] is False
    assert got["data"]["issues"][0]["description"] == _HEAVY_ISSUE["description"]


@pytest.mark.asyncio
async def test_compact_request_is_not_flagged_as_downgraded(
    tmp_path: Path, mock_load_settings: Any
) -> None:
    """Asking for compact and getting compact is not a downgrade."""
    _write_open_snapshot(tmp_path, [_HEAVY_ISSUE])

    got = await tapps_linear_snapshot_get(team="T", project="P", state="open", projection="compact")

    assert got["data"]["projection"] == "compact"
    assert got["data"]["requested_projection"] == "compact"
    assert got["data"]["projection_downgraded"] is False


@pytest.mark.asyncio
async def test_one_row_below_the_compact_floor_misses(
    tmp_path: Path, mock_load_settings: Any
) -> None:
    """A single unusable row taints the slice — a miss costs one API call."""
    _write_open_snapshot(tmp_path, [{"id": "u1", "title": "alpha"}, {"id": "u2"}])

    got = await tapps_linear_snapshot_get(team="T", project="P", state="open")

    assert got["data"]["cached"] is False
    assert got["data"]["miss_reason"] == "degraded_rows"


@pytest.mark.asyncio
async def test_plain_miss_names_its_reason(mock_load_settings: Any) -> None:
    """``miss_reason`` distinguishes an empty cache from a poisoned one."""
    got = await tapps_linear_snapshot_get(team="T", project="P", state="open")

    assert got["data"]["cached"] is False
    assert got["data"]["miss_reason"] == "not_cached"


def test_stored_projection_classifies_row_shapes() -> None:
    """Unit cover for the field-set check the handler reads."""
    assert _stored_projection([]) == "none"
    assert _stored_projection([{"id": "u1"}]) == "none"
    assert _stored_projection([{"title": "no identity"}]) == "none"
    assert _stored_projection(["not a dict"]) == "none"
    assert _stored_projection([{"id": "u1", "title": "a"}]) == "compact"
    assert _stored_projection([{"identifier": "TAP-1", "title": "a"}]) == "compact"
    assert _stored_projection([{"id": "u1", "title": "a", "description": "d"}]) == "full"
    # Mixed: one pruned row is enough to make "full" unprovable.
    assert (
        _stored_projection(
            [{"id": "u1", "title": "a", "description": "d"}, {"id": "u2", "title": "b"}]
        )
        == "compact"
    )

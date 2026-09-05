"""Stem coverage + smoke tests for server_linear_tools_handlers (TAP-5606)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tapps_mcp.server_linear_tools_handlers import (
    _record_call,
    _scan_snapshot_file,
    register,
    tapps_linear_snapshot_get,
    tapps_linear_snapshot_put,
)


def test_record_call_does_not_raise() -> None:
    _record_call("tapps_linear_snapshot_get")


def test_scan_snapshot_file_returns_none_for_expired(tmp_path: Path) -> None:
    cache_file = tmp_path / "snap.json"
    cache_file.write_text(
        json.dumps({"issues": [], "cached_at": 0, "expires_at": 0}), encoding="utf-8"
    )
    seen: dict[str, str] = {}
    assert _scan_snapshot_file(cache_file, time.time(), 0.0, seen) is None
    assert seen == {}


def test_scan_snapshot_file_collects_issue_status(tmp_path: Path) -> None:
    now = time.time()
    cache_file = tmp_path / "snap.json"
    cache_file.write_text(
        json.dumps(
            {
                "issues": [{"id": "LIN-1", "statusType": "Backlog"}],
                "cached_at": now,
                "expires_at": now + 600,
            }
        ),
        encoding="utf-8",
    )
    seen: dict[str, str] = {}
    cached_at = _scan_snapshot_file(cache_file, now, 0.0, seen)
    assert cached_at == now
    assert seen == {"LIN-1": "backlog"}


def test_register_gates_tools_by_allowed_set() -> None:
    mcp_instance = MagicMock()
    register(mcp_instance, frozenset({"tapps_linear_count"}))
    assert mcp_instance.tool.call_count == 1


@pytest.fixture
def fake_settings(tmp_path: Path) -> Any:
    class _Stub:
        project_root = tmp_path
        linear_cache_ttl_open_seconds: int = 300
        linear_cache_ttl_closed_seconds: int = 3600

    return _Stub()


@pytest.mark.asyncio
async def test_snapshot_put_id_only_rows_refuses_with_named_verdict(
    fake_settings: Any,
) -> None:
    """TAP-6636: id-only rows (no title) are below the compact floor and must
    not be stored as a plain ``stored: True`` hit."""
    with patch(
        "tapps_mcp.server_linear_tools.load_settings", return_value=fake_settings
    ):
        issues = [{"id": "LIN-1"}, {"id": "LIN-2"}]
        result = await tapps_linear_snapshot_put(
            team="T", project="P", issues_json=json.dumps(issues), state="backlog"
        )
        assert result["data"]["stored"] is False
        assert result["data"]["stored_projection"] == "none"
        get_result = await tapps_linear_snapshot_get(team="T", project="P", state="backlog")
        assert get_result["data"]["cached"] is False

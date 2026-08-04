"""Stem coverage + smoke tests for server_linear_tools_handlers (TAP-5606)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

from tapps_mcp.server_linear_tools_handlers import (
    _record_call,
    _scan_snapshot_file,
    register,
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

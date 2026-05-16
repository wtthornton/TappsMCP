"""TAP-1792: tapps_quick_check cache-hit path must run the same accounting and
response decoration as the cache-miss path.

Before the fix, a cache hit bypassed ``_with_nudges``,
``_attach_quick_check_structured_output``, ``_record_execution``, and the
``_record_call("tapps_quick_check", success=False)`` on a failing gate. A
cached failing file counted as a success in the checklist, and the cached
payload reached the LLM without ``next_steps`` or ``structuredContent``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.server_scoring_tools import tapps_quick_check


@pytest.fixture
def py_file(tmp_path: Path) -> Path:
    p = tmp_path / "sample.py"
    p.write_text(
        '"""module."""\n\n'
        'def add(a: int, b: int) -> int:\n'
        '    return a + b\n',
        encoding="utf-8",
    )
    return p


def _failing_payload() -> dict[str, Any]:
    return {
        "file_path": "sample.py",
        "overall_score": 42,
        "gate_passed": False,
        "security_passed": True,
        "elapsed_ms": 11,
        "security_issue_count": 0,
        "__structured_content__": {
            "file_path": "sample.py",
            "overall_score": 42,
            "gate_passed": False,
            "security_passed": True,
        },
    }


@pytest.mark.asyncio
async def test_cache_hit_records_failure_when_gate_failed(py_file: Path) -> None:
    record_call = MagicMock()
    record_execution = MagicMock()
    with (
        patch("tapps_mcp.server._validate_file_path", return_value=py_file),
        patch(
            "tapps_mcp.server_scoring_tools.ensure_session_initialized",
            AsyncMock(return_value=None),
        ),
        patch(
            "tapps_mcp.tools.content_hash_cache.content_hash",
            return_value="abc",
        ),
        patch(
            "tapps_mcp.tools.content_hash_cache.get",
            return_value=_failing_payload(),
        ),
        patch("tapps_mcp.server._record_call", record_call),
        patch("tapps_mcp.server._record_execution", record_execution),
        patch("tapps_mcp.server._with_nudges", lambda _tool, resp, _ctx=None: resp),
    ):
        await tapps_quick_check(file_path=str(py_file))

    failure_calls = [
        c for c in record_call.call_args_list
        if c.kwargs.get("success") is False and c.args == ("tapps_quick_check",)
    ]
    assert failure_calls, (
        "TAP-1792: cache-hit on a failing payload must call "
        "_record_call('tapps_quick_check', success=False)"
    )
    assert record_execution.call_count == 1, (
        "TAP-1792: cache-hit path must record execution so timings stay calibrated"
    )


@pytest.mark.asyncio
async def test_cache_hit_does_not_record_failure_on_clean_payload(py_file: Path) -> None:
    payload = _failing_payload()
    payload["gate_passed"] = True
    payload["security_passed"] = True
    record_call = MagicMock()
    with (
        patch("tapps_mcp.server._validate_file_path", return_value=py_file),
        patch(
            "tapps_mcp.server_scoring_tools.ensure_session_initialized",
            AsyncMock(return_value=None),
        ),
        patch(
            "tapps_mcp.tools.content_hash_cache.content_hash",
            return_value="abc",
        ),
        patch(
            "tapps_mcp.tools.content_hash_cache.get",
            return_value=payload,
        ),
        patch("tapps_mcp.server._record_call", record_call),
        patch("tapps_mcp.server._record_execution", MagicMock()),
        patch("tapps_mcp.server._with_nudges", lambda _tool, resp, _ctx=None: resp),
    ):
        await tapps_quick_check(file_path=str(py_file))

    failure_calls = [
        c for c in record_call.call_args_list
        if c.kwargs.get("success") is False
    ]
    assert not failure_calls, (
        "Cache-hit on a passing payload must NOT call _record_call(success=False)"
    )


@pytest.mark.asyncio
async def test_cache_hit_response_carries_structured_content(py_file: Path) -> None:
    with (
        patch("tapps_mcp.server._validate_file_path", return_value=py_file),
        patch(
            "tapps_mcp.server_scoring_tools.ensure_session_initialized",
            AsyncMock(return_value=None),
        ),
        patch(
            "tapps_mcp.tools.content_hash_cache.content_hash",
            return_value="abc",
        ),
        patch(
            "tapps_mcp.tools.content_hash_cache.get",
            return_value=_failing_payload(),
        ),
        patch("tapps_mcp.server._record_call", MagicMock()),
        patch("tapps_mcp.server._record_execution", MagicMock()),
        patch("tapps_mcp.server._with_nudges", lambda _tool, resp, _ctx=None: resp),
    ):
        resp = await tapps_quick_check(file_path=str(py_file))

    assert "structuredContent" in resp, (
        "Cache-hit response must include structuredContent so LLM consumers see the gate result"
    )
    assert resp["structuredContent"]["gate_passed"] is False
    # __structured_content__ is a private cache stash — it should not leak into the data payload.
    assert "__structured_content__" not in resp["data"]


@pytest.mark.asyncio
async def test_cache_hit_response_passes_through_with_nudges(py_file: Path) -> None:
    captured_kwargs: dict[str, Any] = {}

    def fake_with_nudges(tool: str, resp: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        captured_kwargs.update(ctx)
        resp.setdefault("data", {})["next_steps"] = ["sentinel"]
        return resp

    with (
        patch("tapps_mcp.server._validate_file_path", return_value=py_file),
        patch(
            "tapps_mcp.server_scoring_tools.ensure_session_initialized",
            AsyncMock(return_value=None),
        ),
        patch(
            "tapps_mcp.tools.content_hash_cache.content_hash",
            return_value="abc",
        ),
        patch(
            "tapps_mcp.tools.content_hash_cache.get",
            return_value=_failing_payload(),
        ),
        patch("tapps_mcp.server._record_call", MagicMock()),
        patch("tapps_mcp.server._record_execution", MagicMock()),
        patch("tapps_mcp.server._with_nudges", fake_with_nudges),
    ):
        resp = await tapps_quick_check(file_path=str(py_file))

    assert resp["data"].get("next_steps") == ["sentinel"], (
        "Cache-hit response must be routed through _with_nudges so next_steps land on it"
    )
    assert captured_kwargs.get("gate_passed") is False
    assert captured_kwargs.get("security_passed") is True

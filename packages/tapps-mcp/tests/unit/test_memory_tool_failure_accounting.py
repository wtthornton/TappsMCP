"""TAP-1801: tapps_memory must record success=False on its error paths.

The handler eagerly called ``_record_call("tapps_memory")`` (default
success=True) before validating ``action`` or initializing the store. Errors
short-circuited via ``error_response`` without ever flipping that counter, so
a session whose only tapps_memory invocation hit an error still satisfied
any checklist policy listing tapps_memory as required/recommended.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp import server_memory_tools


def _record_call_capture() -> tuple[list[bool], MagicMock]:
    """Return a (records, mock) pair where ``records`` is a per-call `success` value."""
    records: list[bool] = []

    def fake(_tool_name: str, *, success: bool = True) -> None:
        records.append(success)

    mock = MagicMock(side_effect=fake)
    return records, mock


@pytest.mark.asyncio
async def test_invalid_action_records_failure() -> None:
    records, fake_record = _record_call_capture()
    with (
        patch("tapps_mcp.server_memory_tools._record_call", fake_record),
        patch(
            "tapps_mcp.server_memory_tools.ensure_session_initialized",
            AsyncMock(return_value=None),
        ),
    ):
        resp = await server_memory_tools.tapps_memory(action="not_an_action")

    assert resp["success"] is False
    assert resp["error"]["code"] == "invalid_action"
    assert records == [True, False], (
        "TAP-1801: invalid_action path must follow the eager success=True with "
        "an explicit success=False so the checklist counts the call as failed"
    )


@pytest.mark.asyncio
async def test_store_init_failure_records_failure() -> None:
    records, fake_record = _record_call_capture()

    def _boom() -> object:
        raise RuntimeError("simulated store init failure")

    with (
        patch("tapps_mcp.server_memory_tools._record_call", fake_record),
        patch(
            "tapps_mcp.server_memory_tools.ensure_session_initialized",
            AsyncMock(return_value=None),
        ),
        patch(
            "tapps_mcp.server_memory_tools._get_memory_store",
            side_effect=RuntimeError("simulated store init failure"),
        ),
    ):
        # TAP-1993: use lifecycle action to reach the store-init path.
        resp = await server_memory_tools.tapps_memory(action="session_start_capture")

    assert resp["success"] is False
    assert resp["error"]["code"] == "store_init_failed"
    assert records == [True, False]


@pytest.mark.asyncio
async def test_action_dispatch_crash_records_failure() -> None:
    records, fake_record = _record_call_capture()

    # TAP-1993: lifecycle actions go through _ASYNC_DISPATCH, so the crashing
    # handler must be async and patched into _ASYNC_DISPATCH.
    async def _crashing_handler(_store: object, _params: object) -> object:
        raise RuntimeError("simulated dispatch failure")

    fake_store = MagicMock()
    with (
        patch("tapps_mcp.server_memory_tools._record_call", fake_record),
        patch(
            "tapps_mcp.server_memory_tools.ensure_session_initialized",
            AsyncMock(return_value=None),
        ),
        patch(
            "tapps_mcp.server_memory_tools._get_memory_store",
            return_value=fake_store,
        ),
        patch.dict(
            server_memory_tools._ASYNC_DISPATCH,
            {"session_start_capture": _crashing_handler},
            clear=False,
        ),
    ):
        resp = await server_memory_tools.tapps_memory(action="session_start_capture")

    assert resp["success"] is False
    assert resp["error"]["code"] == "action_failed"
    assert records == [True, False]


@pytest.mark.asyncio
async def test_successful_call_still_records_success_only() -> None:
    """The fix must not record a spurious failure on the happy path."""
    records, fake_record = _record_call_capture()

    fake_store = MagicMock()

    with (
        patch("tapps_mcp.server_memory_tools._record_call", fake_record),
        patch(
            "tapps_mcp.server_memory_tools.ensure_session_initialized",
            AsyncMock(return_value=None),
        ),
        patch(
            "tapps_mcp.server_memory_tools._get_memory_store",
            return_value=fake_store,
        ),
        patch.dict(
            server_memory_tools._ASYNC_DISPATCH,
            {"session_start_capture": AsyncMock(return_value={"indexed": True})},
            clear=False,
        ),
    ):
        resp = await server_memory_tools.tapps_memory(action="session_start_capture")

    assert resp["success"] is True
    assert records == [True], (
        "Happy path must not record a spurious success=False"
    )

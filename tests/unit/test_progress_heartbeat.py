from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.server_pipeline_tools import _validate_progress_heartbeat

INTERVAL_PATCH = "tapps_mcp.server_pipeline_tools._PROGRESS_HEARTBEAT_INTERVAL"


@pytest.mark.asyncio
async def test_heartbeat_sends_progress() -> None:
    """Heartbeat calls report_progress at least twice over ~0.3s with 0.1s interval."""
    ctx = MagicMock()
    ctx.report_progress = AsyncMock()
    stop_event = asyncio.Event()
    start_ns = time.perf_counter_ns()

    with patch(INTERVAL_PATCH, 0.1):
        task = asyncio.create_task(
            _validate_progress_heartbeat(ctx, 3, start_ns, stop_event)
        )
        await asyncio.sleep(0.35)
        stop_event.set()
        await task

    assert ctx.report_progress.call_count >= 2
    for call in ctx.report_progress.call_args_list:
        assert isinstance(call.kwargs["progress"], float)
        assert call.kwargs["total"] is None
        assert "in progress" in call.kwargs["message"]


@pytest.mark.asyncio
async def test_heartbeat_stops_on_event() -> None:
    """Heartbeat returns immediately when stop_event is already set."""
    ctx = MagicMock()
    ctx.report_progress = AsyncMock()
    stop_event = asyncio.Event()
    stop_event.set()
    start_ns = time.perf_counter_ns()

    with patch(INTERVAL_PATCH, 0.1):
        await _validate_progress_heartbeat(ctx, 3, start_ns, stop_event)

    assert ctx.report_progress.call_count == 0


@pytest.mark.asyncio
async def test_heartbeat_noop_when_no_report_progress() -> None:
    """Heartbeat returns immediately when ctx has no report_progress attribute."""
    ctx = MagicMock(spec=[])
    stop_event = asyncio.Event()
    start_ns = time.perf_counter_ns()

    # Should return immediately without error
    await _validate_progress_heartbeat(ctx, 3, start_ns, stop_event)


@pytest.mark.asyncio
async def test_heartbeat_noop_when_report_not_callable() -> None:
    """Heartbeat returns immediately when report_progress is not callable."""
    ctx = MagicMock()
    ctx.report_progress = "not_callable"
    stop_event = asyncio.Event()
    start_ns = time.perf_counter_ns()

    await _validate_progress_heartbeat(ctx, 3, start_ns, stop_event)


@pytest.mark.asyncio
async def test_heartbeat_survives_report_exception() -> None:
    """Heartbeat keeps running even when report_progress raises."""
    ctx = MagicMock()
    ctx.report_progress = AsyncMock(side_effect=RuntimeError("boom"))
    stop_event = asyncio.Event()
    start_ns = time.perf_counter_ns()

    with patch(INTERVAL_PATCH, 0.1):
        task = asyncio.create_task(
            _validate_progress_heartbeat(ctx, 3, start_ns, stop_event)
        )
        await asyncio.sleep(0.25)
        stop_event.set()
        await task

    # Function completed without propagating the exception
    assert ctx.report_progress.call_count >= 1


@pytest.mark.asyncio
async def test_heartbeat_progress_increases_monotonically() -> None:
    """Each reported progress value is greater than the previous one."""
    ctx = MagicMock()
    ctx.report_progress = AsyncMock()
    stop_event = asyncio.Event()
    start_ns = time.perf_counter_ns()

    with patch(INTERVAL_PATCH, 0.05):
        task = asyncio.create_task(
            _validate_progress_heartbeat(ctx, 5, start_ns, stop_event)
        )
        await asyncio.sleep(0.3)
        stop_event.set()
        await task

    values = [call.kwargs["progress"] for call in ctx.report_progress.call_args_list]
    assert len(values) >= 2, f"Expected >= 2 progress reports, got {len(values)}"
    for i in range(1, len(values)):
        assert values[i] > values[i - 1], (
            f"Progress not monotonic: {values[i]} <= {values[i - 1]}"
        )

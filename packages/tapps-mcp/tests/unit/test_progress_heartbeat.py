from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.server_pipeline_tools import _ProgressTracker, _validate_progress_heartbeat

INTERVAL_PATCH = "tapps_mcp.server_pipeline_tools._PROGRESS_HEARTBEAT_INTERVAL"


@pytest.mark.asyncio
async def test_heartbeat_sends_progress_without_tracker() -> None:
    """Heartbeat falls back to elapsed-time progress when no tracker is given."""
    ctx = MagicMock()
    ctx.report_progress = AsyncMock()
    stop_event = asyncio.Event()
    start_ns = time.perf_counter_ns()

    with patch(INTERVAL_PATCH, 0.1):
        task = asyncio.create_task(_validate_progress_heartbeat(ctx, 3, start_ns, stop_event))
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
        task = asyncio.create_task(_validate_progress_heartbeat(ctx, 3, start_ns, stop_event))
        await asyncio.sleep(0.25)
        stop_event.set()
        await task

    # Function completed without propagating the exception
    assert ctx.report_progress.call_count >= 1


@pytest.mark.asyncio
async def test_heartbeat_progress_increases_monotonically() -> None:
    """Each reported progress value is greater than the previous one (no tracker)."""
    ctx = MagicMock()
    ctx.report_progress = AsyncMock()
    stop_event = asyncio.Event()
    start_ns = time.perf_counter_ns()

    with patch(INTERVAL_PATCH, 0.05):
        task = asyncio.create_task(_validate_progress_heartbeat(ctx, 5, start_ns, stop_event))
        await asyncio.sleep(0.3)
        stop_event.set()
        await task

    values = [call.kwargs["progress"] for call in ctx.report_progress.call_args_list]
    assert len(values) >= 2, f"Expected >= 2 progress reports, got {len(values)}"
    for i in range(1, len(values)):
        assert values[i] > values[i - 1], f"Progress not monotonic: {values[i]} <= {values[i - 1]}"


# --- Tracker-based progress tests ---


@pytest.mark.asyncio
async def test_heartbeat_reports_file_count_progress() -> None:
    """When a tracker is provided, progress equals completed count and total is set."""
    ctx = MagicMock()
    ctx.report_progress = AsyncMock()
    stop_event = asyncio.Event()
    start_ns = time.perf_counter_ns()
    tracker = _ProgressTracker(total=5, completed=3, last_file="scorer.py")

    with patch(INTERVAL_PATCH, 0.1):
        task = asyncio.create_task(
            _validate_progress_heartbeat(ctx, 5, start_ns, stop_event, tracker)
        )
        await asyncio.sleep(0.15)
        stop_event.set()
        await task

    assert ctx.report_progress.call_count >= 1
    call = ctx.report_progress.call_args_list[0]
    assert call.kwargs["progress"] == 3
    assert call.kwargs["total"] == 5


@pytest.mark.asyncio
async def test_heartbeat_message_includes_last_file() -> None:
    """Heartbeat message includes the last completed filename from the tracker."""
    ctx = MagicMock()
    ctx.report_progress = AsyncMock()
    stop_event = asyncio.Event()
    start_ns = time.perf_counter_ns()
    tracker = _ProgressTracker(total=10, completed=4, last_file="gates.py")

    with patch(INTERVAL_PATCH, 0.1):
        task = asyncio.create_task(
            _validate_progress_heartbeat(ctx, 10, start_ns, stop_event, tracker)
        )
        await asyncio.sleep(0.15)
        stop_event.set()
        await task

    assert ctx.report_progress.call_count >= 1
    msg = ctx.report_progress.call_args_list[0].kwargs["message"]
    assert "4/10" in msg
    assert "gates.py" in msg


@pytest.mark.asyncio
async def test_heartbeat_message_no_file_before_first_completion() -> None:
    """When no file has completed yet, message omits the filename parenthetical."""
    ctx = MagicMock()
    ctx.report_progress = AsyncMock()
    stop_event = asyncio.Event()
    start_ns = time.perf_counter_ns()
    tracker = _ProgressTracker(total=3, completed=0, last_file="")

    with patch(INTERVAL_PATCH, 0.1):
        task = asyncio.create_task(
            _validate_progress_heartbeat(ctx, 3, start_ns, stop_event, tracker)
        )
        await asyncio.sleep(0.15)
        stop_event.set()
        await task

    assert ctx.report_progress.call_count >= 1
    msg = ctx.report_progress.call_args_list[0].kwargs["message"]
    assert "0/3" in msg
    assert "(" not in msg


@pytest.mark.asyncio
async def test_heartbeat_reflects_tracker_updates() -> None:
    """Heartbeat picks up tracker mutations between intervals."""
    ctx = MagicMock()
    ctx.report_progress = AsyncMock()
    stop_event = asyncio.Event()
    start_ns = time.perf_counter_ns()
    tracker = _ProgressTracker(total=5, completed=0, last_file="")

    with patch(INTERVAL_PATCH, 0.1):
        task = asyncio.create_task(
            _validate_progress_heartbeat(ctx, 5, start_ns, stop_event, tracker)
        )
        # Let first heartbeat fire with completed=0
        await asyncio.sleep(0.15)
        # Simulate files completing
        tracker.completed = 3
        tracker.last_file = "server.py"
        # Let second heartbeat fire
        await asyncio.sleep(0.15)
        stop_event.set()
        await task

    assert ctx.report_progress.call_count >= 2
    first_call = ctx.report_progress.call_args_list[0]
    assert first_call.kwargs["progress"] == 0

    last_call = ctx.report_progress.call_args_list[-1]
    assert last_call.kwargs["progress"] == 3
    assert "server.py" in last_call.kwargs["message"]

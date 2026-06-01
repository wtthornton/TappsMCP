"""TAP-1943: Unit tests for _fire_validate_events — validate_changed KG event emission."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.tools.validate_changed import _BatchOutcome, _fire_validate_events, _TimedOutInfo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_outcome(
    *,
    all_passed: bool = True,
    total_sec: int = 0,
    file_paths: list[str] | None = None,
    scores: list[float] | None = None,
) -> _BatchOutcome:
    """Build a minimal _BatchOutcome for testing."""
    file_paths = file_paths or ["/project/src/foo.py"]
    scores = scores or [85.0] * len(file_paths)
    results = [
        {"file_path": fp, "overall_score": sc, "gate_passed": all_passed}
        for fp, sc in zip(file_paths, scores, strict=False)
    ]
    return _BatchOutcome(
        results=results,
        all_passed=all_passed,
        total_sec=total_sec,
        impact_data=None,
        timeout_info=_TimedOutInfo(timed_out=False, files_remaining=[]),
    )


def _make_paths(file_paths: list[str] | None = None) -> list[Path]:
    return [Path(p) for p in (file_paths or ["/project/src/foo.py"])]


# ---------------------------------------------------------------------------
# TestFireValidateEvents — unit tests for the helper itself
# ---------------------------------------------------------------------------


class TestFireValidateEvents:
    """Unit tests for _fire_validate_events (TAP-1943)."""

    def test_schedules_task_when_bridge_present(self) -> None:
        """create_task is called once when the bridge has record_kg_event."""
        mock_bridge = MagicMock()
        mock_bridge.record_kg_event = AsyncMock(return_value={"recorded": True})

        with (
            patch(
                "tapps_mcp.tools.validate_changed._get_brain_bridge",
                return_value=mock_bridge,
            ),
            patch(
                "tapps_mcp.tools.validate_changed.asyncio.create_task"
            ) as mock_task,
        ):
            _fire_validate_events(_make_paths(), _make_outcome(), elapsed_ms=42)

        mock_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_emits_validate_completed_event(self) -> None:
        """The emitted coroutine calls record_kg_event with validate_completed event type."""
        mock_bridge = MagicMock()
        mock_bridge.record_kg_event = AsyncMock(return_value={"recorded": True})
        captured: list[Any] = []

        def _capture_task(coro: Any) -> None:
            captured.append(coro)

        with (
            patch(
                "tapps_mcp.tools.validate_changed._get_brain_bridge",
                return_value=mock_bridge,
            ),
            patch(
                "tapps_mcp.tools.validate_changed.asyncio.create_task",
                side_effect=_capture_task,
            ),
        ):
            paths = _make_paths(["/project/src/a.py", "/project/src/b.py"])
            _fire_validate_events(paths, _make_outcome(file_paths=[str(p) for p in paths]), elapsed_ms=100)

            assert len(captured) == 1
            await captured[0]

        mock_bridge.record_kg_event.assert_awaited_once()
        call_kwargs = mock_bridge.record_kg_event.call_args.kwargs
        assert call_kwargs["event_type"] == "validate_completed"
        # Entities: one per path
        entity_ids = {e["id"] for e in call_kwargs["entities"]}
        assert "/project/src/a.py" in entity_ids
        assert "/project/src/b.py" in entity_ids

    @pytest.mark.asyncio
    async def test_payload_pass_verdict(self) -> None:
        """payload_data reflects 'pass' + utility_score=1.0 when all_passed and no security issues."""
        mock_bridge = MagicMock()
        mock_bridge.record_kg_event = AsyncMock(return_value={})
        captured: list[Any] = []

        with (
            patch(
                "tapps_mcp.tools.validate_changed._get_brain_bridge",
                return_value=mock_bridge,
            ),
            patch(
                "tapps_mcp.tools.validate_changed.asyncio.create_task",
                side_effect=captured.append,
            ),
        ):
            _fire_validate_events(
                _make_paths(),
                _make_outcome(all_passed=True, total_sec=0),
                elapsed_ms=50,
            )

            await captured[0]

        payload = mock_bridge.record_kg_event.call_args.kwargs["payload_data"]
        assert payload["overall_verdict"] == "pass"
        assert payload["utility_score"] == 1.0
        assert payload["elapsed_ms"] == 50

    @pytest.mark.asyncio
    async def test_payload_warn_verdict(self) -> None:
        """payload_data reflects 'warn' + utility_score=0.5 when gate passes but security issues exist."""
        mock_bridge = MagicMock()
        mock_bridge.record_kg_event = AsyncMock(return_value={})
        captured: list[Any] = []

        with (
            patch(
                "tapps_mcp.tools.validate_changed._get_brain_bridge",
                return_value=mock_bridge,
            ),
            patch(
                "tapps_mcp.tools.validate_changed.asyncio.create_task",
                side_effect=captured.append,
            ),
        ):
            _fire_validate_events(
                _make_paths(),
                _make_outcome(all_passed=True, total_sec=2),
                elapsed_ms=75,
            )

            await captured[0]

        payload = mock_bridge.record_kg_event.call_args.kwargs["payload_data"]
        assert payload["overall_verdict"] == "warn"
        assert payload["utility_score"] == 0.5

    @pytest.mark.asyncio
    async def test_payload_fail_verdict(self) -> None:
        """payload_data reflects 'fail' + utility_score=0.0 when all_passed is False."""
        mock_bridge = MagicMock()
        mock_bridge.record_kg_event = AsyncMock(return_value={})
        captured: list[Any] = []

        with (
            patch(
                "tapps_mcp.tools.validate_changed._get_brain_bridge",
                return_value=mock_bridge,
            ),
            patch(
                "tapps_mcp.tools.validate_changed.asyncio.create_task",
                side_effect=captured.append,
            ),
        ):
            _fire_validate_events(
                _make_paths(),
                _make_outcome(all_passed=False),
                elapsed_ms=200,
            )

            await captured[0]

        payload = mock_bridge.record_kg_event.call_args.kwargs["payload_data"]
        assert payload["overall_verdict"] == "fail"
        assert payload["utility_score"] == 0.0

    @pytest.mark.asyncio
    async def test_silent_when_bridge_is_none(self) -> None:
        """The emitted coroutine exits silently when bridge is unavailable."""
        captured: list[Any] = []

        with (
            patch(
                "tapps_mcp.tools.validate_changed._get_brain_bridge",
                return_value=None,
            ),
            patch(
                "tapps_mcp.tools.validate_changed.asyncio.create_task",
                side_effect=captured.append,
            ),
        ):
            _fire_validate_events(_make_paths(), _make_outcome(), elapsed_ms=10)

            assert len(captured) == 1
            await captured[0]  # must not raise

    @pytest.mark.asyncio
    async def test_silent_when_bridge_lacks_record_kg_event(self) -> None:
        """The emitted coroutine exits silently when bridge has no record_kg_event."""
        mock_bridge = MagicMock(spec=[])  # no attributes at all
        captured: list[Any] = []

        with (
            patch(
                "tapps_mcp.tools.validate_changed._get_brain_bridge",
                return_value=mock_bridge,
            ),
            patch(
                "tapps_mcp.tools.validate_changed.asyncio.create_task",
                side_effect=captured.append,
            ),
        ):
            _fire_validate_events(_make_paths(), _make_outcome(), elapsed_ms=10)

            assert len(captured) == 1
            await captured[0]  # must not raise

    @pytest.mark.asyncio
    async def test_raising_bridge_does_not_propagate(self) -> None:
        """A bridge that raises must not affect callers — exception is swallowed."""
        mock_bridge = MagicMock()
        mock_bridge.record_kg_event = AsyncMock(side_effect=RuntimeError("brain down"))
        captured: list[Any] = []

        with (
            patch(
                "tapps_mcp.tools.validate_changed._get_brain_bridge",
                return_value=mock_bridge,
            ),
            patch(
                "tapps_mcp.tools.validate_changed.asyncio.create_task",
                side_effect=captured.append,
            ),
        ):
            _fire_validate_events(_make_paths(), _make_outcome(), elapsed_ms=10)

            assert len(captured) == 1
            await captured[0]  # must NOT raise even though bridge raised

    def test_create_task_exception_is_swallowed(self) -> None:
        """If create_task itself raises (no running loop), the function does not propagate."""
        mock_bridge = MagicMock()
        mock_bridge.record_kg_event = AsyncMock()

        with (
            patch(
                "tapps_mcp.tools.validate_changed._get_brain_bridge",
                return_value=mock_bridge,
            ),
            patch(
                "tapps_mcp.tools.validate_changed.asyncio.create_task",
                side_effect=RuntimeError("no running event loop"),
            ),
        ):
            # Must not raise
            _fire_validate_events(_make_paths(), _make_outcome(), elapsed_ms=10)

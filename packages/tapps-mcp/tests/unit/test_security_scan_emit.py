"""TAP-1945: Unit tests for _fire_security_scan_events — KG event emission."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.server import _fire_security_scan_events

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bandit_issue(
    *,
    code: str = "B101",
    severity: str = "medium",
    line: int = 10,
    file: str = "/project/src/foo.py",
) -> MagicMock:
    """Build a minimal SecurityIssue-like mock."""
    issue = MagicMock()
    issue.code = code
    issue.severity = severity
    issue.line = line
    issue.file = file
    return issue


def _secret_finding(
    *,
    secret_type: str = "api_key",  # noqa: S107
    severity: str = "high",
    line_number: int = 5,
    file_path: str = "/project/src/foo.py",
) -> MagicMock:
    """Build a minimal SecretFinding-like mock."""
    finding = MagicMock()
    finding.secret_type = secret_type
    finding.severity = severity
    finding.line_number = line_number
    finding.file_path = file_path
    return finding


# ---------------------------------------------------------------------------
# TestFireSecurityScanEvents
# ---------------------------------------------------------------------------


class TestFireSecurityScanEvents:
    """Unit tests for _fire_security_scan_events (TAP-1945)."""

    def test_schedules_task_when_findings_present(self) -> None:
        """create_task is called once when the bridge is available."""
        mock_bridge = MagicMock()
        mock_bridge.record_kg_event = AsyncMock(return_value={"recorded": True})

        with (
            patch("tapps_mcp.server._get_brain_bridge", return_value=mock_bridge),
            patch("tapps_mcp.server.asyncio.create_task") as mock_task,
        ):
            _fire_security_scan_events(
                "/project/src/foo.py",
                [_bandit_issue()],
                [],
            )

        mock_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_emits_bandit_finding_event(self) -> None:
        """Bandit issues produce security_finding events with bandit:<code> entity."""
        mock_bridge = MagicMock()
        mock_bridge.record_kg_event = AsyncMock(return_value={})
        captured: list[Any] = []

        with (
            patch("tapps_mcp.server._get_brain_bridge", return_value=mock_bridge),
            patch("tapps_mcp.server.asyncio.create_task", side_effect=captured.append),
        ):
            issue = _bandit_issue(code="B110", severity="medium", line=42)
            _fire_security_scan_events("/project/src/foo.py", [issue], [])

            assert len(captured) == 1
            await captured[0]

        mock_bridge.record_kg_event.assert_awaited_once()
        call_kwargs = mock_bridge.record_kg_event.call_args.kwargs
        assert call_kwargs["event_type"] == "security_finding"
        entity_ids = {e["id"] for e in call_kwargs["entities"]}
        assert "/project/src/foo.py" in entity_ids
        assert "bandit:B110" in entity_ids
        assert call_kwargs["payload_data"]["severity"] == "medium"
        assert call_kwargs["payload_data"]["line"] == 42

    @pytest.mark.asyncio
    async def test_emits_secret_finding_event(self) -> None:
        """Secret findings produce security_finding events with secret:<type> entity."""
        mock_bridge = MagicMock()
        mock_bridge.record_kg_event = AsyncMock(return_value={})
        captured: list[Any] = []

        with (
            patch("tapps_mcp.server._get_brain_bridge", return_value=mock_bridge),
            patch("tapps_mcp.server.asyncio.create_task", side_effect=captured.append),
        ):
            finding = _secret_finding(secret_type="api_key", severity="high", line_number=7)
            _fire_security_scan_events("/project/src/foo.py", [], [finding])

            assert len(captured) == 1
            await captured[0]

        mock_bridge.record_kg_event.assert_awaited_once()
        call_kwargs = mock_bridge.record_kg_event.call_args.kwargs
        assert call_kwargs["event_type"] == "security_finding"
        entity_ids = {e["id"] for e in call_kwargs["entities"]}
        assert "secret:api_key" in entity_ids
        assert call_kwargs["payload_data"]["severity"] == "high"
        assert call_kwargs["payload_data"]["line"] == 7

    @pytest.mark.asyncio
    async def test_emits_one_event_per_finding(self) -> None:
        """Multiple findings produce multiple record_kg_event calls."""
        mock_bridge = MagicMock()
        mock_bridge.record_kg_event = AsyncMock(return_value={})
        captured: list[Any] = []

        with (
            patch("tapps_mcp.server._get_brain_bridge", return_value=mock_bridge),
            patch("tapps_mcp.server.asyncio.create_task", side_effect=captured.append),
        ):
            issues = [_bandit_issue(code="B101"), _bandit_issue(code="B102")]
            secret = _secret_finding(secret_type="token")
            _fire_security_scan_events("/project/src/foo.py", issues, [secret])

            assert len(captured) == 1
            await captured[0]

        # 2 bandit + 1 secret = 3 calls
        assert mock_bridge.record_kg_event.await_count == 3

    @pytest.mark.asyncio
    async def test_low_severity_findings_skipped(self) -> None:
        """Low-severity findings do NOT trigger emission."""
        mock_bridge = MagicMock()
        mock_bridge.record_kg_event = AsyncMock(return_value={})
        captured: list[Any] = []

        with (
            patch("tapps_mcp.server._get_brain_bridge", return_value=mock_bridge),
            patch("tapps_mcp.server.asyncio.create_task", side_effect=captured.append),
        ):
            low_issue = _bandit_issue(severity="low")
            _fire_security_scan_events("/project/src/foo.py", [low_issue], [])

            assert len(captured) == 1
            await captured[0]

        # No events for low-severity
        mock_bridge.record_kg_event.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_silent_when_bridge_is_none(self) -> None:
        """The emitted coroutine exits silently when bridge is unavailable."""
        captured: list[Any] = []

        with (
            patch("tapps_mcp.server._get_brain_bridge", return_value=None),
            patch("tapps_mcp.server.asyncio.create_task", side_effect=captured.append),
        ):
            _fire_security_scan_events("/project/src/foo.py", [_bandit_issue()], [])

            assert len(captured) == 1
            await captured[0]  # must not raise

    @pytest.mark.asyncio
    async def test_silent_when_bridge_lacks_record_kg_event(self) -> None:
        """Exits silently when bridge has no record_kg_event."""
        mock_bridge = MagicMock(spec=[])  # no attributes
        captured: list[Any] = []

        with (
            patch("tapps_mcp.server._get_brain_bridge", return_value=mock_bridge),
            patch("tapps_mcp.server.asyncio.create_task", side_effect=captured.append),
        ):
            _fire_security_scan_events("/project/src/foo.py", [_bandit_issue()], [])

            assert len(captured) == 1
            await captured[0]  # must not raise

    @pytest.mark.asyncio
    async def test_raising_bridge_does_not_propagate(self) -> None:
        """A bridge that raises must not affect callers — exception is swallowed."""
        mock_bridge = MagicMock()
        mock_bridge.record_kg_event = AsyncMock(side_effect=RuntimeError("brain down"))
        captured: list[Any] = []

        with (
            patch("tapps_mcp.server._get_brain_bridge", return_value=mock_bridge),
            patch("tapps_mcp.server.asyncio.create_task", side_effect=captured.append),
        ):
            _fire_security_scan_events("/project/src/foo.py", [_bandit_issue()], [])

            assert len(captured) == 1
            await captured[0]  # must NOT raise

    def test_create_task_exception_is_swallowed(self) -> None:
        """If create_task raises (no running loop), the function does not propagate."""
        mock_bridge = MagicMock()
        mock_bridge.record_kg_event = AsyncMock()

        with (
            patch("tapps_mcp.server._get_brain_bridge", return_value=mock_bridge),
            patch(
                "tapps_mcp.server.asyncio.create_task",
                side_effect=RuntimeError("no running event loop"),
            ),
        ):
            # Must not raise
            _fire_security_scan_events("/project/src/foo.py", [_bandit_issue()], [])

    @pytest.mark.asyncio
    async def test_no_emission_when_no_findings(self) -> None:
        """Empty findings → no record_kg_event calls (but task is still scheduled)."""
        mock_bridge = MagicMock()
        mock_bridge.record_kg_event = AsyncMock(return_value={})
        captured: list[Any] = []

        with (
            patch("tapps_mcp.server._get_brain_bridge", return_value=mock_bridge),
            patch("tapps_mcp.server.asyncio.create_task", side_effect=captured.append),
        ):
            _fire_security_scan_events("/project/src/foo.py", [], [])

            assert len(captured) == 1
            await captured[0]

        mock_bridge.record_kg_event.assert_not_awaited()

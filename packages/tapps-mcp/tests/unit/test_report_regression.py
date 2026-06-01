"""Regression tests for tapps_report project-wide scans (TAP-2723).

Covers the bug where project-wide reports at higher ``max_files`` failed with an
empty error message ("Error executing tool tapps_report:" with nothing after the
colon). Root causes: unbounded subprocess fan-out via asyncio.gather, a too-narrow
per-file except, and a re-raise that escaped into the MCP framework's empty-message
path instead of returning a structured error.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, _patch, patch

import pytest


@contextmanager
def report_env(
    mock_settings: Any,
    scorer: Any,
    *extra: _patch[Any],
) -> Iterator[None]:
    """Enter the common tapps_report handler patches plus any *extra* ones.

    Local imports inside the handler mean ``generate_report`` /
    ``evaluate_gate`` / ``_get_scorer`` / ``should_skip_path`` must be patched
    at their *source* modules, not on ``server_analysis_tools``.
    """
    with ExitStack() as stack:
        stack.enter_context(patch("tapps_mcp.server_analysis_tools._record_call"))
        stack.enter_context(patch("tapps_mcp.server_analysis_tools._record_execution"))
        stack.enter_context(
            patch("tapps_mcp.server_analysis_tools._with_nudges", side_effect=lambda _n, r: r)
        )
        stack.enter_context(
            patch("tapps_mcp.server_analysis_tools.load_settings", return_value=mock_settings)
        )
        stack.enter_context(patch("tapps_mcp.server_helpers._get_scorer", return_value=scorer))
        stack.enter_context(
            patch(
                "tapps_mcp.server_analysis_tools.ensure_session_initialized",
                new_callable=AsyncMock,
            )
        )
        for cm in extra:
            stack.enter_context(cm)
        yield


def _project_wide_extra(
    files: list[Path], gate: Any, report_value: dict[str, Any]
) -> tuple[_patch[Any], ...]:
    return (
        patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=gate),
        patch("tapps_core.common.utils.should_skip_path", return_value=False),
        patch("pathlib.Path.rglob", return_value=files),
        patch("tapps_mcp.project.report.generate_report", return_value=report_value),
    )


class TestProjectWideScale:
    """A project-wide report over many files must finish (no empty error)."""

    @pytest.mark.asyncio
    async def test_large_project_wide_scan_succeeds(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_report

        # 60 files — well above the previous ~12-file failure threshold.
        files = [Path(f"/fake/project/mod_{i:03d}.py") for i in range(60)]
        mock_settings = MagicMock(project_root=Path("/fake/project"), quality_preset="standard")
        gate = MagicMock(passed=True, failures=[])
        scorer = MagicMock()
        scorer.score_file = AsyncMock(
            return_value=MagicMock(overall_score=82.0, security_issues=[])
        )

        extra = _project_wide_extra(files, gate, {"summary": {"files_scored": 60}, "files": []})
        with report_env(mock_settings, scorer, *extra):
            result = await tapps_report(report_format="markdown", max_files=60)

        assert result["success"] is True
        assert scorer.score_file.await_count == 60
        assert "skipped_files" not in result["data"]

    @pytest.mark.asyncio
    async def test_concurrency_is_bounded(self) -> None:
        """The semaphore caps simultaneous scorers below the file count."""
        from tapps_mcp.server_analysis_tools import _REPORT_MAX_CONCURRENCY, tapps_report

        files = [Path(f"/fake/project/mod_{i:03d}.py") for i in range(50)]
        mock_settings = MagicMock(project_root=Path("/fake/project"), quality_preset="standard")
        gate = MagicMock(passed=True, failures=[])

        in_flight = 0
        peak = 0

        async def _slow_score(_pf: Path) -> Any:
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            try:
                await asyncio.sleep(0)  # yield so unbounded tasks would pile up
                return MagicMock(overall_score=80.0, security_issues=[])
            finally:
                in_flight -= 1

        scorer = MagicMock()
        scorer.score_file = AsyncMock(side_effect=_slow_score)

        extra = _project_wide_extra(files, gate, {"summary": {}, "files": []})
        with report_env(mock_settings, scorer, *extra):
            result = await tapps_report(report_format="json", max_files=50)

        assert result["success"] is True
        assert peak <= _REPORT_MAX_CONCURRENCY, f"peak concurrency {peak} exceeded cap"


class TestPartialResults:
    """One bad file must not abort the whole report."""

    @pytest.mark.asyncio
    async def test_one_failing_file_is_skipped_not_fatal(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_report

        files = [
            Path("/fake/project/good_a.py"),
            Path("/fake/project/bad.py"),
            Path("/fake/project/good_b.py"),
        ]
        mock_settings = MagicMock(project_root=Path("/fake/project"), quality_preset="standard")
        gate = MagicMock(passed=True, failures=[])

        async def _score(pf: Path) -> Any:
            if pf.name == "bad.py":
                raise ValueError("syntax explosion in bad.py")
            return MagicMock(overall_score=80.0, security_issues=[])

        scorer = MagicMock()
        scorer.score_file = AsyncMock(side_effect=_score)

        extra = _project_wide_extra(files, gate, {"summary": {"files_scored": 2}, "files": []})
        with report_env(mock_settings, scorer, *extra):
            result = await tapps_report(report_format="json", max_files=10)

        assert result["success"] is True
        skipped = result["data"]["skipped_files"]
        assert len(skipped) == 1
        assert skipped[0]["file"] == "/fake/project/bad.py"
        assert "ValueError" in skipped[0]["error"]
        assert "syntax explosion" in skipped[0]["error"]

    @pytest.mark.asyncio
    async def test_non_valueerror_failure_also_skipped(self) -> None:
        """The pre-fix except only caught (ValueError, OSError, RuntimeError)."""
        from tapps_mcp.server_analysis_tools import tapps_report

        files = [Path("/fake/project/a.py"), Path("/fake/project/b.py")]
        mock_settings = MagicMock(project_root=Path("/fake/project"), quality_preset="standard")
        gate = MagicMock(passed=True, failures=[])

        async def _score(pf: Path) -> Any:
            if pf.name == "b.py":
                raise KeyError("unexpected key")
            return MagicMock(overall_score=80.0, security_issues=[])

        scorer = MagicMock()
        scorer.score_file = AsyncMock(side_effect=_score)

        extra = _project_wide_extra(files, gate, {"summary": {"files_scored": 1}, "files": []})
        with report_env(mock_settings, scorer, *extra):
            result = await tapps_report(report_format="json", max_files=10)

        assert result["success"] is True
        assert len(result["data"]["skipped_files"]) == 1
        assert "KeyError" in result["data"]["skipped_files"][0]["error"]


class TestNonEmptyError:
    """When the report genuinely fails, the message is structured and non-empty."""

    @pytest.mark.asyncio
    async def test_render_failure_returns_structured_nonempty_error(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_report

        files = [Path("/fake/project/a.py")]
        mock_settings = MagicMock(project_root=Path("/fake/project"), quality_preset="standard")
        gate = MagicMock(passed=True, failures=[])
        scorer = MagicMock()
        scorer.score_file = AsyncMock(
            return_value=MagicMock(overall_score=80.0, security_issues=[])
        )

        extra = (
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=gate),
            patch("tapps_core.common.utils.should_skip_path", return_value=False),
            patch("pathlib.Path.rglob", return_value=files),
            patch(
                "tapps_mcp.project.report.generate_report",
                side_effect=RuntimeError("renderer blew up"),
            ),
        )
        with report_env(mock_settings, scorer, *extra):
            result = await tapps_report(report_format="markdown", max_files=10)

        assert result["success"] is False
        msg = result["error"]["message"]
        assert msg, "error message must never be empty"
        assert "RuntimeError" in msg
        assert "renderer blew up" in msg

    @pytest.mark.asyncio
    async def test_single_file_scorer_failure_returns_nonempty_error(self) -> None:
        from tapps_mcp.server_analysis_tools import tapps_report

        mock_settings = MagicMock(project_root=Path("/fake/project"), quality_preset="standard")
        scorer = MagicMock()
        scorer.score_file = AsyncMock(side_effect=RuntimeError("scorer crashed"))

        extra = (
            patch(
                "tapps_mcp.server_analysis_tools._validate_file_path_lazy",
                return_value=Path("/fake/project/single.py"),
            ),
            patch("tapps_mcp.gates.evaluator.evaluate_gate", return_value=MagicMock(passed=True)),
        )
        with report_env(mock_settings, scorer, *extra):
            result = await tapps_report(file_path="/fake/project/single.py")

        assert result["success"] is False
        msg = result["error"]["message"]
        assert msg
        assert "RuntimeError" in msg
        assert "scorer crashed" in msg


class TestHeartbeatDoesNotLeak:
    """A scan that outlives a heartbeat interval must still succeed.

    Regression for the empty-message bug: the progress heartbeat's
    ``asyncio.wait_for(stop_event.wait(), timeout=...)`` raises TimeoutError
    on every interval while the scan runs. The original code only suppressed
    CancelledError, so the heartbeat task died with TimeoutError and the
    ``finally`` re-raised it as an empty "Error executing tool tapps_report:".
    Only reproduces with a real ``ctx.report_progress`` and a scan longer than
    one heartbeat interval.
    """

    @pytest.mark.asyncio
    async def test_long_scan_with_progress_ctx_succeeds(self) -> None:
        import tapps_mcp.server_analysis_tools as mod
        from tapps_mcp.server_analysis_tools import tapps_report

        files = [Path(f"/fake/project/mod_{i}.py") for i in range(4)]
        mock_settings = MagicMock(project_root=Path("/fake/project"), quality_preset="standard")
        gate = MagicMock(passed=True, failures=[])

        async def _score(_pf: Path) -> Any:
            # Each file takes longer than the (shrunk) heartbeat interval, so the
            # heartbeat's wait_for times out repeatedly during the scan.
            await asyncio.sleep(0.03)
            return MagicMock(overall_score=80.0, security_issues=[])

        scorer = MagicMock()
        scorer.score_file = AsyncMock(side_effect=_score)

        ctx = MagicMock()
        ctx.info = AsyncMock()
        ctx.report_progress = AsyncMock()

        extra = (
            *_project_wide_extra(files, gate, {"summary": {"files_scored": 4}, "files": []}),
            patch.object(mod, "_REPORT_HEARTBEAT_INTERVAL_S", 0.01),
        )
        with report_env(mock_settings, scorer, *extra):
            result = await tapps_report(report_format="json", max_files=10, ctx=ctx)

        assert result["success"] is True
        # The heartbeat must have fired at least once (proving the timeout path ran).
        assert ctx.report_progress.await_count >= 1

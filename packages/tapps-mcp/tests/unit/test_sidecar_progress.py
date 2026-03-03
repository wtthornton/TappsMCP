"""Tests for the sidecar progress file and ctx.info() notifications."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tapps_mcp.server_pipeline_tools import (
    _VALIDATION_PROGRESS_FILE,
    _ProgressTracker,
    _emit_file_info,
    _validate_single_file,
)


# ---------------------------------------------------------------------------
# _ProgressTracker sidecar tests
# ---------------------------------------------------------------------------


class TestProgressTrackerSidecar:
    """Tests for _ProgressTracker sidecar file I/O."""

    def test_init_sidecar_creates_file(self, tmp_path: Path) -> None:
        """init_sidecar creates the progress file with running status."""
        tracker = _ProgressTracker(total=5)
        tracker.init_sidecar(tmp_path)

        sidecar = tmp_path / _VALIDATION_PROGRESS_FILE
        assert sidecar.exists()
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        assert data["status"] == "running"
        assert data["total"] == 5
        assert data["completed"] == 0
        assert data["results"] == []

    def test_record_file_result_updates_sidecar(self, tmp_path: Path) -> None:
        """record_file_result appends to results and updates the file."""
        tracker = _ProgressTracker(total=3)
        tracker.init_sidecar(tmp_path)

        tracker.completed = 1
        tracker.last_file = "scorer.py"
        tracker.record_file_result(
            "src/scorer.py",
            {"overall_score": 82.5, "gate_passed": True},
        )

        sidecar = tmp_path / _VALIDATION_PROGRESS_FILE
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        assert data["status"] == "running"
        assert data["completed"] == 1
        assert len(data["results"]) == 1
        assert data["results"][0]["file"] == "src/scorer.py"
        assert data["results"][0]["score"] == 82.5
        assert data["results"][0]["gate_passed"] is True

    def test_finalize_writes_completed_status(self, tmp_path: Path) -> None:
        """finalize sets status to completed with summary and elapsed."""
        tracker = _ProgressTracker(total=2, completed=2, last_file="gates.py")
        tracker.init_sidecar(tmp_path)
        tracker.finalize(
            all_passed=True,
            summary="2 files validated, 2 passed gate",
            elapsed_ms=1234,
        )

        sidecar = tmp_path / _VALIDATION_PROGRESS_FILE
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        assert data["status"] == "completed"
        assert data["all_gates_passed"] is True
        assert data["summary"] == "2 files validated, 2 passed gate"
        assert data["elapsed_ms"] == 1234

    def test_finalize_error_writes_error_status(self, tmp_path: Path) -> None:
        """finalize_error sets status to error with message."""
        tracker = _ProgressTracker(total=5)
        tracker.init_sidecar(tmp_path)
        tracker.finalize_error("Scoring engine crashed")

        sidecar = tmp_path / _VALIDATION_PROGRESS_FILE
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        assert data["status"] == "error"
        assert data["error"] == "Scoring engine crashed"

    def test_sidecar_not_written_without_init(self, tmp_path: Path) -> None:
        """Without init_sidecar, record/finalize are silent no-ops."""
        tracker = _ProgressTracker(total=3)
        # No init_sidecar call
        tracker.record_file_result("foo.py", {"overall_score": 80})
        tracker.finalize(True, "ok", 100)

        sidecar = tmp_path / _VALIDATION_PROGRESS_FILE
        assert not sidecar.exists()

    def test_sidecar_survives_write_error(self, tmp_path: Path) -> None:
        """If the sidecar path is unwritable, no exception propagates."""
        tracker = _ProgressTracker(total=1)
        # Point to an invalid path
        tracker._sidecar_path = Path("/nonexistent/deep/path/progress.json")
        tracker._started_at = "2026-01-01T00:00:00Z"
        # Should not raise
        tracker.record_file_result("foo.py", {"overall_score": 50})
        tracker.finalize(False, "fail", 100)

    def test_multiple_results_accumulate(self, tmp_path: Path) -> None:
        """Multiple record_file_result calls accumulate in the results array."""
        tracker = _ProgressTracker(total=3)
        tracker.init_sidecar(tmp_path)

        for i, name in enumerate(["a.py", "b.py", "c.py"], 1):
            tracker.completed = i
            tracker.last_file = name
            tracker.record_file_result(name, {"overall_score": 70 + i, "gate_passed": True})

        sidecar = tmp_path / _VALIDATION_PROGRESS_FILE
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        assert len(data["results"]) == 3
        assert data["completed"] == 3
        assert data["results"][2]["file"] == "c.py"


# ---------------------------------------------------------------------------
# ctx.info() notification tests
# ---------------------------------------------------------------------------


class TestEmitFileInfo:
    """Tests for _emit_file_info ctx.info() notifications."""

    @pytest.mark.asyncio
    async def test_sends_info_on_pass(self) -> None:
        """ctx.info is called with PASSED status when gate passes."""
        ctx = MagicMock()
        ctx.info = AsyncMock()
        result = {"overall_score": 85.0, "gate_passed": True}

        await _emit_file_info(ctx, Path("scorer.py"), result)

        ctx.info.assert_called_once()
        msg = ctx.info.call_args[0][0]
        assert "scorer.py" in msg
        assert "85.0" in msg
        assert "PASSED" in msg

    @pytest.mark.asyncio
    async def test_sends_info_on_fail(self) -> None:
        """ctx.info is called with FAILED status when gate fails."""
        ctx = MagicMock()
        ctx.info = AsyncMock()
        result = {"overall_score": 55.0, "gate_passed": False}

        await _emit_file_info(ctx, Path("server.py"), result)

        msg = ctx.info.call_args[0][0]
        assert "FAILED" in msg
        assert "55.0" in msg

    @pytest.mark.asyncio
    async def test_noop_when_ctx_is_none(self) -> None:
        """No error when ctx is None."""
        await _emit_file_info(None, Path("foo.py"), {"gate_passed": True})

    @pytest.mark.asyncio
    async def test_noop_when_no_info_method(self) -> None:
        """No error when ctx has no info method."""
        ctx = MagicMock(spec=[])
        await _emit_file_info(ctx, Path("foo.py"), {"gate_passed": True})

    @pytest.mark.asyncio
    async def test_survives_info_exception(self) -> None:
        """Exception from ctx.info is suppressed."""
        ctx = MagicMock()
        ctx.info = AsyncMock(side_effect=RuntimeError("boom"))
        result = {"overall_score": 80.0, "gate_passed": True}

        await _emit_file_info(ctx, Path("foo.py"), result)
        # Should not raise


class TestValidateSingleFileCtxInfo:
    """Tests that _validate_single_file sends ctx.info notifications."""

    @pytest.mark.asyncio
    async def test_ctx_info_called_after_scoring(self) -> None:
        """ctx.info is called once per file after scoring completes."""
        ctx = MagicMock()
        ctx.info = AsyncMock()

        mock_score = MagicMock()
        mock_score.overall_score = 82.0
        mock_score.security_issues = []

        mock_gate = MagicMock()
        mock_gate.passed = True
        mock_gate.failures = []

        mock_scorer = MagicMock()
        mock_scorer.score_file_quick = MagicMock(return_value=mock_score)

        sem = asyncio.Semaphore(10)
        tracker = _ProgressTracker(total=1)

        with patch(
            "tapps_mcp.server_pipeline_tools.asyncio.to_thread",
            return_value=mock_score,
        ), patch(
            "tapps_mcp.gates.evaluator.evaluate_gate",
            return_value=mock_gate,
        ):
            result = await _validate_single_file(
                Path("test.py"), mock_scorer, "standard", True, False, sem,
                tracker, ctx,
            )

        assert result["gate_passed"] is True
        ctx.info.assert_called_once()
        msg = ctx.info.call_args[0][0]
        assert "test.py" in msg
        assert "PASSED" in msg

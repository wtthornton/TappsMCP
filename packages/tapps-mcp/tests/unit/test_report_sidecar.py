"""Tests for the report sidecar progress file."""

from __future__ import annotations

import json
from pathlib import Path

from tapps_mcp.server_analysis_tools import _ReportProgressTracker


class TestReportSidecar:
    """Tests for _ReportProgressTracker sidecar file I/O."""

    def test_sidecar_created_on_init(self, tmp_path: Path) -> None:
        tracker = _ReportProgressTracker(total=5)
        tracker.init_sidecar(tmp_path)

        sidecar = tmp_path / ".tapps-mcp" / ".report-progress.json"
        assert sidecar.exists()
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        assert data["status"] == "running"
        assert data["total"] == 5
        assert data["completed"] == 0

    def test_sidecar_records_file_results(self, tmp_path: Path) -> None:
        tracker = _ReportProgressTracker(total=3)
        tracker.init_sidecar(tmp_path)

        tracker.completed = 1
        tracker.last_file = "scorer.py"
        tracker.record_file_result("src/scorer.py", {"overall_score": 82.5})

        sidecar = tmp_path / ".tapps-mcp" / ".report-progress.json"
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        assert data["completed"] == 1
        assert len(data["results"]) == 1
        assert data["results"][0]["file"] == "src/scorer.py"
        assert data["results"][0]["score"] == 82.5

    def test_sidecar_finalize_sets_completed(self, tmp_path: Path) -> None:
        tracker = _ReportProgressTracker(total=2)
        tracker.init_sidecar(tmp_path)
        tracker.finalize("2 files scored", 1234)

        sidecar = tmp_path / ".tapps-mcp" / ".report-progress.json"
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        assert data["status"] == "completed"
        assert data["summary"] == "2 files scored"
        assert data["elapsed_ms"] == 1234

    def test_sidecar_finalize_error(self, tmp_path: Path) -> None:
        tracker = _ReportProgressTracker(total=5)
        tracker.init_sidecar(tmp_path)
        tracker.finalize_error("Scoring engine crashed")

        sidecar = tmp_path / ".tapps-mcp" / ".report-progress.json"
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        assert data["status"] == "error"
        assert data["error"] == "Scoring engine crashed"

    def test_sidecar_not_written_without_init(self, tmp_path: Path) -> None:
        tracker = _ReportProgressTracker(total=3)
        tracker.record_file_result("foo.py", {"overall_score": 80})
        tracker.finalize("ok", 100)

        sidecar = tmp_path / ".tapps-mcp" / ".report-progress.json"
        assert not sidecar.exists()

    def test_sidecar_survives_write_error(self) -> None:
        tracker = _ReportProgressTracker(total=1)
        tracker._sidecar_path = Path("/nonexistent/deep/path/progress.json")
        tracker._started_at = "2026-01-01T00:00:00Z"
        # Should not raise
        tracker.record_file_result("foo.py", {"overall_score": 50})
        tracker.finalize("fail", 100)

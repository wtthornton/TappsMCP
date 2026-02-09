"""Tests for file-based adaptive persistence."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from tapps_mcp.adaptive.models import CodeOutcome
from tapps_mcp.adaptive.persistence import (
    FileOutcomeTracker,
    FilePerformanceTracker,
    save_json_atomic,
)


class TestFileOutcomeTracker:
    @pytest.fixture()
    def tracker(self, tmp_path: Path) -> FileOutcomeTracker:
        return FileOutcomeTracker(tmp_path)

    def test_save_and_load_roundtrip(self, tracker: FileOutcomeTracker):
        outcome = CodeOutcome(
            workflow_id="wf-1",
            file_path="main.py",
            initial_scores={"complexity": 7.0},
            first_pass_success=True,
        )
        tracker.save_outcome(outcome)
        loaded = tracker.load_outcomes()
        assert len(loaded) == 1
        assert loaded[0].workflow_id == "wf-1"
        assert loaded[0].first_pass_success is True

    def test_load_with_limit(self, tracker: FileOutcomeTracker):
        for i in range(5):
            tracker.save_outcome(
                CodeOutcome(workflow_id=f"wf-{i}", file_path="f.py")
            )
        loaded = tracker.load_outcomes(limit=2)
        assert len(loaded) == 2
        assert loaded[0].workflow_id == "wf-3"
        assert loaded[1].workflow_id == "wf-4"

    def test_load_with_workflow_id_filter(self, tracker: FileOutcomeTracker):
        tracker.save_outcome(CodeOutcome(workflow_id="wf-a", file_path="a.py"))
        tracker.save_outcome(CodeOutcome(workflow_id="wf-b", file_path="b.py"))
        loaded = tracker.load_outcomes(workflow_id="wf-a")
        assert len(loaded) == 1
        assert loaded[0].file_path == "a.py"

    def test_load_empty(self, tracker: FileOutcomeTracker):
        loaded = tracker.load_outcomes()
        assert loaded == []

    def test_get_statistics_empty(self, tracker: FileOutcomeTracker):
        stats = tracker.get_statistics()
        assert stats["total_outcomes"] == 0
        assert stats["first_pass_success_rate"] == 0.0

    def test_get_statistics_populated(self, tracker: FileOutcomeTracker):
        tracker.save_outcome(
            CodeOutcome(
                workflow_id="wf-1",
                file_path="a.py",
                first_pass_success=True,
                iterations=1,
                expert_consultations=["expert-security"],
            )
        )
        tracker.save_outcome(
            CodeOutcome(
                workflow_id="wf-2",
                file_path="b.py",
                first_pass_success=False,
                iterations=3,
                expert_consultations=["expert-security", "expert-testing"],
            )
        )
        stats = tracker.get_statistics()
        assert stats["total_outcomes"] == 2
        assert stats["first_pass_success_rate"] == 0.5
        assert stats["avg_iterations"] == 2.0
        assert stats["expert_usage"]["expert-security"] == 2

    def test_jsonl_format(self, tracker: FileOutcomeTracker):
        tracker.save_outcome(CodeOutcome(workflow_id="wf-1", file_path="a.py"))
        lines = tracker._file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["workflow_id"] == "wf-1"


class TestFilePerformanceTracker:
    @pytest.fixture()
    def tracker(self, tmp_path: Path) -> FilePerformanceTracker:
        return FilePerformanceTracker(tmp_path)

    def test_track_and_calculate(self, tracker: FilePerformanceTracker):
        tracker.track_consultation("expert-security", "security", 0.85, "How to hash?")
        tracker.track_consultation("expert-security", "security", 0.90, "Salt usage?")
        perf = tracker.calculate_performance("expert-security")
        assert perf is not None
        assert perf.consultations == 2
        assert 0.87 <= perf.avg_confidence <= 0.88
        assert "security" in perf.domain_coverage

    def test_calculate_empty(self, tracker: FilePerformanceTracker):
        perf = tracker.calculate_performance("nonexistent")
        assert perf is None

    def test_get_all_performance(self, tracker: FilePerformanceTracker):
        tracker.track_consultation("expert-a", "security", 0.8)
        tracker.track_consultation("expert-b", "testing", 0.7)
        all_perf = tracker.get_all_performance()
        assert "expert-a" in all_perf
        assert "expert-b" in all_perf

    def test_weakness_low_confidence(self, tracker: FilePerformanceTracker):
        # Track consultations with low confidence.
        for _ in range(3):
            tracker.track_consultation("expert-weak", "domain-x", 0.3)
        perf = tracker.calculate_performance("expert-weak")
        assert perf is not None
        assert "low_confidence" in perf.weaknesses


class TestSaveJsonAtomic:
    def test_writes_json(self, tmp_path: Path):
        target = tmp_path / "data.json"
        save_json_atomic({"key": "value"}, target)
        assert target.exists()
        data = json.loads(target.read_text(encoding="utf-8"))
        assert data["key"] == "value"

    def test_overwrites_existing(self, tmp_path: Path):
        target = tmp_path / "data.json"
        save_json_atomic({"v": 1}, target)
        save_json_atomic({"v": 2}, target)
        data = json.loads(target.read_text(encoding="utf-8"))
        assert data["v"] == 2

"""Tests for tapps_core.metrics.feedback — user feedback tracker."""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_core.metrics.feedback import FeedbackRecord, FeedbackTracker


# ---------------------------------------------------------------------------
# FeedbackRecord
# ---------------------------------------------------------------------------


class TestFeedbackRecord:
    def test_to_dict(self) -> None:
        rec = FeedbackRecord(
            tool_name="tapps_score_file",
            helpful=True,
            context="good output",
            session_id="s1",
            timestamp="2026-01-01T00:00:00+00:00",
        )
        d = rec.to_dict()
        assert d["tool_name"] == "tapps_score_file"
        assert d["helpful"] is True

    def test_from_dict_round_trip(self) -> None:
        original = FeedbackRecord(
            tool_name="tapps_checklist",
            helpful=False,
            context="missed items",
            session_id="s2",
            timestamp="2026-01-02T00:00:00+00:00",
        )
        restored = FeedbackRecord.from_dict(original.to_dict())
        assert restored.tool_name == original.tool_name
        assert restored.helpful == original.helpful
        assert restored.context == original.context

    def test_from_dict_ignores_extra_keys(self) -> None:
        data = {"tool_name": "x", "helpful": True, "unknown_field": 42}
        rec = FeedbackRecord.from_dict(data)
        assert rec.tool_name == "x"


# ---------------------------------------------------------------------------
# FeedbackTracker
# ---------------------------------------------------------------------------


class TestFeedbackTracker:
    @pytest.fixture
    def tracker(self, tmp_path: Path) -> FeedbackTracker:
        return FeedbackTracker(tmp_path / "metrics")

    def test_record_creates_file(self, tracker: FeedbackTracker) -> None:
        tracker.record("tapps_score_file", helpful=True)
        assert tracker._file.exists()

    def test_record_returns_feedback_record(self, tracker: FeedbackTracker) -> None:
        rec = tracker.record("tapps_score_file", helpful=True, context="great")
        assert isinstance(rec, FeedbackRecord)
        assert rec.helpful is True
        assert rec.timestamp  # Non-empty

    def test_statistics_empty(self, tracker: FeedbackTracker) -> None:
        stats = tracker.get_statistics()
        assert stats["total_feedback"] == 0
        assert stats["helpful_rate"] == 0.0

    def test_statistics_after_records(self, tracker: FeedbackTracker) -> None:
        tracker.record("tool_a", helpful=True)
        tracker.record("tool_a", helpful=True)
        tracker.record("tool_a", helpful=False)
        stats = tracker.get_statistics()
        assert stats["total_feedback"] == 3
        assert stats["helpful_count"] == 2
        assert stats["not_helpful_count"] == 1

    def test_statistics_filtered_by_tool(self, tracker: FeedbackTracker) -> None:
        tracker.record("tool_a", helpful=True)
        tracker.record("tool_b", helpful=False)
        stats = tracker.get_statistics(tool_name="tool_a")
        assert stats["total_feedback"] == 1
        assert stats["helpful_count"] == 1

    def test_get_by_tool(self, tracker: FeedbackTracker) -> None:
        tracker.record("tool_a", helpful=True)
        tracker.record("tool_b", helpful=False)
        tracker.record("tool_b", helpful=True)
        by_tool = tracker.get_by_tool()
        assert "tool_a" in by_tool
        assert "tool_b" in by_tool
        assert by_tool["tool_b"]["total"] == 2

    def test_context_truncation(self, tracker: FeedbackTracker) -> None:
        long_context = "x" * 1000
        rec = tracker.record("tool_a", helpful=True, context=long_context)
        assert len(rec.context) == 500

    def test_to_adaptive_outcomes(self, tracker: FeedbackTracker) -> None:
        tracker.record("tapps_score_file", helpful=True)
        tracker.record("tapps_quality_gate", helpful=False)
        tracker.record("other_tool", helpful=True)  # not a scoring tool
        outcomes = tracker.to_adaptive_outcomes()
        assert len(outcomes) == 2
        assert outcomes[0]["first_pass_success"] is True
        assert outcomes[1]["first_pass_success"] is False
        assert outcomes[0]["source"] == "feedback"

    def test_is_duplicate_detects_recent(self, tracker: FeedbackTracker) -> None:
        tracker.record("tool_a", helpful=True, context="ctx")
        assert tracker.is_duplicate("tool_a", True, "ctx") is True

    def test_is_duplicate_different_context(self, tracker: FeedbackTracker) -> None:
        tracker.record("tool_a", helpful=True, context="ctx1")
        assert tracker.is_duplicate("tool_a", True, "ctx2") is False

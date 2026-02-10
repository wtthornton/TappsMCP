"""Tests for feedback tracker."""

from pathlib import Path

import pytest

from tapps_mcp.metrics.feedback import FeedbackTracker


@pytest.fixture
def metrics_dir(tmp_path):
    d = tmp_path / "metrics"
    d.mkdir()
    return d


@pytest.fixture
def tracker(metrics_dir):
    return FeedbackTracker(metrics_dir)


class TestFeedbackTracker:
    def test_record(self, tracker):
        entry = tracker.record(
            tool_name="tapps_score_file",
            helpful=True,
            context="Gave accurate score",
            session_id="s1",
        )
        assert entry.tool_name == "tapps_score_file"
        assert entry.helpful is True

    def test_record_not_helpful(self, tracker):
        entry = tracker.record("tapps_consult_expert", helpful=False)
        assert entry.helpful is False

    def test_get_statistics(self, tracker):
        tracker.record("tool_a", helpful=True)
        tracker.record("tool_a", helpful=True)
        tracker.record("tool_a", helpful=False)

        stats = tracker.get_statistics()
        assert stats["total_feedback"] == 3
        assert stats["helpful_count"] == 2
        assert stats["not_helpful_count"] == 1
        assert abs(stats["helpful_rate"] - 0.6667) < 0.01

    def test_get_statistics_by_tool(self, tracker):
        tracker.record("tool_a", helpful=True)
        tracker.record("tool_b", helpful=False)

        stats_a = tracker.get_statistics(tool_name="tool_a")
        assert stats_a["helpful_rate"] == 1.0

        stats_b = tracker.get_statistics(tool_name="tool_b")
        assert stats_b["helpful_rate"] == 0.0

    def test_get_by_tool(self, tracker):
        tracker.record("tool_a", helpful=True)
        tracker.record("tool_b", helpful=False)
        tracker.record("tool_a", helpful=True)

        by_tool = tracker.get_by_tool()
        assert "tool_a" in by_tool
        assert by_tool["tool_a"]["total"] == 2
        assert by_tool["tool_a"]["helpful"] == 2

    def test_empty_statistics(self, tracker):
        stats = tracker.get_statistics()
        assert stats["total_feedback"] == 0
        assert stats["helpful_rate"] == 0.0

    def test_context_truncation(self, tracker):
        long_context = "x" * 1000
        entry = tracker.record("tool_a", True, context=long_context)
        assert len(entry.context) == 500

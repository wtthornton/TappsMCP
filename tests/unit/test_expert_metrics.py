"""Tests for expert performance tracking."""

from pathlib import Path

import pytest

from tapps_mcp.metrics.expert_metrics import (
    ExpertPerformanceTracker,
)


@pytest.fixture
def metrics_dir(tmp_path):
    d = tmp_path / "metrics"
    d.mkdir()
    return d


@pytest.fixture
def tracker(metrics_dir):
    return ExpertPerformanceTracker(metrics_dir)


class TestExpertPerformanceTracker:
    def test_track_consultation(self, tracker):
        record = tracker.track_consultation(
            expert_id="security_expert",
            domain="security",
            confidence=0.85,
            query="How to hash passwords?",
            session_id="s1",
        )
        assert record.expert_id == "security_expert"
        assert record.confidence == 0.85

    def test_get_performance(self, tracker):
        for i in range(5):
            tracker.track_consultation("exp1", "security", 0.7 + i * 0.05)

        perf = tracker.get_performance(expert_id="exp1")
        assert len(perf) == 1
        assert perf[0].consultations == 5
        assert perf[0].avg_confidence > 0

    def test_get_performance_all_experts(self, tracker):
        tracker.track_consultation("exp1", "security", 0.8)
        tracker.track_consultation("exp2", "testing", 0.9)
        tracker.track_consultation("exp1", "security", 0.7)

        perf = tracker.get_performance()
        assert len(perf) == 2

    def test_get_domain_breakdown(self, tracker):
        tracker.track_consultation("exp1", "security", 0.8)
        tracker.track_consultation("exp2", "security", 0.7)
        tracker.track_consultation("exp1", "testing", 0.9)

        breakdown = tracker.get_domain_breakdown()
        assert "security" in breakdown
        assert "testing" in breakdown
        assert breakdown["security"]["consultations"] == 2

    def test_low_confidence_weakness(self, tracker):
        for _ in range(5):
            tracker.track_consultation("exp1", "testing", 0.3)

        perf = tracker.get_performance(expert_id="exp1")
        assert "low_confidence" in perf[0].weaknesses

    def test_empty_performance(self, tracker):
        perf = tracker.get_performance()
        assert len(perf) == 0

    def test_persistence(self, tracker, metrics_dir):
        tracker.track_consultation("exp1", "security", 0.8)

        # Create a new tracker pointing to same dir
        tracker2 = ExpertPerformanceTracker(metrics_dir)
        perf = tracker2.get_performance()
        assert len(perf) == 1

"""Tests for confidence metrics tracker."""


import pytest

from tapps_mcp.metrics.confidence_metrics import (
    ConfidenceMetricsTracker,
)


@pytest.fixture
def metrics_dir(tmp_path):
    d = tmp_path / "metrics"
    d.mkdir()
    return d


@pytest.fixture
def tracker(metrics_dir):
    return ConfidenceMetricsTracker(metrics_dir)


class TestConfidenceMetricsTracker:
    def test_record(self, tracker):
        metric = tracker.record(
            domain="security",
            confidence=0.85,
            threshold=0.6,
            agreement_level=0.9,
            num_experts=3,
        )
        assert metric.meets_threshold is True
        assert metric.domain == "security"

    def test_record_below_threshold(self, tracker):
        metric = tracker.record(domain="testing", confidence=0.4, threshold=0.6)
        assert metric.meets_threshold is False

    def test_get_statistics(self, tracker):
        tracker.record("security", 0.8, 0.6)
        tracker.record("testing", 0.5, 0.6)
        tracker.record("security", 0.9, 0.6)

        stats = tracker.get_statistics()
        assert stats.total_records == 3
        assert stats.avg_confidence > 0
        assert "security" in stats.by_domain
        assert "testing" in stats.by_domain

    def test_threshold_meet_rate(self, tracker):
        tracker.record("security", 0.8, 0.6)  # meets
        tracker.record("security", 0.4, 0.6)  # doesn't meet
        tracker.record("security", 0.7, 0.6)  # meets

        stats = tracker.get_statistics()
        assert abs(stats.threshold_meet_rate - 0.6667) < 0.01

    def test_get_recent(self, tracker):
        for i in range(10):
            tracker.record("security", 0.5 + i * 0.05, 0.6)

        recent = tracker.get_recent(limit=5)
        assert len(recent) == 5

    def test_bounded_storage(self, tracker, metrics_dir):
        # Record more than max records to test trimming
        for i in range(20):
            tracker.record("security", 0.7, 0.6)

        records = tracker._load()
        assert len(records) <= 1000  # _MAX_RECORDS

    def test_empty_statistics(self, tracker):
        stats = tracker.get_statistics()
        assert stats.total_records == 0
        assert stats.avg_confidence == 0.0

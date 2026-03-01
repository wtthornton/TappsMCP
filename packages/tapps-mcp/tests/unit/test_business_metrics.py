"""Tests for business metrics collection."""

from datetime import UTC, datetime, timedelta

import pytest

from tapps_mcp.metrics.business_metrics import (
    BusinessMetricsCollector,
    BusinessMetricsData,
)
from tapps_mcp.metrics.confidence_metrics import ConfidenceMetricsTracker
from tapps_mcp.metrics.execution_metrics import ToolCallMetricsCollector
from tapps_mcp.metrics.expert_metrics import ExpertPerformanceTracker
from tapps_mcp.metrics.outcome_tracker import OutcomeTracker
from tapps_mcp.metrics.rag_metrics import RAGMetricsTracker


@pytest.fixture
def metrics_dir(tmp_path):
    d = tmp_path / "metrics"
    d.mkdir()
    return d


@pytest.fixture
def all_trackers(metrics_dir):
    return {
        "execution_collector": ToolCallMetricsCollector(metrics_dir),
        "outcome_tracker": OutcomeTracker(metrics_dir),
        "expert_tracker": ExpertPerformanceTracker(metrics_dir),
        "confidence_tracker": ConfidenceMetricsTracker(metrics_dir),
        "rag_tracker": RAGMetricsTracker(metrics_dir),
    }


@pytest.fixture
def collector(metrics_dir, all_trackers):
    return BusinessMetricsCollector(metrics_dir, **all_trackers)


class TestBusinessMetricsCollector:
    def test_collect_empty(self, collector):
        data = collector.collect()
        assert isinstance(data, BusinessMetricsData)
        assert data.adoption.total_consultations == 0
        assert data.roi.total_tool_calls == 0

    def test_collect_with_execution_data(self, collector, all_trackers):
        now = datetime.now(tz=UTC)
        exec_coll = all_trackers["execution_collector"]
        exec_coll.record("tapps_score_file", now, now + timedelta(milliseconds=100))
        exec_coll.record("tapps_quality_gate", now, now + timedelta(milliseconds=200))

        data = collector.collect()
        assert data.adoption.total_consultations == 2
        assert data.roi.total_tool_calls == 2

    def test_collect_with_outcome_data(self, collector, all_trackers):
        outcome_tracker = all_trackers["outcome_tracker"]
        outcome_tracker.track_initial_scores("s1", "/tmp/a.py", {"overall": 80.0})
        outcome_tracker.finalize_outcome("s1", "/tmp/a.py")

        data = collector.collect()
        assert data.effectiveness.first_pass_success_rate > 0

    def test_collect_with_confidence_data(self, collector, all_trackers):
        conf = all_trackers["confidence_tracker"]
        conf.record("security", 0.85, 0.6)
        conf.record("testing", 0.70, 0.6)

        data = collector.collect()
        assert data.quality.avg_confidence > 0

    def test_operational_metrics(self, collector, all_trackers):
        now = datetime.now(tz=UTC)
        exec_coll = all_trackers["execution_collector"]
        exec_coll.record("tool_a", now, now + timedelta(milliseconds=100), status="success")
        exec_coll.record("tool_b", now, now + timedelta(milliseconds=100), status="failed")

        data = collector.collect()
        assert data.operational.error_rate == 0.5

    def test_to_dict(self, collector):
        data = collector.collect()
        d = data.to_dict()
        assert "adoption" in d
        assert "effectiveness" in d
        assert "quality" in d
        assert "roi" in d
        assert "operational" in d

    def test_get_latest(self, collector):
        # First collect creates the file
        collector.collect()
        latest = collector.get_latest()
        assert latest is not None
        assert latest.timestamp != ""

    def test_get_latest_no_file(self, collector):
        latest = collector.get_latest()
        assert latest is None

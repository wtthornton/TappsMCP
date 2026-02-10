"""Tests for RAG metrics tracker."""

from pathlib import Path

import pytest

from tapps_mcp.metrics.rag_metrics import (
    RAGMetricsTracker,
    RAGQueryTimer,
)


@pytest.fixture
def metrics_dir(tmp_path):
    d = tmp_path / "metrics"
    d.mkdir()
    return d


@pytest.fixture
def tracker(metrics_dir):
    return RAGMetricsTracker(metrics_dir)


class TestRAGMetricsTracker:
    def test_record_query(self, tracker):
        metric = tracker.record_query(
            query="How to use fastapi?",
            domain="api-design",
            latency_ms=50.0,
            num_results=5,
            similarities=[0.9, 0.8, 0.7, 0.6, 0.5],
            cache_hit=True,
            backend_type="vector",
        )
        assert metric.avg_similarity > 0
        assert metric.cache_hit is True

    def test_get_metrics(self, tracker):
        tracker.record_query("q1", "security", 30.0, 3, [0.8, 0.7, 0.6], True)
        tracker.record_query("q2", "testing", 50.0, 2, [0.5, 0.4], False)

        metrics = tracker.get_metrics()
        assert metrics.total_queries == 2
        assert metrics.cache_hit_rate == 0.5
        assert "security" in metrics.by_domain

    def test_by_backend(self, tracker):
        tracker.record_query("q1", "security", 30.0, 3, backend_type="vector")
        tracker.record_query("q2", "security", 50.0, 2, backend_type="simple")

        metrics = tracker.get_metrics()
        assert "vector" in metrics.by_backend
        assert "simple" in metrics.by_backend

    def test_get_recent(self, tracker):
        for i in range(10):
            tracker.record_query(f"q{i}", "test", 10.0 * i, 1)

        recent = tracker.get_recent(limit=5)
        assert len(recent) == 5

    def test_query_truncation(self, tracker):
        long_query = "x" * 500
        metric = tracker.record_query(long_query, "test", 10.0, 1)
        assert len(metric.query) == 200

    def test_empty_metrics(self, tracker):
        metrics = tracker.get_metrics()
        assert metrics.total_queries == 0
        assert metrics.cache_hit_rate == 0.0


class TestRAGQueryTimer:
    def test_timer(self):
        timer = RAGQueryTimer()
        with timer:
            # Simulate work
            total = sum(range(1000))
            _ = total
        assert timer.elapsed_ms > 0

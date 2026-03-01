"""Tests for quality aggregator."""

import pytest

from tapps_core.metrics.quality_aggregator import (
    FileScore,
    QualityAggregator,
)


@pytest.fixture
def aggregator():
    return QualityAggregator()


@pytest.fixture
def sample_files():
    return [
        FileScore("a.py", 85.0, {"security": 90.0, "complexity": 80.0}, 3, True),
        FileScore("b.py", 72.0, {"security": 70.0, "complexity": 74.0}, 5, True),
        FileScore("c.py", 55.0, {"security": 50.0, "complexity": 60.0}, 10, False),
        FileScore("d.py", 92.0, {"security": 95.0, "complexity": 89.0}, 1, True),
    ]


class TestQualityAggregator:
    def test_aggregate_scores(self, aggregator, sample_files):
        report = aggregator.aggregate_scores(sample_files)
        assert report.total_files == 4
        assert report.min_score == 55.0
        assert report.max_score == 92.0
        assert report.gate_pass_rate == 0.75
        assert report.total_violations == 19

    def test_aggregate_empty(self, aggregator):
        report = aggregator.aggregate_scores([])
        assert report.total_files == 0

    def test_category_averages(self, aggregator, sample_files):
        report = aggregator.aggregate_scores(sample_files)
        assert "security" in report.category_averages
        assert "complexity" in report.category_averages

    def test_score_distribution(self, aggregator, sample_files):
        report = aggregator.aggregate_scores(sample_files)
        assert report.score_distribution["90-100"] == 1
        assert report.score_distribution["80-89"] == 1
        assert report.score_distribution["70-79"] == 1
        assert report.score_distribution["0-59"] == 1

    def test_best_worst_files(self, aggregator, sample_files):
        report = aggregator.aggregate_scores(sample_files)
        assert "d.py" in report.best_files
        assert len(report.best_files) == 3

    def test_compare_files(self, aggregator, sample_files):
        comparison = aggregator.compare_files(sample_files)
        assert comparison["best"] == "d.py"
        assert comparison["worst"] == "c.py"
        assert comparison["range"] == 37.0
        assert len(comparison["rankings"]) == 4

    def test_compare_empty(self, aggregator):
        comparison = aggregator.compare_files([])
        assert comparison["rankings"] == []

    def test_generate_quality_report(self, aggregator, sample_files):
        report = aggregator.generate_quality_report(sample_files)
        assert "aggregate" in report
        assert "comparison" in report

    def test_to_dict(self, aggregator, sample_files):
        report = aggregator.aggregate_scores(sample_files)
        d = report.to_dict()
        assert "total_files" in d
        assert "score_distribution" in d

"""Tests for ASCII visualizer."""

import pytest

from tapps_mcp.metrics.visualizer import AnalyticsVisualizer


@pytest.fixture
def viz():
    return AnalyticsVisualizer()


class TestAnalyticsVisualizer:
    def test_bar_chart(self, viz):
        data = {"Tool A": 10.0, "Tool B": 5.0, "Tool C": 8.0}
        chart = viz.create_bar_chart(data, title="Usage")
        assert "Usage" in chart
        assert "Tool A" in chart
        assert "10.00" in chart

    def test_bar_chart_empty(self, viz):
        chart = viz.create_bar_chart({})
        assert chart == ""

    def test_bar_chart_no_values(self, viz):
        data = {"Tool A": 0.0}
        chart = viz.create_bar_chart(data)
        assert "Tool A" in chart

    def test_sparkline(self, viz):
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
        sparkline = viz.create_sparkline(values)
        assert len(sparkline) > 0

    def test_sparkline_empty(self, viz):
        sparkline = viz.create_sparkline([])
        assert sparkline == ""

    def test_sparkline_resampling(self, viz):
        values = [float(i) for i in range(100)]
        sparkline = viz.create_sparkline(values, width=10)
        assert len(sparkline) == 10

    def test_metric_table(self, viz):
        headers = ["Tool", "Calls", "Rate"]
        rows = [["tool_a", "10", "90%"], ["tool_b", "5", "80%"]]
        table = viz.create_metric_table(headers, rows, title="Stats")
        assert "Stats" in table
        assert "tool_a" in table
        assert "90%" in table

    def test_metric_table_empty(self, viz):
        table = viz.create_metric_table([], [])
        assert table == ""

    def test_metric_comparison(self, viz):
        before = {"score": 70.0, "security": 60.0}
        after = {"score": 85.0, "security": 80.0}
        comparison = viz.create_metric_comparison(before, after)
        assert "score" in comparison
        assert "security" in comparison
        assert "+15.00" in comparison

    def test_metric_comparison_empty(self, viz):
        comparison = viz.create_metric_comparison({}, {})
        assert comparison == ""

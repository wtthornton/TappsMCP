"""Tests for trend detection."""


from tapps_mcp.metrics.trends import (
    calculate_trend,
    detect_trends,
)


class TestCalculateTrend:
    def test_improving_trend(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        trend = calculate_trend("test_metric", values)
        assert trend.direction == "improving"
        assert trend.slope > 0
        assert trend.data_points == 10
        assert trend.change_pct > 0

    def test_degrading_trend(self):
        values = [10.0, 9.0, 8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0]
        trend = calculate_trend("test_metric", values)
        assert trend.direction == "degrading"
        assert trend.slope < 0

    def test_stable_trend(self):
        values = [5.0, 5.0, 5.0, 5.0, 5.0]
        trend = calculate_trend("test_metric", values)
        assert trend.direction == "stable"

    def test_single_value(self):
        trend = calculate_trend("test_metric", [5.0])
        assert trend.direction == "stable"
        assert trend.data_points == 1

    def test_empty_values(self):
        trend = calculate_trend("test_metric", [])
        assert trend.data_points == 0

    def test_two_values(self):
        trend = calculate_trend("test_metric", [1.0, 10.0])
        assert trend.data_points == 2

    def test_noisy_stable(self):
        # Random-ish values with no clear trend
        values = [5.0, 5.1, 4.9, 5.0, 5.1, 4.9, 5.0]
        trend = calculate_trend("test_metric", values)
        assert trend.direction == "stable"

    def test_to_dict(self):
        trend = calculate_trend("test_metric", [1.0, 2.0, 3.0])
        d = trend.to_dict()
        assert d["metric_name"] == "test_metric"
        assert "direction" in d
        assert "slope" in d

    def test_r_squared(self):
        # Perfect linear data
        values = [float(i) for i in range(10)]
        trend = calculate_trend("test_metric", values)
        assert trend.r_squared > 0.99


class TestDetectTrends:
    def test_multiple_metrics(self):
        series = {
            "improving": [1.0, 2.0, 3.0, 4.0, 5.0],
            "degrading": [5.0, 4.0, 3.0, 2.0, 1.0],
            "stable": [3.0, 3.0, 3.0, 3.0, 3.0],
        }
        trends = detect_trends(series)
        assert len(trends) == 3
        assert trends["improving"].direction == "improving"
        assert trends["degrading"].direction == "degrading"
        assert trends["stable"].direction == "stable"

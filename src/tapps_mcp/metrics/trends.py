"""Trend detection for metrics over time.

Uses simple linear regression to detect improving, stable, or degrading trends.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TrendData:
    """Trend analysis result for a metric."""

    metric_name: str
    direction: str = "stable"  # improving, stable, degrading
    slope: float = 0.0
    r_squared: float = 0.0
    data_points: int = 0
    first_value: float = 0.0
    last_value: float = 0.0
    change_pct: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "direction": self.direction,
            "slope": round(self.slope, 6),
            "r_squared": round(self.r_squared, 4),
            "data_points": self.data_points,
            "first_value": round(self.first_value, 4),
            "last_value": round(self.last_value, 4),
            "change_pct": round(self.change_pct, 2),
        }


# Threshold for significance: slopes smaller than this are "stable"
_SLOPE_THRESHOLD = 0.001
# R-squared threshold: below this, the trend is too noisy to be meaningful
_R_SQUARED_THRESHOLD = 0.1


def calculate_trend(
    metric_name: str,
    values: list[float],
    slope_threshold: float = _SLOPE_THRESHOLD,
) -> TrendData:
    """Calculate trend direction from a time series of values.

    Uses ordinary least squares linear regression. The x-axis is simply
    the index of each value (0, 1, 2, ...).

    Args:
        metric_name: Name of the metric being analyzed.
        values: Time-ordered values (oldest first).
        slope_threshold: Minimum absolute slope to consider non-stable.

    Returns:
        TrendData with direction, slope, and supporting statistics.
    """
    n = len(values)
    if n < 2:
        return TrendData(
            metric_name=metric_name,
            data_points=n,
            first_value=values[0] if values else 0.0,
            last_value=values[-1] if values else 0.0,
        )

    # Simple linear regression: y = mx + b
    x_vals = list(range(n))
    x_mean = sum(x_vals) / n
    y_mean = sum(values) / n

    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_vals, values, strict=True))
    denominator = sum((x - x_mean) ** 2 for x in x_vals)

    if denominator == 0:
        return TrendData(
            metric_name=metric_name,
            data_points=n,
            first_value=values[0],
            last_value=values[-1],
        )

    slope = numerator / denominator

    # R-squared
    y_pred = [slope * x + (y_mean - slope * x_mean) for x in x_vals]
    ss_res = sum((y - yp) ** 2 for y, yp in zip(values, y_pred, strict=True))
    ss_tot = sum((y - y_mean) ** 2 for y in values)
    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

    # Determine direction
    if abs(slope) < slope_threshold or r_squared < _R_SQUARED_THRESHOLD:
        direction = "stable"
    elif slope > 0:
        direction = "improving"
    else:
        direction = "degrading"

    # Change percentage
    change_pct = 0.0
    if values[0] != 0:
        change_pct = ((values[-1] - values[0]) / abs(values[0])) * 100.0

    return TrendData(
        metric_name=metric_name,
        direction=direction,
        slope=slope,
        r_squared=r_squared,
        data_points=n,
        first_value=values[0],
        last_value=values[-1],
        change_pct=change_pct,
    )


def detect_trends(
    metric_series: dict[str, list[float]],
    slope_threshold: float = _SLOPE_THRESHOLD,
) -> dict[str, TrendData]:
    """Detect trends for multiple metric time series.

    Args:
        metric_series: Dict of metric_name -> time-ordered values.
        slope_threshold: Minimum absolute slope for non-stable.

    Returns:
        Dict of metric_name -> TrendData.
    """
    return {
        name: calculate_trend(name, values, slope_threshold)
        for name, values in metric_series.items()
    }

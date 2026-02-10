"""Analytics alerting system.

Threshold-based alerting for quality metric degradation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

import structlog

from tapps_mcp.common.utils import utc_now

logger = structlog.get_logger(__name__)


class AlertSeverity(StrEnum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class AlertCondition:
    """A configurable alert condition."""

    name: str
    metric_type: str  # gate_pass_rate, avg_score, cache_hit_rate, etc.
    threshold: float
    condition: str  # below, above, change
    severity: AlertSeverity = AlertSeverity.WARNING
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value
        return d


@dataclass
class Alert:
    """A triggered alert."""

    condition_name: str
    metric_type: str
    current_value: float
    threshold: float
    message: str
    severity: AlertSeverity = AlertSeverity.WARNING
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value
        return d


# Default alert conditions
_DEFAULT_CONDITIONS: list[AlertCondition] = [
    AlertCondition(
        name="gate_pass_rate_low",
        metric_type="gate_pass_rate",
        threshold=0.50,
        condition="below",
        severity=AlertSeverity.WARNING,
    ),
    AlertCondition(
        name="gate_pass_rate_critical",
        metric_type="gate_pass_rate",
        threshold=0.25,
        condition="below",
        severity=AlertSeverity.CRITICAL,
    ),
    AlertCondition(
        name="cache_hit_rate_low",
        metric_type="cache_hit_rate",
        threshold=0.60,
        condition="below",
        severity=AlertSeverity.WARNING,
    ),
    AlertCondition(
        name="confidence_low",
        metric_type="avg_confidence",
        threshold=0.50,
        condition="below",
        severity=AlertSeverity.WARNING,
    ),
    AlertCondition(
        name="error_rate_high",
        metric_type="error_rate",
        threshold=0.20,
        condition="above",
        severity=AlertSeverity.CRITICAL,
    ),
]


class AlertManager:
    """Manages alert conditions and evaluates them against metrics."""

    def __init__(
        self,
        conditions: list[AlertCondition] | None = None,
    ) -> None:
        self._conditions = conditions or list(_DEFAULT_CONDITIONS)

    @property
    def conditions(self) -> list[AlertCondition]:
        return list(self._conditions)

    def add_condition(self, condition: AlertCondition) -> None:
        """Add a custom alert condition."""
        self._conditions.append(condition)

    def check_alerts(self, metrics: dict[str, float]) -> list[Alert]:
        """Evaluate all conditions against provided metrics.

        Args:
            metrics: Dict of metric_type -> current_value.

        Returns:
            List of triggered alerts.
        """
        triggered: list[Alert] = []
        now = utc_now().isoformat()

        for cond in self._conditions:
            if not cond.enabled:
                continue

            value = metrics.get(cond.metric_type)
            if value is None:
                continue

            fired = (cond.condition == "below" and value < cond.threshold) or (
                cond.condition == "above" and value > cond.threshold
            )

            if fired:
                triggered.append(
                    Alert(
                        condition_name=cond.name,
                        metric_type=cond.metric_type,
                        current_value=round(value, 4),
                        threshold=cond.threshold,
                        message=self._format_message(cond, value),
                        severity=cond.severity,
                        timestamp=now,
                    )
                )

        return triggered

    def get_active_alerts(self, metrics: dict[str, float]) -> list[Alert]:
        """Alias for check_alerts."""
        return self.check_alerts(metrics)

    @staticmethod
    def _format_message(cond: AlertCondition, value: float) -> str:
        direction = "below" if cond.condition == "below" else "above"
        return (
            f"{cond.name}: {cond.metric_type} is {value:.4f}, "
            f"{direction} threshold {cond.threshold:.4f}"
        )

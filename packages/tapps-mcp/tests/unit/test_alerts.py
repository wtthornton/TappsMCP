"""Tests for analytics alerting system."""

from tapps_mcp.metrics.alerts import (
    AlertCondition,
    AlertManager,
    AlertSeverity,
)


class TestAlertSeverity:
    def test_values(self):
        assert AlertSeverity.INFO == "info"
        assert AlertSeverity.WARNING == "warning"
        assert AlertSeverity.CRITICAL == "critical"


class TestAlertCondition:
    def test_to_dict(self):
        cond = AlertCondition(
            name="test_alert",
            metric_type="gate_pass_rate",
            threshold=0.5,
            condition="below",
            severity=AlertSeverity.WARNING,
        )
        d = cond.to_dict()
        assert d["severity"] == "warning"
        assert d["threshold"] == 0.5


class TestAlertManager:
    def test_default_conditions(self):
        manager = AlertManager()
        assert len(manager.conditions) > 0

    def test_check_alerts_below_threshold(self):
        manager = AlertManager()
        metrics = {"gate_pass_rate": 0.20}
        alerts = manager.check_alerts(metrics)

        # Should trigger both gate_pass_rate_low and gate_pass_rate_critical
        names = [a.condition_name for a in alerts]
        assert "gate_pass_rate_low" in names
        assert "gate_pass_rate_critical" in names

    def test_check_alerts_above_threshold(self):
        manager = AlertManager()
        metrics = {"error_rate": 0.30}
        alerts = manager.check_alerts(metrics)

        names = [a.condition_name for a in alerts]
        assert "error_rate_high" in names

    def test_no_alerts_when_healthy(self):
        manager = AlertManager()
        metrics = {
            "gate_pass_rate": 0.80,
            "cache_hit_rate": 0.90,
            "avg_confidence": 0.75,
            "error_rate": 0.05,
        }
        alerts = manager.check_alerts(metrics)
        assert len(alerts) == 0

    def test_custom_condition(self):
        manager = AlertManager(conditions=[])
        manager.add_condition(
            AlertCondition(
                name="custom_test",
                metric_type="my_metric",
                threshold=10.0,
                condition="above",
                severity=AlertSeverity.INFO,
            )
        )
        alerts = manager.check_alerts({"my_metric": 15.0})
        assert len(alerts) == 1
        assert alerts[0].condition_name == "custom_test"

    def test_disabled_condition(self):
        cond = AlertCondition(
            name="disabled_test",
            metric_type="gate_pass_rate",
            threshold=0.5,
            condition="below",
            enabled=False,
        )
        manager = AlertManager(conditions=[cond])
        alerts = manager.check_alerts({"gate_pass_rate": 0.1})
        assert len(alerts) == 0

    def test_missing_metric(self):
        manager = AlertManager()
        alerts = manager.check_alerts({})
        assert len(alerts) == 0

    def test_alert_message_format(self):
        manager = AlertManager(
            conditions=[
                AlertCondition(
                    name="test",
                    metric_type="score",
                    threshold=0.5,
                    condition="below",
                )
            ]
        )
        alerts = manager.check_alerts({"score": 0.3})
        assert "test" in alerts[0].message
        assert "0.3" in alerts[0].message

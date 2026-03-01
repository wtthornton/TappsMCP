"""Tests for gates.models."""

import pytest
from pydantic import ValidationError

from tapps_mcp.gates.models import GateFailure, GateResult, GateThresholds


class TestGateThresholds:
    def test_defaults(self):
        t = GateThresholds()
        assert t.overall_min == 70.0
        assert t.security_min == 0.0
        assert t.maintainability_min == 0.0
        assert t.complexity_max == 10.0
        assert t.test_coverage_min == 0.0
        assert t.performance_min == 0.0

    def test_custom(self):
        t = GateThresholds(overall_min=80.0, security_min=7.0)
        assert t.overall_min == 80.0
        assert t.security_min == 7.0

    def test_overall_min_bound(self):
        with pytest.raises(ValidationError):
            GateThresholds(overall_min=-1.0)
        with pytest.raises(ValidationError):
            GateThresholds(overall_min=101.0)

    def test_category_bounds(self):
        with pytest.raises(ValidationError):
            GateThresholds(security_min=-0.1)
        with pytest.raises(ValidationError):
            GateThresholds(security_min=10.1)


class TestGateFailure:
    def test_creation(self):
        f = GateFailure(
            category="security",
            actual=5.0,
            threshold=7.0,
            message="Security 5.0 < 7.0",
        )
        assert f.category == "security"
        assert f.actual == 5.0
        assert f.threshold == 7.0


class TestGateResult:
    def test_passed(self):
        r = GateResult(
            passed=True,
            scores={"overall": 85.0},
            preset="standard",
        )
        assert r.passed is True
        assert r.failures == []
        assert r.warnings == []

    def test_failed(self):
        failure = GateFailure(
            category="overall",
            actual=60.0,
            threshold=70.0,
            message="Overall 60.0 < 70.0",
        )
        r = GateResult(
            passed=False,
            failures=[failure],
            scores={"overall": 60.0},
            preset="standard",
        )
        assert r.passed is False
        assert len(r.failures) == 1

    def test_with_warnings(self):
        r = GateResult(
            passed=True,
            warnings=["Degraded result"],
            scores={"overall": 75.0},
            preset="standard",
        )
        assert len(r.warnings) == 1

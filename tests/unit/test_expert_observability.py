"""Tests for expert observability system."""

import pytest

from tapps_mcp.metrics.confidence_metrics import ConfidenceMetricsTracker
from tapps_mcp.metrics.expert_observability import (
    ObservabilitySystem,
)


@pytest.fixture
def metrics_dir(tmp_path):
    d = tmp_path / "metrics"
    d.mkdir()
    return d


@pytest.fixture
def system(metrics_dir):
    return ObservabilitySystem(metrics_dir)


class TestObservabilitySystem:
    def test_identify_weak_areas_empty(self, system):
        weak = system.identify_weak_areas()
        assert isinstance(weak, list)

    def test_identify_low_confidence(self, metrics_dir):
        conf = ConfidenceMetricsTracker(metrics_dir)
        for _ in range(5):
            conf.record("security", 0.3, 0.6)

        system = ObservabilitySystem(
            metrics_dir,
            confidence_tracker=conf,
        )
        weak = system.identify_weak_areas()
        low_conf = [w for w in weak if w.weakness_type == "low_confidence"]
        assert len(low_conf) > 0
        assert low_conf[0].domain == "security"

    def test_generate_improvement_proposals(self, metrics_dir):
        conf = ConfidenceMetricsTracker(metrics_dir)
        for _ in range(5):
            conf.record("security", 0.2, 0.6)  # Critical low confidence

        system = ObservabilitySystem(
            metrics_dir,
            confidence_tracker=conf,
        )
        proposals = system.generate_improvement_proposals()
        assert len(proposals) > 0
        assert proposals[0].domain == "security"
        assert proposals[0].proposal_type == "add_knowledge"

    def test_weak_areas_saved_to_file(self, system, metrics_dir):
        system.identify_weak_areas()
        assert (metrics_dir / "weak_areas.json").exists()

    def test_proposals_saved_to_file(self, system, metrics_dir):
        system.generate_improvement_proposals()
        assert (metrics_dir / "improvement_proposals.json").exists()

    def test_severity_levels(self, metrics_dir):
        conf = ConfidenceMetricsTracker(metrics_dir)
        # Very low confidence -> critical
        for _ in range(5):
            conf.record("domain_a", 0.1, 0.5)
        # Moderate low confidence -> warning
        for _ in range(5):
            conf.record("domain_b", 0.4, 0.5)

        system = ObservabilitySystem(metrics_dir, confidence_tracker=conf)
        weak = system.identify_weak_areas()
        severities = {w.domain: w.severity for w in weak}
        assert severities.get("domain_a") == "critical"
        assert severities.get("domain_b") == "warning"

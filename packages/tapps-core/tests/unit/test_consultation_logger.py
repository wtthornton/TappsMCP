"""Tests for consultation logger."""

import pytest

from tapps_core.metrics.consultation_logger import (
    ConsultationLogger,
)


@pytest.fixture
def metrics_dir(tmp_path):
    d = tmp_path / "metrics"
    d.mkdir()
    return d


@pytest.fixture
def logger_instance(metrics_dir):
    return ConsultationLogger(metrics_dir)


class TestConsultationLogger:
    def test_log_consultation(self, logger_instance):
        entry = logger_instance.log_consultation(
            expert_id="security_expert",
            domain="security",
            confidence=0.85,
            reasoning="Used OWASP guidelines",
            context_summary="Password hashing question",
        )
        assert entry.expert_id == "security_expert"
        assert entry.confidence == 0.85

    def test_get_recent(self, logger_instance):
        for i in range(10):
            logger_instance.log_consultation(f"exp{i}", "security", 0.7)

        recent = logger_instance.get_recent(limit=5)
        assert len(recent) == 5

    def test_get_by_expert(self, logger_instance):
        logger_instance.log_consultation("exp1", "security", 0.8)
        logger_instance.log_consultation("exp2", "testing", 0.9)
        logger_instance.log_consultation("exp1", "security", 0.7)

        results = logger_instance.get_by_expert("exp1")
        assert len(results) == 2

    def test_get_by_domain(self, logger_instance):
        logger_instance.log_consultation("exp1", "security", 0.8)
        logger_instance.log_consultation("exp2", "testing", 0.9)

        results = logger_instance.get_by_domain("testing")
        assert len(results) == 1

    def test_get_statistics(self, logger_instance):
        logger_instance.log_consultation("exp1", "security", 0.8)
        logger_instance.log_consultation("exp2", "testing", 0.9)

        stats = logger_instance.get_statistics()
        assert stats["total_consultations"] == 2
        assert "security" in stats["domains"]
        assert "exp1" in stats["experts"]

    def test_rotate(self, logger_instance):
        for i in range(20):
            logger_instance.log_consultation(f"exp{i}", "security", 0.7)

        removed = logger_instance.rotate(keep_recent=5)
        assert removed == 15

        remaining = logger_instance.get_recent(limit=100)
        assert len(remaining) == 5

    def test_reasoning_truncation(self, logger_instance):
        long_reasoning = "x" * 1000
        entry = logger_instance.log_consultation("exp1", "test", 0.8, reasoning=long_reasoning)
        assert len(entry.reasoning) == 500

    def test_empty_statistics(self, logger_instance):
        stats = logger_instance.get_statistics()
        assert stats["total_consultations"] == 0

"""Tests for adaptive learning models."""

from __future__ import annotations

from tapps_mcp.adaptive.models import (
    AdaptiveWeightsSnapshot,
    CodeOutcome,
    ExpertPerformance,
    ExpertWeightMatrix,
    ExpertWeightsSnapshot,
)


class TestCodeOutcome:
    def test_create_minimal(self):
        o = CodeOutcome(workflow_id="wf-1", file_path="main.py")
        assert o.workflow_id == "wf-1"
        assert o.file_path == "main.py"
        assert o.iterations == 1
        assert o.first_pass_success is False
        assert o.timestamp  # auto-populated

    def test_create_full(self):
        o = CodeOutcome(
            workflow_id="wf-2",
            file_path="app.py",
            initial_scores={"complexity": 7.0, "security": 8.0},
            final_scores={"complexity": 8.0, "security": 9.0},
            iterations=3,
            expert_consultations=["expert-security"],
            time_to_correctness=12.5,
            first_pass_success=True,
            agent_id="agent-1",
            prompt_hash="abc123",
        )
        assert o.iterations == 3
        assert o.first_pass_success is True
        assert o.agent_id == "agent-1"

    def test_serialization_roundtrip(self):
        o = CodeOutcome(
            workflow_id="wf-3",
            file_path="test.py",
            initial_scores={"complexity": 5.0},
        )
        data = o.model_dump()
        restored = CodeOutcome.model_validate(data)
        assert restored.workflow_id == o.workflow_id
        assert restored.initial_scores == o.initial_scores
        assert restored.timestamp == o.timestamp


class TestExpertPerformance:
    def test_create_defaults(self):
        p = ExpertPerformance(expert_id="expert-1")
        assert p.consultations == 0
        assert p.avg_confidence == 0.0
        assert p.weaknesses == []
        assert p.last_updated  # auto-populated

    def test_with_data(self):
        p = ExpertPerformance(
            expert_id="expert-security",
            consultations=50,
            avg_confidence=0.85,
            first_pass_success_rate=0.72,
            domain_coverage=["security", "authentication"],
            weaknesses=["stale_knowledge"],
        )
        assert p.avg_confidence == 0.85
        assert len(p.domain_coverage) == 2


class TestExpertWeightMatrix:
    def _make_matrix(self):
        return ExpertWeightMatrix(
            weights={
                "expert-a": {"domain-x": 0.51, "domain-y": 0.49},
                "expert-b": {"domain-x": 0.49, "domain-y": 0.51},
            },
            domains=["domain-x", "domain-y"],
            experts=["expert-a", "expert-b"],
        )

    def test_get_expert_weight(self):
        m = self._make_matrix()
        assert m.get_expert_weight("expert-a", "domain-x") == 0.51
        assert m.get_expert_weight("expert-b", "domain-x") == 0.49
        assert m.get_expert_weight("unknown", "domain-x") == 0.0

    def test_get_primary_expert(self):
        m = self._make_matrix()
        assert m.get_primary_expert("domain-x") == "expert-a"
        assert m.get_primary_expert("domain-y") == "expert-b"

    def test_get_primary_expert_domain(self):
        m = self._make_matrix()
        assert m.get_primary_expert_domain("expert-a") == "domain-x"
        assert m.get_primary_expert_domain("expert-b") == "domain-y"

    def test_validate_valid_matrix(self):
        m = self._make_matrix()
        errors = m.validate_matrix()
        assert errors == []

    def test_validate_invalid_sums(self):
        m = ExpertWeightMatrix(
            weights={"expert-a": {"domain-x": 0.3}},
            domains=["domain-x"],
            experts=["expert-a"],
        )
        errors = m.validate_matrix()
        assert any("sum" in e.lower() or "0.3" in e for e in errors)

    def test_validate_no_primary(self):
        m = ExpertWeightMatrix(
            weights={
                "expert-a": {"domain-x": 0.5},
                "expert-b": {"domain-x": 0.5},
            },
            domains=["domain-x"],
            experts=["expert-a", "expert-b"],
        )
        errors = m.validate_matrix()
        assert any("primary" in e.lower() for e in errors)


class TestAdaptiveWeightsSnapshot:
    def test_serialization_roundtrip(self):
        s = AdaptiveWeightsSnapshot(
            weights={"complexity": 0.2, "security": 0.3},
            correlations={"complexity": 0.5},
            outcomes_analyzed=42,
            learning_rate=0.1,
        )
        data = s.model_dump()
        restored = AdaptiveWeightsSnapshot.model_validate(data)
        assert restored.weights == s.weights
        assert restored.outcomes_analyzed == 42


class TestExpertWeightsSnapshot:
    def test_serialization_roundtrip(self):
        matrix = ExpertWeightMatrix(
            weights={"expert-a": {"domain-x": 1.0}},
            domains=["domain-x"],
            experts=["expert-a"],
        )
        s = ExpertWeightsSnapshot(
            matrix=matrix,
            performance_summary={"expert-a": 0.9},
        )
        data = s.model_dump()
        restored = ExpertWeightsSnapshot.model_validate(data)
        assert restored.matrix.domains == ["domain-x"]

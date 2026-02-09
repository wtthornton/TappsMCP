"""Unit tests for tapps_mcp.experts.models."""

from __future__ import annotations

from tapps_mcp.experts.models import (
    ConfidenceFactors,
    ConsultationResult,
    DomainMapping,
    ExpertConfig,
    ExpertInfo,
    KnowledgeChunk,
    StackDetectionResult,
)


class TestExpertConfig:
    """Tests for ExpertConfig model."""

    def test_minimal_creation(self) -> None:
        cfg = ExpertConfig(
            expert_id="expert-security",
            expert_name="Security Expert",
            primary_domain="security",
        )
        assert cfg.expert_id == "expert-security"
        assert cfg.rag_enabled is True
        assert cfg.knowledge_dir is None
        assert cfg.description == ""

    def test_with_all_fields(self) -> None:
        cfg = ExpertConfig(
            expert_id="expert-testing",
            expert_name="Testing Expert",
            primary_domain="testing-strategies",
            description="Test strategy and coverage.",
            rag_enabled=False,
            knowledge_dir="testing",
        )
        assert cfg.knowledge_dir == "testing"
        assert cfg.rag_enabled is False
        assert cfg.description == "Test strategy and coverage."

    def test_forbids_extra_fields(self) -> None:
        import pytest

        with pytest.raises(Exception):  # noqa: B017
            ExpertConfig(
                expert_id="x",
                expert_name="x",
                primary_domain="x",
                unknown_field="boom",  # type: ignore[call-arg]
            )

    def test_serialisation_round_trip(self) -> None:
        cfg = ExpertConfig(
            expert_id="expert-perf",
            expert_name="Performance Expert",
            primary_domain="performance-optimization",
        )
        data = cfg.model_dump()
        restored = ExpertConfig(**data)
        assert restored == cfg


class TestKnowledgeChunk:
    """Tests for KnowledgeChunk model."""

    def test_defaults(self) -> None:
        chunk = KnowledgeChunk(
            content="Hello", source_file="security/vuln.md", line_start=1, line_end=5
        )
        assert chunk.score == 0.0

    def test_with_score(self) -> None:
        chunk = KnowledgeChunk(
            content="X", source_file="a.md", line_start=1, line_end=1, score=0.85
        )
        assert chunk.score == 0.85


class TestConfidenceFactors:
    """Tests for ConfidenceFactors model."""

    def test_defaults(self) -> None:
        f = ConfidenceFactors()
        assert f.rag_quality == 0.0
        assert f.domain_relevance == 1.0
        assert f.source_count == 0
        assert f.chunk_coverage == 0.0

    def test_custom(self) -> None:
        f = ConfidenceFactors(rag_quality=0.9, source_count=3, chunk_coverage=0.75)
        assert f.rag_quality == 0.9
        assert f.source_count == 3


class TestConsultationResult:
    """Tests for ConsultationResult model."""

    def test_creation(self) -> None:
        result = ConsultationResult(
            domain="security",
            expert_id="expert-security",
            expert_name="Security Expert",
            answer="Use parameterised queries.",
            confidence=0.85,
        )
        assert result.chunks_used == 0
        assert result.sources == []
        assert result.factors.rag_quality == 0.0


class TestDomainMapping:
    """Tests for DomainMapping model."""

    def test_creation(self) -> None:
        dm = DomainMapping(domain="security", confidence=0.9)
        assert dm.signals == []
        assert dm.reasoning == ""

    def test_with_signals(self) -> None:
        dm = DomainMapping(
            domain="testing-strategies",
            confidence=0.7,
            signals=["keyword:pytest", "keyword:test"],
            reasoning="Matched 2 keywords.",
        )
        assert len(dm.signals) == 2


class TestStackDetectionResult:
    """Tests for StackDetectionResult model."""

    def test_empty(self) -> None:
        r = StackDetectionResult()
        assert r.detected_domains == []
        assert r.primary_language is None


class TestExpertInfo:
    """Tests for ExpertInfo model."""

    def test_creation(self) -> None:
        info = ExpertInfo(
            expert_id="expert-security",
            expert_name="Security Expert",
            primary_domain="security",
            knowledge_files=12,
        )
        assert info.knowledge_files == 12
        assert info.rag_enabled is True

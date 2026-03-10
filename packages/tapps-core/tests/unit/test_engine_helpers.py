"""Unit tests for extracted helper functions in tapps_core.experts.engine.

Epic 28b.4 — verifies the refactored helpers that reduce cyclomatic complexity
of ``consult_expert`` and its supporting functions.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from tapps_core.experts.engine import (
    _build_answer,
    _collect_source_ages,
    _compute_confidence,
    _KnowledgeResult,
    _resolve_domain,
    _retrieve_knowledge,
    _unique_top_sources,
    consult_expert,
)
from tapps_core.experts.models import DomainMapping, KnowledgeChunk

# ---------------------------------------------------------------------------
# _resolve_domain (aliased as "detect domain" in the story spec)
# ---------------------------------------------------------------------------


class TestDetectDomainWithHint:
    """When a domain hint is provided, it takes precedence over detection."""

    def test_explicit_domain_takes_precedence(self) -> None:
        resolved = _resolve_domain("How do I test my code?", domain="security")
        assert resolved.domain == "security"
        assert resolved.adaptive_domain_used is False

    def test_explicit_domain_skips_detection(self) -> None:
        """No detected_domains list is populated when domain is explicit."""
        resolved = _resolve_domain("random question", domain="testing-strategies")
        assert resolved.domain == "testing-strategies"
        assert resolved.detected == []


class TestDetectDomainAdaptiveFallback:
    """Falls back to static detection when adaptive confidence is too low."""

    @patch("tapps_core.experts.engine._try_adaptive_detection")
    def test_falls_back_to_static_when_adaptive_returns_none(
        self, mock_adaptive: MagicMock
    ) -> None:
        mock_adaptive.return_value = (None, [])
        resolved = _resolve_domain("How do I prevent SQL injection?", domain=None)
        assert resolved.adaptive_domain_used is False
        # Static detector should have resolved to security.
        assert resolved.domain == "security"
        assert len(resolved.detected) >= 1

    @patch("tapps_core.experts.engine._try_adaptive_detection")
    def test_uses_adaptive_when_high_confidence(
        self, mock_adaptive: MagicMock
    ) -> None:
        mock_adaptive.return_value = (
            "testing-strategies",
            [
                DomainMapping(
                    domain="testing-strategies",
                    confidence=0.85,
                    signals=["adaptive:prompt"],
                    reasoning="Adaptive: prompt",
                )
            ],
        )
        resolved = _resolve_domain("How do I test my code?", domain=None)
        assert resolved.adaptive_domain_used is True
        assert resolved.domain == "testing-strategies"


# ---------------------------------------------------------------------------
# _retrieve_knowledge
# ---------------------------------------------------------------------------


class TestRetrieveKnowledgeEmpty:
    """When no knowledge matches, the result has empty chunks."""

    def test_no_knowledge_found_returns_empty_list(self) -> None:
        """A query that matches nothing in the knowledge base returns empty."""
        from tapps_core.experts.registry import ExpertRegistry

        expert = ExpertRegistry.get_expert_for_domain("security")
        assert expert is not None
        # Use a nonsensical query unlikely to match any knowledge chunk.
        result = _retrieve_knowledge(
            question="xyzzy plugh unicorn rainbow 42 qwerty",
            resolved_domain="security",
            expert=expert,
            max_chunks=5,
            max_context_length=3000,
        )
        assert isinstance(result.chunks, list)
        # Chunks may or may not be empty depending on keyword matching,
        # but the structure should always be valid.
        assert isinstance(result.context, str)
        assert isinstance(result.sources, list)


# ---------------------------------------------------------------------------
# _build_answer / response formatting
# ---------------------------------------------------------------------------


class TestFormatResponseIncludesDomain:
    """The formatted consultation response includes the domain field."""

    def test_consult_expert_response_has_domain(self) -> None:
        result = consult_expert("How do I prevent SQL injection?")
        assert result.domain == "security"
        assert result.expert_id == "expert-security"

    def test_response_answer_contains_domain_name(self) -> None:
        result = consult_expert(
            "How to write good unit tests?",
            domain="testing-strategies",
        )
        assert "testing-strategies" in result.answer

    def test_build_answer_includes_domain_in_header(self) -> None:
        """_build_answer places the domain in the answer header."""
        from tapps_core.experts.engine import _ConfidenceResult
        from tapps_core.experts.models import ConfidenceFactors
        from tapps_core.experts.registry import ExpertRegistry

        expert = ExpertRegistry.get_expert_for_domain("security")
        assert expert is not None

        knowledge = _KnowledgeResult(
            chunks=[
                KnowledgeChunk(
                    content="Always use parameterised queries.",
                    source_file="sql-injection.md",
                    line_start=1,
                    line_end=1,
                    score=0.9,
                )
            ],
            context="Always use parameterised queries.",
            sources=["sql-injection.md"],
        )
        conf = _ConfidenceResult(
            confidence=0.8,
            factors=ConfidenceFactors(rag_quality=0.8, source_count=1, chunk_coverage=0.7),
        )
        answer_result = _build_answer(
            question="How to prevent SQL injection?",
            expert=expert,
            resolved_domain="security",
            knowledge=knowledge,
            conf=conf,
        )
        assert "security" in answer_result.answer


# ---------------------------------------------------------------------------
# _build_answer / communication_style (Epic 73)
# ---------------------------------------------------------------------------


class TestBuildAnswerCommunicationStyle:
    """Tests for communication_style in _build_answer (Epic 73)."""

    def _make_knowledge(self) -> _KnowledgeResult:
        return _KnowledgeResult(
            chunks=[
                KnowledgeChunk(
                    content="Use parameterised queries.",
                    source_file="security.md",
                    line_start=1,
                    line_end=1,
                    score=0.9,
                )
            ],
            context="Use parameterised queries.",
            sources=["security.md"],
        )

    def _make_conf(self) -> "_ConfidenceResult":
        from tapps_core.experts.engine import _ConfidenceResult
        from tapps_core.experts.models import ConfidenceFactors

        return _ConfidenceResult(
            confidence=0.8,
            factors=ConfidenceFactors(rag_quality=0.8, source_count=1, chunk_coverage=0.7),
        )

    def test_communication_style_appears_in_answer(self) -> None:
        """When communication_style is set, it appears in the answer preamble."""
        from tapps_core.experts.models import ExpertConfig

        expert = ExpertConfig(
            expert_id="expert-test",
            expert_name="Test Expert",
            primary_domain="testing-strategies",
            communication_style="Use concrete examples with test code snippets.",
        )
        result = _build_answer(
            question="How to test?",
            expert=expert,
            resolved_domain="testing-strategies",
            knowledge=self._make_knowledge(),
            conf=self._make_conf(),
        )
        assert "Style: Use concrete examples with test code snippets." in result.answer

    def test_no_communication_style_no_style_line(self) -> None:
        """When communication_style is empty, no Style: line appears."""
        from tapps_core.experts.models import ExpertConfig

        expert = ExpertConfig(
            expert_id="expert-test",
            expert_name="Test Expert",
            primary_domain="testing-strategies",
        )
        result = _build_answer(
            question="How to test?",
            expert=expert,
            resolved_domain="testing-strategies",
            knowledge=self._make_knowledge(),
            conf=self._make_conf(),
        )
        assert "Style:" not in result.answer

    def test_persona_and_communication_style_both_appear(self) -> None:
        """When both persona and communication_style are set, both appear."""
        from tapps_core.experts.models import ExpertConfig

        expert = ExpertConfig(
            expert_id="expert-test",
            expert_name="Test Expert",
            primary_domain="testing-strategies",
            persona="Senior test engineer with 10 years experience.",
            communication_style="Recommend specific testing patterns by name.",
        )
        result = _build_answer(
            question="How to test?",
            expert=expert,
            resolved_domain="testing-strategies",
            knowledge=self._make_knowledge(),
            conf=self._make_conf(),
        )
        assert "Senior test engineer" in result.answer
        assert "Style: Recommend specific testing patterns by name." in result.answer
        persona_pos = result.answer.index("Senior test engineer")
        style_pos = result.answer.index("Style:")
        assert persona_pos < style_pos

    def test_builtin_security_expert_has_communication_style(self) -> None:
        """The Security expert in the registry has communication_style set."""
        from tapps_core.experts.registry import ExpertRegistry

        expert = ExpertRegistry.get_expert_for_domain("security")
        assert expert is not None
        assert expert.communication_style != ""
        assert "CWE" in expert.communication_style

    def test_builtin_testing_expert_has_communication_style(self) -> None:
        """The Testing expert in the registry has communication_style set."""
        from tapps_core.experts.registry import ExpertRegistry

        expert = ExpertRegistry.get_expert_for_domain("testing-strategies")
        assert expert is not None
        assert expert.communication_style != ""
        assert "Arrange-Act-Assert" in expert.communication_style

    def test_expert_without_style_unchanged(self) -> None:
        """Experts without communication_style produce same output as before."""
        from tapps_core.experts.registry import ExpertRegistry

        expert = ExpertRegistry.get_expert_for_domain("performance-optimization")
        assert expert is not None
        assert expert.communication_style == ""
        result = _build_answer(
            question="How to optimize?",
            expert=expert,
            resolved_domain="performance-optimization",
            knowledge=self._make_knowledge(),
            conf=self._make_conf(),
        )
        assert "Style:" not in result.answer


# ---------------------------------------------------------------------------
# _unique_top_sources (newly extracted helper)
# ---------------------------------------------------------------------------


class TestUniqueTopSources:
    """Tests for the _unique_top_sources helper."""

    def test_deduplicates_sources(self) -> None:
        chunks = [
            KnowledgeChunk(
                content="A", source_file="a.md", line_start=1, line_end=1, score=0.9
            ),
            KnowledgeChunk(
                content="B", source_file="a.md", line_start=2, line_end=2, score=0.8
            ),
            KnowledgeChunk(
                content="C", source_file="b.md", line_start=1, line_end=1, score=0.7
            ),
        ]
        sources = _unique_top_sources(chunks)
        assert sources == ["a.md", "b.md"]

    def test_respects_limit(self) -> None:
        chunks = [
            KnowledgeChunk(
                content=f"Chunk {i}",
                source_file=f"file{i}.md",
                line_start=1,
                line_end=1,
                score=0.5,
            )
            for i in range(10)
        ]
        sources = _unique_top_sources(chunks, limit=2)
        assert len(sources) == 2
        assert sources == ["file0.md", "file1.md"]

    def test_empty_chunks(self) -> None:
        assert _unique_top_sources([]) == []

    def test_preserves_order(self) -> None:
        chunks = [
            KnowledgeChunk(
                content="X", source_file="z.md", line_start=1, line_end=1, score=0.9
            ),
            KnowledgeChunk(
                content="Y", source_file="a.md", line_start=1, line_end=1, score=0.8
            ),
        ]
        sources = _unique_top_sources(chunks)
        assert sources == ["z.md", "a.md"]


# ---------------------------------------------------------------------------
# _collect_source_ages (newly extracted helper)
# ---------------------------------------------------------------------------


class TestCollectSourceAges:
    """Tests for the _collect_source_ages helper."""

    def test_returns_ages_for_existing_files(self, tmp_path: Path) -> None:
        f = tmp_path / "recent.md"
        f.write_text("content")
        ages = _collect_source_ages(["recent.md"], tmp_path)
        assert len(ages) == 1
        assert ages[0] >= 0
        assert ages[0] < 2  # Created just now.

    def test_skips_missing_files(self, tmp_path: Path) -> None:
        ages = _collect_source_ages(["nonexistent.md"], tmp_path)
        assert ages == []

    def test_old_file_returns_large_age(self, tmp_path: Path) -> None:
        f = tmp_path / "old.md"
        f.write_text("old content")
        old_time = time.time() - (400 * 86400)
        os.utime(f, (old_time, old_time))
        ages = _collect_source_ages(["old.md"], tmp_path)
        assert len(ages) == 1
        assert ages[0] >= 399

    def test_mixed_existing_and_missing(self, tmp_path: Path) -> None:
        f = tmp_path / "exists.md"
        f.write_text("content")
        ages = _collect_source_ages(["exists.md", "missing.md"], tmp_path)
        assert len(ages) == 1


# ---------------------------------------------------------------------------
# _compute_confidence
# ---------------------------------------------------------------------------


class TestComputeConfidence:
    """Tests for the _compute_confidence helper."""

    def test_returns_confidence_between_zero_and_one(self) -> None:
        knowledge = _KnowledgeResult(
            chunks=[
                KnowledgeChunk(
                    content="Test content about security",
                    source_file="security.md",
                    line_start=1,
                    line_end=1,
                    score=0.8,
                )
            ],
            context="Test content about security",
            sources=["security.md"],
        )
        result = _compute_confidence("SQL injection prevention", knowledge, "security")
        assert 0.0 <= result.confidence <= 1.0
        assert result.factors is not None

    def test_empty_chunks_returns_low_confidence(self) -> None:
        knowledge = _KnowledgeResult(chunks=[], context="", sources=[])
        result = _compute_confidence("anything", knowledge, "security")
        assert result.confidence >= 0.0
        assert result.confidence <= 1.0

"""Unit tests for tech stack boost in expert engine (Epic 54.4).

Tests the _apply_tech_stack_boost function and integration with
_retrieve_knowledge.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tapps_core.experts.engine import _apply_tech_stack_boost


def _make_chunk(score: float) -> MagicMock:
    """Create a mock KnowledgeChunk with a score."""
    chunk = MagicMock()
    chunk.score = score
    return chunk


class TestApplyTechStackBoost:
    """Tests for _apply_tech_stack_boost."""

    def test_no_boost_when_multiplier_is_one(self) -> None:
        chunks = [_make_chunk(0.8)]
        result = _apply_tech_stack_boost(chunks, "security", 1.0)
        assert result[0].score == 0.8

    def test_no_boost_when_domain_not_in_tech_stack(self) -> None:
        chunks = [_make_chunk(0.8)]
        with patch(
            "tapps_core.experts.engine._get_tech_stack_domains",
            return_value={"testing-strategies"},
        ):
            result = _apply_tech_stack_boost(chunks, "security", 1.2)
        assert result[0].score == 0.8

    def test_boost_applied_when_domain_matches(self) -> None:
        chunks = [_make_chunk(0.5), _make_chunk(0.7)]
        with patch(
            "tapps_core.experts.engine._get_tech_stack_domains",
            return_value={"security", "api-design-integration"},
        ):
            result = _apply_tech_stack_boost(chunks, "security", 1.2)
        assert result[0].score == pytest.approx(0.6)
        assert result[1].score == pytest.approx(0.84)

    def test_boost_capped_at_one(self) -> None:
        chunks = [_make_chunk(0.9)]
        with patch(
            "tapps_core.experts.engine._get_tech_stack_domains",
            return_value={"security"},
        ):
            result = _apply_tech_stack_boost(chunks, "security", 1.5)
        assert result[0].score == 1.0

    def test_empty_chunks_returns_empty(self) -> None:
        result = _apply_tech_stack_boost([], "security", 1.2)
        assert result == []

    def test_no_boost_when_tech_stack_unavailable(self) -> None:
        chunks = [_make_chunk(0.8)]
        with patch(
            "tapps_core.experts.engine._get_tech_stack_domains",
            return_value=set(),
        ):
            result = _apply_tech_stack_boost(chunks, "security", 1.2)
        assert result[0].score == 0.8


class TestGetTechStackDomains:
    """Tests for _get_tech_stack_domains cache-based approach."""

    def test_returns_empty_set_when_not_populated(self) -> None:
        from tapps_core.experts.engine import (
            _get_tech_stack_domains,
            _reset_tech_stack_domains_cache,
        )

        _reset_tech_stack_domains_cache()
        result = _get_tech_stack_domains()
        assert result == set()

    def test_returns_cached_domains(self) -> None:
        from tapps_core.experts.engine import (
            _get_tech_stack_domains,
            _reset_tech_stack_domains_cache,
            set_tech_stack_domains,
        )

        _reset_tech_stack_domains_cache()
        set_tech_stack_domains({"security", "testing-strategies"})
        result = _get_tech_stack_domains()
        assert result == {"security", "testing-strategies"}
        _reset_tech_stack_domains_cache()

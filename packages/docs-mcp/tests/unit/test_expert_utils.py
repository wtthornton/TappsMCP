"""Tests for docs_mcp.generators.expert_utils."""

from __future__ import annotations

import pytest

from docs_mcp.generators.expert_utils import (
    extract_expert_advice,
    filter_expert_guidance,
    parse_confidence,
)


class TestParseConfidence:
    def test_percent_string(self) -> None:
        assert parse_confidence("85%") == 0.85
        assert parse_confidence("0%") == 0.0
        assert parse_confidence("100%") == 1.0

    def test_invalid_returns_zero(self) -> None:
        assert parse_confidence("") == 0.0
        assert parse_confidence("bad") == 0.0
        # "50" without % is parsed as 50 (0.5); only non-numeric returns 0
        assert parse_confidence("nope") == 0.0


class TestExtractExpertAdvice:
    def test_skips_header_and_boilerplate(self) -> None:
        answer = (
            "## Security Expert — security\n\n"
            "Based on domain knowledge (3 source(s), confidence 70%):\n\n"
            "Validate all input at the boundary. Use whitelist validation."
        )
        assert extract_expert_advice(answer) == (
            "Validate all input at the boundary. Use whitelist validation."
        )

    def test_skips_no_knowledge_paragraph(self) -> None:
        answer = (
            "## X — y\n\n"
            "No specific knowledge found for this query in the security knowledge base."
        )
        assert extract_expert_advice(answer) == ""

    def test_returns_empty_for_empty(self) -> None:
        assert extract_expert_advice("") == ""
        assert extract_expert_advice("   ") == ""

    def test_truncates_to_max_length(self) -> None:
        long_para = "A" * 400
        result = extract_expert_advice(long_para, max_length=100)
        assert len(result) <= 100
        assert result.endswith("...")

    def test_first_substantive_paragraph_used(self) -> None:
        answer = (
            "## Expert — domain\n\n"
            "Based on domain knowledge (1 source(s), confidence 50%):\n\n"
            "First real sentence here.\n\n"
            "Second paragraph not used."
        )
        assert "First real sentence" in extract_expert_advice(answer)
        assert "Second paragraph" not in extract_expert_advice(answer)


class TestFilterExpertGuidance:
    def test_below_30_suppressed(self) -> None:
        guidance = [
            {"domain": "security", "expert": "X", "advice": "Real", "confidence": "25%"},
        ]
        assert len(filter_expert_guidance(guidance)) == 0

    def test_30_to_50_flagged(self) -> None:
        guidance = [
            {"domain": "security", "expert": "X", "advice": "Real", "confidence": "40%"},
        ]
        result = filter_expert_guidance(guidance)
        assert len(result) == 1
        assert "Expert review recommended" in result[0]["advice"]

    def test_above_50_kept(self) -> None:
        guidance = [
            {"domain": "security", "expert": "X", "advice": "Use validation.", "confidence": "85%"},
        ]
        result = filter_expert_guidance(guidance)
        assert len(result) == 1
        assert result[0]["advice"] == "Use validation."

    def test_no_knowledge_suppressed(self) -> None:
        guidance = [
            {
                "domain": "security",
                "expert": "X",
                "advice": "No specific knowledge found for this domain.",
                "confidence": "80%",
            },
        ]
        assert len(filter_expert_guidance(guidance)) == 0

    def test_empty_advice_suppressed(self) -> None:
        guidance = [
            {"domain": "security", "expert": "X", "advice": "", "confidence": "85%"},
        ]
        assert len(filter_expert_guidance(guidance)) == 0

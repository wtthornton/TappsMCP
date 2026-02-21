"""Unit tests for the tapps_research combined tool in server.py.

Complements integration tests in test_expert_pipeline.py with edge cases
and response-shape validation that don't require the full pipeline.
"""

from __future__ import annotations

from typing import Any

from tapps_mcp.server import tapps_research


class TestTappsResearchResponseShape:
    """Validate complete response structure in a single call."""

    def test_full_response_structure(self) -> None:
        result: dict[str, Any] = tapps_research(
            question="How to prevent SQL injection?",
            domain="security",
        )
        assert result["tool"] == "tapps_research"
        assert result["success"] is True
        assert result["elapsed_ms"] >= 0
        data = result["data"]
        expected_keys = {
            "domain",
            "expert_id",
            "expert_name",
            "answer",
            "confidence",
            "factors",
            "sources",
            "chunks_used",
            "docs_supplemented",
            "docs_library",
            "docs_topic",
            "docs_error",
            "suggested_tool",
            "suggested_library",
            "suggested_topic",
            "fallback_used",
            "fallback_library",
            "fallback_topic",
        }
        assert expected_keys <= set(data.keys())
        assert isinstance(data["docs_supplemented"], bool)
        assert 0.0 <= data["confidence"] <= 1.0
        assert all(
            k in data["factors"]
            for k in ("rag_quality", "domain_relevance", "source_count", "chunk_coverage")
        )


class TestTappsResearchRouting:
    """Domain routing and auto-detection."""

    def test_explicit_domain(self) -> None:
        result = tapps_research(question="How to prevent SQL injection?", domain="security")
        assert result["data"]["domain"] == "security"
        assert result["data"]["expert_id"] == "expert-security"

    def test_auto_routing(self) -> None:
        result = tapps_research(question="How to write unit tests with pytest?", domain="")
        assert result["success"] is True
        assert result["data"]["domain"] == "testing-strategies"


class TestTappsResearchDocsLookup:
    """Docs supplementation edge cases."""

    def test_docs_error_field_type(self) -> None:
        """docs_error is None or a string, never other types."""
        result = tapps_research(
            question="How to use an obscure library xyz123?",
            domain="security",
            library="xyz123_nonexistent",
        )
        err = result["data"]["docs_error"]
        assert err is None or isinstance(err, str)

    def test_answer_nonempty(self) -> None:
        result = tapps_research(
            question="What are best practices for database migrations?",
            domain="database-data-management",
        )
        assert len(result["data"]["answer"]) > 0

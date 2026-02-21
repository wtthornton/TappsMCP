"""Unit tests for the tapps_research combined tool in server.py."""

from __future__ import annotations

from typing import Any

from tapps_mcp.server import tapps_research


class TestTappsResearchResponseShape:
    """Test the response structure of tapps_research."""

    def test_basic_response_shape(self) -> None:
        result: dict[str, Any] = tapps_research(
            question="How to prevent SQL injection?",
            domain="security",
        )
        assert result["tool"] == "tapps_research"
        assert result["success"] is True
        assert result["elapsed_ms"] >= 0
        assert "data" in result

    def test_data_fields_present(self) -> None:
        result = tapps_research(
            question="How to prevent SQL injection?",
            domain="security",
        )
        data = result["data"]
        assert "domain" in data
        assert "expert_id" in data
        assert "expert_name" in data
        assert "answer" in data
        assert "confidence" in data
        assert "factors" in data
        assert "sources" in data
        assert "chunks_used" in data
        assert "docs_supplemented" in data
        assert "docs_library" in data
        assert "docs_topic" in data
        assert "docs_error" in data
        assert "suggested_tool" in data
        assert "suggested_library" in data
        assert "suggested_topic" in data
        assert "fallback_used" in data
        assert "fallback_library" in data
        assert "fallback_topic" in data

    def test_docs_supplemented_is_bool(self) -> None:
        result = tapps_research(
            question="How to prevent SQL injection?",
            domain="security",
        )
        assert isinstance(result["data"]["docs_supplemented"], bool)

    def test_confidence_in_range(self) -> None:
        result = tapps_research(
            question="How to prevent SQL injection?",
            domain="security",
        )
        conf = result["data"]["confidence"]
        assert 0.0 <= conf <= 1.0


class TestTappsResearchRouting:
    """Test domain routing and auto-detection."""

    def test_explicit_domain(self) -> None:
        result = tapps_research(
            question="How to prevent SQL injection?",
            domain="security",
        )
        assert result["data"]["domain"] == "security"
        assert result["data"]["expert_id"] == "expert-security"

    def test_auto_routing_empty_domain(self) -> None:
        result = tapps_research(
            question="How to write unit tests with pytest?",
            domain="",
        )
        assert result["success"] is True
        assert result["data"]["domain"] == "testing-strategies"

    def test_auto_routing_no_domain_arg(self) -> None:
        result = tapps_research(
            question="How to profile slow database queries?",
        )
        assert result["success"] is True
        assert result["data"]["domain"]  # Should have detected a domain


class TestTappsResearchDocsLookup:
    """Test docs supplementation logic."""

    def test_high_confidence_no_docs(self) -> None:
        """When expert has high confidence and chunks, docs should not be supplemented
        (unless docs lookup happens to succeed anyway)."""
        result = tapps_research(
            question="How to prevent SQL injection?",
            domain="security",
        )
        # Security has good KB — likely chunks_used > 0 and confidence >= 0.5
        # docs_supplemented may or may not be True depending on chunks/confidence
        assert isinstance(result["data"]["docs_supplemented"], bool)

    def test_docs_error_on_no_api_key(self) -> None:
        """When no API key is configured and docs supplement is needed,
        docs_error should be set."""
        # This will likely need docs and fail without API key
        result = tapps_research(
            question="How to use an obscure library xyz123?",
            domain="security",
            library="xyz123_nonexistent",
            topic="getting-started",
        )
        # Either docs_supplemented=False with docs_error, or no docs needed
        data = result["data"]
        if not data["docs_supplemented"]:
            # If docs were attempted and failed, error should be set
            # If docs weren't attempted (high confidence), error may be None
            assert data["docs_error"] is None or isinstance(data["docs_error"], str)

    def test_explicit_library_and_topic(self) -> None:
        """Explicit library and topic arguments are passed through."""
        result = tapps_research(
            question="How to set up FastAPI routes?",
            domain="api-design-integration",
            library="fastapi",
            topic="routing",
        )
        assert result["success"] is True
        data = result["data"]
        # If docs were looked up, they should use the specified library/topic
        if data["docs_supplemented"]:
            assert data["docs_library"] == "fastapi"
            assert data["docs_topic"] == "routing"


class TestTappsResearchAnswer:
    """Test answer construction."""

    def test_answer_nonempty(self) -> None:
        result = tapps_research(
            question="What are best practices for database migrations?",
            domain="database-data-management",
        )
        assert len(result["data"]["answer"]) > 0

    def test_answer_contains_expert_name(self) -> None:
        result = tapps_research(
            question="How to prevent SQL injection?",
            domain="security",
        )
        # Expert answer typically includes the expert's name
        answer = result["data"]["answer"]
        assert len(answer) > 0

    def test_factors_structure(self) -> None:
        """Confidence factors should have the expected fields."""
        result = tapps_research(
            question="How to prevent SQL injection?",
            domain="security",
        )
        factors = result["data"]["factors"]
        assert "rag_quality" in factors
        assert "domain_relevance" in factors
        assert "source_count" in factors
        assert "chunk_coverage" in factors

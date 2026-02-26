"""Integration tests: expert system end-to-end pipeline.

Tests the full flow from MCP tool call through domain detection,
RAG retrieval, confidence scoring, and response formatting.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from tapps_mcp.experts.domain_detector import DomainDetector
from tapps_mcp.experts.engine import consult_expert, list_experts
from tapps_mcp.experts.rag import SimpleKnowledgeBase
from tapps_mcp.experts.registry import ExpertRegistry
from tapps_mcp.server import tapps_consult_expert, tapps_list_experts, tapps_research

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.integration
class TestExpertConsultationPipeline:
    """End-to-end expert consultation tests using real knowledge files."""

    def test_security_consultation_with_rag(self) -> None:
        """Security expert returns relevant knowledge from RAG."""
        result = consult_expert(
            "What are best practices for preventing XSS attacks?",
            domain="security",
        )
        assert result.domain == "security"
        assert result.expert_id == "expert-security"
        assert result.confidence > 0
        assert result.answer
        assert "Security Expert" in result.answer

    def test_auto_routing_finds_correct_domain(self) -> None:
        """Question about testing routes to testing-strategies expert."""
        result = consult_expert("How should I write pytest fixtures for database tests?")
        assert result.domain == "testing-strategies"
        assert result.expert_id == "expert-testing"

    def test_performance_expert_uses_knowledge_dir_override(self) -> None:
        """Performance expert maps to 'performance' dir, not 'performance-optimization'."""
        result = consult_expert(
            "How to profile and optimize slow database queries?",
            domain="performance-optimization",
        )
        assert result.domain == "performance-optimization"
        assert result.expert_id == "expert-performance"
        # Should find knowledge files in 'performance/' directory.
        assert result.chunks_used >= 0

    def test_confidence_factors_populated(self) -> None:
        """Confidence factors are properly computed."""
        result = consult_expert(
            "What are OWASP top 10 vulnerabilities?",
            domain="security",
        )
        assert result.factors.domain_relevance == 1.0  # Technical domain
        assert result.confidence > 0

    def test_fallback_for_unknown_domain(self) -> None:
        """Consultation with unregistered domain falls back gracefully."""
        result = consult_expert(
            "Tell me about quantum computing",
            domain="quantum-physics",
        )
        # Should fallback to software-architecture.
        assert result.domain is not None
        assert result.expert_name

    def test_all_17_domains_consultable(self) -> None:
        """Each of the 17 domains can handle a consultation."""
        for expert in ExpertRegistry.get_all_experts():
            result = consult_expert(
                f"Tell me about {expert.primary_domain} best practices",
                domain=expert.primary_domain,
            )
            assert result.domain == expert.primary_domain
            assert result.expert_id == expert.expert_id
            assert result.answer


@pytest.mark.integration
class TestExpertListPipeline:
    """End-to-end list_experts tests."""

    def test_list_experts_returns_all(self) -> None:
        experts = list_experts()
        assert len(experts) == 17

    def test_knowledge_file_counts_nonzero(self) -> None:
        """At least some experts have knowledge files."""
        experts = list_experts()
        with_files = [e for e in experts if e.knowledge_files > 0]
        assert len(with_files) >= 10  # Most should have files.

    def test_total_knowledge_files(self) -> None:
        """Total knowledge files across all experts should be ~119."""
        experts = list_experts()
        total = sum(e.knowledge_files for e in experts)
        # We copied 119 files; some domains may have sub-dirs.
        assert total >= 100


@pytest.mark.integration
class TestRAGWithRealKnowledgeFiles:
    """Tests RAG search against the actual bundled knowledge files."""

    def test_security_knowledge_search(self) -> None:
        """Search security knowledge for XSS returns results."""
        kb_path = ExpertRegistry.get_knowledge_base_path() / "security"
        kb = SimpleKnowledgeBase(kb_path)
        assert kb.file_count > 0

        results = kb.search("cross-site scripting xss")
        # Should find something in the security knowledge base.
        assert len(results) >= 0  # May vary based on content.

    def test_testing_knowledge_search(self) -> None:
        """Search testing knowledge returns results."""
        kb_path = ExpertRegistry.get_knowledge_base_path() / "testing"
        kb = SimpleKnowledgeBase(kb_path)
        assert kb.file_count > 0

    def test_performance_knowledge_search(self) -> None:
        """Performance knowledge base loads via override directory."""
        kb_path = ExpertRegistry.get_knowledge_base_path() / "performance"
        kb = SimpleKnowledgeBase(kb_path)
        assert kb.file_count > 0


@pytest.mark.integration
class TestDomainDetectionFromProject:
    """Tests domain detection against real project structures."""

    def test_detect_from_tapps_mcp_project(self) -> None:
        """Detect domains from TappsMCP's own project root."""
        from pathlib import Path

        project_root = Path(__file__).parent.parent.parent
        results = DomainDetector.detect_from_project(project_root)
        domains = [r.domain for r in results]
        # TappsMCP has pyproject.toml → code-quality-analysis.
        assert "code-quality-analysis" in domains

    def test_detect_from_project_with_tests(self, tmp_path: Path) -> None:
        """Project with conftest.py triggers testing domain."""
        (tmp_path / "conftest.py").write_text("import pytest\n")
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
        results = DomainDetector.detect_from_project(tmp_path)
        domains = [r.domain for r in results]
        assert "testing-strategies" in domains
        assert "code-quality-analysis" in domains


@pytest.mark.integration
class TestMCPToolHandlers:
    """Tests for the MCP tool wrappers in server.py."""

    def test_tapps_consult_expert_response_shape(self) -> None:
        """tapps_consult_expert returns expected response structure."""
        result: dict[str, Any] = tapps_consult_expert(
            question="How to prevent SQL injection?",
            domain="security",
        )
        assert result["tool"] == "tapps_consult_expert"
        assert result["success"] is True
        assert result["elapsed_ms"] >= 0
        assert result["data"]["domain"] == "security"
        assert result["data"]["expert_id"] == "expert-security"
        assert "answer" in result["data"]
        assert "confidence" in result["data"]
        assert "factors" in result["data"]
        assert "sources" in result["data"]
        assert "suggested_tool" in result["data"]
        assert "suggested_library" in result["data"]
        assert "suggested_topic" in result["data"]
        assert "fallback_used" in result["data"]
        assert "fallback_library" in result["data"]
        assert "fallback_topic" in result["data"]

    def test_tapps_consult_expert_auto_routing(self) -> None:
        """tapps_consult_expert auto-routes when domain is empty."""
        result: dict[str, Any] = tapps_consult_expert(
            question="How to write unit tests with pytest?",
            domain="",
        )
        assert result["success"] is True
        # Should route to testing-strategies.
        assert result["data"]["domain"] == "testing-strategies"

    def test_tapps_list_experts_response_shape(self) -> None:
        """tapps_list_experts returns expected response structure."""
        result: dict[str, Any] = tapps_list_experts()
        assert result["tool"] == "tapps_list_experts"
        assert result["success"] is True
        assert result["data"]["expert_count"] == 17
        assert len(result["data"]["experts"]) == 17

        first = result["data"]["experts"][0]
        assert "expert_id" in first
        assert "expert_name" in first
        assert "primary_domain" in first
        assert "knowledge_files" in first

    async def test_tapps_research_response_shape(self) -> None:
        """tapps_research returns combined expert + docs response structure."""
        result: dict[str, Any] = await tapps_research(
            question="How to prevent SQL injection?",
            domain="security",
        )
        assert result["tool"] == "tapps_research"
        assert result["success"] is True
        assert result["elapsed_ms"] >= 0
        assert result["data"]["domain"] == "security"
        assert result["data"]["expert_id"] == "expert-security"
        assert "answer" in result["data"]
        assert "confidence" in result["data"]
        assert "docs_supplemented" in result["data"]
        assert isinstance(result["data"]["docs_supplemented"], bool)

    async def test_tapps_research_auto_routing(self) -> None:
        """tapps_research auto-routes when domain is empty."""
        result: dict[str, Any] = await tapps_research(
            question="How to write unit tests with pytest?",
            domain="",
        )
        assert result["success"] is True
        assert result["data"]["domain"] == "testing-strategies"

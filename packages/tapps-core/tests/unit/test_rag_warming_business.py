"""Unit tests for warm_business_expert_rag_indices in experts/rag_warming.py.

Epic 44.5: Verifies RAG warming for business experts with graceful
degradation when faiss is unavailable or knowledge directories are missing.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tapps_core.experts.models import ExpertConfig
from tapps_core.experts.rag_warming import warm_business_expert_rag_indices
from tapps_core.experts.registry import ExpertRegistry


def _make_business_expert(
    domain: str,
    *,
    rag_enabled: bool = True,
    knowledge_dir: str | None = None,
) -> ExpertConfig:
    """Helper to create a business expert config."""
    return ExpertConfig(
        expert_id=f"biz-{domain}",
        expert_name=f"Business {domain.title()} Expert",
        primary_domain=domain,
        description=f"Expert for {domain}.",
        rag_enabled=rag_enabled,
        knowledge_dir=knowledge_dir,
        is_builtin=False,
    )


class TestWarmBusinessNoExperts:
    """warm_business_expert_rag_indices with no registered business experts."""

    def test_returns_empty_when_no_business_experts(self, tmp_path: Path) -> None:
        """No business experts registered -> all lists empty."""
        result = warm_business_expert_rag_indices(tmp_path)
        assert result == {"warmed": [], "skipped": [], "errors": []}


class TestWarmBusinessSkipsDisabledRag:
    """Experts with rag_enabled=False are skipped."""

    def test_skips_rag_disabled_experts(self, tmp_path: Path) -> None:
        expert = _make_business_expert("sales-ops", rag_enabled=False)
        ExpertRegistry.register_business_experts([expert])

        result = warm_business_expert_rag_indices(tmp_path)
        assert "sales-ops" in result["skipped"]
        assert result["warmed"] == []
        assert result["errors"] == []


class TestWarmBusinessMissingKnowledgeDir:
    """Missing knowledge directory is handled gracefully."""

    def test_skips_when_knowledge_dir_missing(self, tmp_path: Path) -> None:
        expert = _make_business_expert("inventory")
        ExpertRegistry.register_business_experts([expert])

        # Do NOT create the knowledge directory
        result = warm_business_expert_rag_indices(tmp_path)
        assert "inventory" in result["skipped"]
        assert result["warmed"] == []
        assert result["errors"] == []

    def test_skips_when_knowledge_dir_empty(self, tmp_path: Path) -> None:
        """Knowledge dir exists but contains no .md files."""
        expert = _make_business_expert("logistics")
        ExpertRegistry.register_business_experts([expert])

        # Create dir but no .md files
        knowledge_dir = tmp_path / ".tapps-mcp" / "knowledge" / "logistics"
        knowledge_dir.mkdir(parents=True)
        (knowledge_dir / "notes.txt").write_text("not a markdown file")

        result = warm_business_expert_rag_indices(tmp_path)
        assert "logistics" in result["skipped"]
        assert result["warmed"] == []


class TestWarmBusinessValidKnowledge:
    """Business expert with valid knowledge directory (mock VectorKnowledgeBase)."""

    @patch("tapps_core.experts.vector_rag.VectorKnowledgeBase")
    def test_warms_expert_with_valid_knowledge(
        self, mock_vkb_cls: MagicMock, tmp_path: Path
    ) -> None:
        expert = _make_business_expert("compliance")
        ExpertRegistry.register_business_experts([expert])

        # Create knowledge dir with .md files
        knowledge_dir = tmp_path / ".tapps-mcp" / "knowledge" / "compliance"
        knowledge_dir.mkdir(parents=True)
        (knowledge_dir / "gdpr-checklist.md").write_text("# GDPR Checklist\n\nItems...")

        # Mock VectorKnowledgeBase to simulate successful vector warming
        mock_vkb = MagicMock()
        mock_vkb.backend_type = "vector"
        mock_vkb_cls.return_value = mock_vkb

        result = warm_business_expert_rag_indices(tmp_path)
        assert "compliance" in result["warmed"]
        assert result["errors"] == []

        # Verify VKB was constructed and searched
        mock_vkb_cls.assert_called_once_with(knowledge_dir, domain="compliance")
        mock_vkb.search.assert_called_once_with(
            "overview patterns best practices", max_results=1
        )

    @patch("tapps_core.experts.vector_rag.VectorKnowledgeBase")
    def test_skips_when_faiss_unavailable(
        self, mock_vkb_cls: MagicMock, tmp_path: Path
    ) -> None:
        """When VKB falls back to simple backend, domain is skipped (not warmed)."""
        expert = _make_business_expert("hr-policies")
        ExpertRegistry.register_business_experts([expert])

        knowledge_dir = tmp_path / ".tapps-mcp" / "knowledge" / "hr-policies"
        knowledge_dir.mkdir(parents=True)
        (knowledge_dir / "onboarding.md").write_text("# Onboarding\n\nSteps...")

        mock_vkb = MagicMock()
        mock_vkb.backend_type = "simple"  # faiss not available
        mock_vkb_cls.return_value = mock_vkb

        result = warm_business_expert_rag_indices(tmp_path)
        assert "hr-policies" in result["skipped"]
        assert result["warmed"] == []


class TestWarmBusinessMaxDomains:
    """max_domains cap is respected."""

    @patch("tapps_core.experts.vector_rag.VectorKnowledgeBase")
    def test_max_domains_caps_warming(
        self, mock_vkb_cls: MagicMock, tmp_path: Path
    ) -> None:
        experts = [
            _make_business_expert(f"domain-{i}")
            for i in range(5)
        ]
        ExpertRegistry.register_business_experts(experts)

        # Create knowledge dirs for all
        for i in range(5):
            kdir = tmp_path / ".tapps-mcp" / "knowledge" / f"domain-{i}"
            kdir.mkdir(parents=True)
            (kdir / "guide.md").write_text(f"# Domain {i}\n\nContent")

        mock_vkb = MagicMock()
        mock_vkb.backend_type = "vector"
        mock_vkb_cls.return_value = mock_vkb

        result = warm_business_expert_rag_indices(tmp_path, max_domains=2)
        # Only first 2 should be processed
        assert len(result["warmed"]) == 2
        assert mock_vkb_cls.call_count == 2

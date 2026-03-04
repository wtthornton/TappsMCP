"""Unit tests for business expert routing in tapps_core.experts.engine.

Story 44.2 — verifies that the engine correctly routes to business experts,
uses business knowledge paths, and includes business experts in list_experts.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tapps_core.experts.engine import (
    _resolve_domain,
    _resolve_knowledge_path,
    _retrieve_knowledge,
    consult_expert,
    list_experts,
)
from tapps_core.experts.models import ExpertConfig
from tapps_core.experts.registry import ExpertRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_business_expert(
    domain: str = "fintech-compliance",
    expert_id: str = "expert-fintech",
    expert_name: str = "Fintech Compliance Expert",
    keywords: list[str] | None = None,
    knowledge_dir: str | None = None,
) -> ExpertConfig:
    """Build a business expert config for testing."""
    return ExpertConfig(
        expert_id=expert_id,
        expert_name=expert_name,
        primary_domain=domain,
        description=f"Business expert for {domain}.",
        is_builtin=False,
        keywords=keywords or ["fintech", "payment processing", "pci dss"],
        knowledge_dir=knowledge_dir,
    )


# ---------------------------------------------------------------------------
# Tests: consult_expert routes to business expert
# ---------------------------------------------------------------------------


class TestConsultExpertBusinessRouting:
    """consult_expert routes to business experts when domain matches."""

    def setup_method(self) -> None:
        self.expert = _make_business_expert()
        ExpertRegistry.register_business_experts([self.expert])

    def teardown_method(self) -> None:
        ExpertRegistry.clear_business_experts()

    @patch("tapps_core.experts.engine._try_adaptive_detection", return_value=(None, []))
    def test_routes_to_business_expert_by_domain(self, _mock: MagicMock) -> None:
        """Explicit domain routes to business expert."""
        resolved = _resolve_domain("question about fintech", domain="fintech-compliance")
        assert resolved.domain == "fintech-compliance"
        assert resolved.expert.expert_id == "expert-fintech"
        assert resolved.expert.is_builtin is False

    @patch("tapps_core.experts.engine._try_adaptive_detection", return_value=(None, []))
    def test_auto_detects_business_domain_via_keywords(self, _mock: MagicMock) -> None:
        """Question keywords route to business expert when matched."""
        resolved = _resolve_domain(
            "How should we handle PCI DSS compliance for payment processing?",
            domain=None,
        )
        assert resolved.domain == "fintech-compliance"
        assert resolved.expert.expert_id == "expert-fintech"

    @patch("tapps_core.experts.engine._try_adaptive_detection", return_value=(None, []))
    def test_consult_expert_returns_business_expert_name(self, _mock: MagicMock) -> None:
        """Full consult_expert returns the business expert's name."""
        result = consult_expert(
            "What are fintech compliance requirements?",
            domain="fintech-compliance",
        )
        assert result.expert_name == "Fintech Compliance Expert"
        assert result.domain == "fintech-compliance"
        assert result.expert_id == "expert-fintech"


# ---------------------------------------------------------------------------
# Tests: list_experts includes business experts
# ---------------------------------------------------------------------------


class TestListExpertsWithBusiness:
    """list_experts includes business experts with correct info."""

    def setup_method(self) -> None:
        self.expert = _make_business_expert()
        ExpertRegistry.register_business_experts([self.expert])

    def teardown_method(self) -> None:
        ExpertRegistry.clear_business_experts()

    def test_list_includes_business_expert(self) -> None:
        experts = list_experts()
        domains = [e.primary_domain for e in experts]
        assert "fintech-compliance" in domains

    def test_list_business_expert_has_is_builtin_false(self) -> None:
        experts = list_experts()
        fintech = next(e for e in experts if e.primary_domain == "fintech-compliance")
        assert fintech.is_builtin is False

    def test_list_business_expert_has_keywords(self) -> None:
        experts = list_experts()
        fintech = next(e for e in experts if e.primary_domain == "fintech-compliance")
        assert "fintech" in fintech.keywords
        assert "pci dss" in fintech.keywords

    def test_list_builtin_experts_still_present(self) -> None:
        """Built-in experts are still returned when business experts exist."""
        experts = list_experts()
        builtin_domains = {e.primary_domain for e in experts if e.is_builtin}
        assert "security" in builtin_domains
        assert "testing-strategies" in builtin_domains


# ---------------------------------------------------------------------------
# Tests: built-in behavior unchanged
# ---------------------------------------------------------------------------


class TestBuiltinBehaviorUnchanged:
    """Built-in expert behavior is unchanged when business experts exist."""

    def setup_method(self) -> None:
        self.expert = _make_business_expert()
        ExpertRegistry.register_business_experts([self.expert])

    def teardown_method(self) -> None:
        ExpertRegistry.clear_business_experts()

    @patch("tapps_core.experts.engine._try_adaptive_detection", return_value=(None, []))
    def test_builtin_domain_still_routes_to_builtin(self, _mock: MagicMock) -> None:
        resolved = _resolve_domain("How do I prevent SQL injection?", domain="security")
        assert resolved.expert.expert_id == "expert-security"
        assert resolved.expert.is_builtin is True

    @patch("tapps_core.experts.engine._try_adaptive_detection", return_value=(None, []))
    def test_builtin_fallback_when_no_business_match(self, _mock: MagicMock) -> None:
        """Falls back to built-in when question doesn't match business keywords."""
        resolved = _resolve_domain("How to write pytest fixtures?", domain=None)
        assert resolved.expert.is_builtin is True


# ---------------------------------------------------------------------------
# Tests: empty business expert list
# ---------------------------------------------------------------------------


class TestNoBusiness:
    """Behavior without business experts is identical to original."""

    @patch("tapps_core.experts.engine._try_adaptive_detection", return_value=(None, []))
    def test_no_business_experts_same_as_before(self, _mock: MagicMock) -> None:
        resolved = _resolve_domain("How do I prevent SQL injection?", domain=None)
        assert resolved.expert.is_builtin is True
        assert resolved.domain == "security"

    def test_list_experts_no_business(self) -> None:
        experts = list_experts()
        assert all(e.is_builtin for e in experts)


# ---------------------------------------------------------------------------
# Tests: missing knowledge directory
# ---------------------------------------------------------------------------


class TestMissingKnowledgeDir:
    """Missing knowledge directory returns graceful empty result."""

    def setup_method(self) -> None:
        self.expert = _make_business_expert()
        ExpertRegistry.register_business_experts([self.expert])

    def teardown_method(self) -> None:
        ExpertRegistry.clear_business_experts()

    @patch("tapps_core.config.settings.load_settings")
    def test_missing_dir_returns_empty_knowledge(
        self, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        """When business knowledge dir doesn't exist, return empty result."""
        mock_settings.return_value = MagicMock(project_root=tmp_path)
        # Don't create the knowledge dir -- it should be missing.
        result = _retrieve_knowledge(
            "fintech question",
            "fintech-compliance",
            self.expert,
            max_chunks=5,
            max_context_length=3000,
        )
        assert result.chunks == []
        assert result.context == ""
        assert result.sources == []


# ---------------------------------------------------------------------------
# Tests: knowledge retrieval uses business path
# ---------------------------------------------------------------------------


class TestBusinessKnowledgePath:
    """Knowledge retrieval uses business knowledge path for non-builtin."""

    def test_builtin_expert_uses_bundled_path(self) -> None:
        expert = ExpertConfig(
            expert_id="expert-security",
            expert_name="Security Expert",
            primary_domain="security",
            is_builtin=True,
        )
        path = _resolve_knowledge_path(expert)
        assert "knowledge" in str(path)
        # Should be under the bundled package path, not .tapps-mcp.
        assert ".tapps-mcp" not in str(path)

    @patch("tapps_core.config.settings.load_settings")
    def test_business_expert_uses_project_path(
        self, mock_settings: MagicMock, tmp_path: Path
    ) -> None:
        mock_settings.return_value = MagicMock(project_root=tmp_path)
        expert = _make_business_expert()
        path = _resolve_knowledge_path(expert)
        expected = tmp_path / ".tapps-mcp" / "knowledge" / "fintech-compliance"
        assert path == expected

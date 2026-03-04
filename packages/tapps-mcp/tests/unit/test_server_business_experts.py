"""Tests for MCP tool handler updates supporting business experts.

Validates that tapps_consult_expert and tapps_list_experts correctly
expose is_builtin / expert_type fields and business expert counts.
"""

from __future__ import annotations

from typing import Any

import pytest

from tapps_core.experts.models import ExpertConfig
from tapps_core.experts.registry import ExpertRegistry
from tapps_mcp.server import tapps_consult_expert, tapps_list_experts


@pytest.fixture(autouse=True)
def _clear_business_experts() -> Any:  # noqa: ANN401
    """Ensure business experts are cleared after each test."""
    yield
    ExpertRegistry.clear_business_experts()


def _register_sample_business_expert() -> ExpertConfig:
    """Register a single sample business expert and return it."""
    expert = ExpertConfig(
        expert_id="expert-finance",
        expert_name="Finance Expert",
        primary_domain="finance",
        description="Financial analysis and budgeting.",
        is_builtin=False,
        keywords=["finance", "budget", "revenue"],
    )
    ExpertRegistry.register_business_experts([expert])
    return expert


class TestConsultExpertBusinessFields:
    """Tests for is_builtin and expert_type in tapps_consult_expert."""

    def test_builtin_domain_returns_is_builtin_true(self) -> None:
        """Consulting a built-in domain marks is_builtin=True."""
        result: dict[str, Any] = tapps_consult_expert(
            question="How do I prevent SQL injection?",
            domain="security",
        )
        assert result["success"] is True
        data = result["data"]
        assert data["is_builtin"] is True
        assert data["expert_type"] == "builtin"

    def test_expert_type_field_present_in_response(self) -> None:
        """Response always includes expert_type field."""
        result: dict[str, Any] = tapps_consult_expert(
            question="What are best practices for testing?",
            domain="testing-strategies",
        )
        assert result["success"] is True
        assert "expert_type" in result["data"]
        assert result["data"]["expert_type"] in ("builtin", "business")


class TestListExpertsBusinessFields:
    """Tests for builtin_count, business_count, and is_builtin in tapps_list_experts."""

    def test_no_business_experts_returns_only_builtin_count(self) -> None:
        """When no business experts registered, business_count is 0."""
        result: dict[str, Any] = tapps_list_experts()
        assert result["success"] is True
        data = result["data"]
        assert data["builtin_count"] == len(ExpertRegistry.BUILTIN_EXPERTS)
        assert data["business_count"] == 0
        assert data["expert_count"] == data["builtin_count"]

    def test_with_business_experts_includes_both_counts(self) -> None:
        """After registering business experts, both counts reflect correctly."""
        _register_sample_business_expert()

        result: dict[str, Any] = tapps_list_experts()
        assert result["success"] is True
        data = result["data"]
        assert data["builtin_count"] == len(ExpertRegistry.BUILTIN_EXPERTS)
        assert data["business_count"] == 1
        assert data["expert_count"] == data["builtin_count"] + 1

    def test_expert_entries_include_is_builtin_field(self) -> None:
        """Each expert entry in the list includes is_builtin."""
        _register_sample_business_expert()

        result: dict[str, Any] = tapps_list_experts()
        data = result["data"]
        experts = data["experts"]

        # All entries must have is_builtin
        for expert in experts:
            assert "is_builtin" in expert

        # Built-in experts should be True
        builtin_entries = [e for e in experts if e["is_builtin"]]
        assert len(builtin_entries) == len(ExpertRegistry.BUILTIN_EXPERTS)

        # Business expert should be False
        business_entries = [e for e in experts if not e["is_builtin"]]
        assert len(business_entries) == 1
        assert business_entries[0]["expert_id"] == "expert-finance"

    def test_business_expert_has_correct_metadata(self) -> None:
        """Business expert entry preserves name, domain, and description."""
        _register_sample_business_expert()

        result: dict[str, Any] = tapps_list_experts()
        experts = result["data"]["experts"]
        biz = next(e for e in experts if e["expert_id"] == "expert-finance")
        assert biz["expert_name"] == "Finance Expert"
        assert biz["primary_domain"] == "finance"
        assert biz["description"] == "Financial analysis and budgeting."
        assert biz["is_builtin"] is False
        assert biz["keywords"] == ["finance", "budget", "revenue"]

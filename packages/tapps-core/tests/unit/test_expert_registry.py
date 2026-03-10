"""Unit tests for tapps_core.experts.registry."""

from __future__ import annotations

import pytest

from tapps_core.experts.models import ExpertConfig
from tapps_core.experts.registry import ExpertRegistry


def _make_business_expert(
    expert_id: str = "expert-biz-strategy",
    domain: str = "business-strategy",
    name: str = "Business Strategy Expert",
) -> ExpertConfig:
    """Create a business ExpertConfig for testing."""
    return ExpertConfig(
        expert_id=expert_id,
        expert_name=name,
        primary_domain=domain,
        description="Business strategy guidance.",
        is_builtin=False,
        keywords=["strategy", "roadmap"],
    )


class TestExpertRegistry:
    """Tests for ExpertRegistry."""

    def test_has_17_experts(self) -> None:
        assert len(ExpertRegistry.BUILTIN_EXPERTS) == 17

    def test_has_17_domains(self) -> None:
        assert len(ExpertRegistry.TECHNICAL_DOMAINS) == 17

    def test_all_experts_map_to_technical_domains(self) -> None:
        for expert in ExpertRegistry.BUILTIN_EXPERTS:
            assert ExpertRegistry.is_technical_domain(expert.primary_domain), (
                f"{expert.expert_id} domain '{expert.primary_domain}' not in TECHNICAL_DOMAINS"
            )

    def test_expert_ids_are_unique(self) -> None:
        ids = ExpertRegistry.get_expert_ids()
        assert len(ids) == len(set(ids))

    def test_get_all_experts_returns_copy(self) -> None:
        a = ExpertRegistry.get_all_experts()
        b = ExpertRegistry.get_all_experts()
        assert a is not b
        assert a == b

    def test_get_expert_by_id_found(self) -> None:
        expert = ExpertRegistry.get_expert_by_id("expert-security")
        assert expert is not None
        assert expert.primary_domain == "security"

    def test_get_expert_by_id_not_found(self) -> None:
        assert ExpertRegistry.get_expert_by_id("expert-nonexistent") is None

    def test_get_expert_for_domain_found(self) -> None:
        expert = ExpertRegistry.get_expert_for_domain("testing-strategies")
        assert expert is not None
        assert expert.expert_id == "expert-testing"

    def test_get_expert_for_domain_not_found(self) -> None:
        assert ExpertRegistry.get_expert_for_domain("astrology") is None

    def test_is_technical_domain(self) -> None:
        assert ExpertRegistry.is_technical_domain("security") is True
        assert ExpertRegistry.is_technical_domain("banana") is False

    def test_knowledge_base_path(self) -> None:
        path = ExpertRegistry.get_knowledge_base_path()
        assert path.name == "knowledge"
        assert path.exists()

    def test_each_expert_has_description(self) -> None:
        for expert in ExpertRegistry.BUILTIN_EXPERTS:
            assert expert.description, f"{expert.expert_id} is missing a description"

    def test_security_expert_details(self) -> None:
        expert = ExpertRegistry.get_expert_by_id("expert-security")
        assert expert is not None
        assert expert.expert_name == "Security Expert"
        assert expert.rag_enabled is True

    def test_all_experts_have_persona(self) -> None:
        for expert in ExpertRegistry.BUILTIN_EXPERTS:
            assert expert.persona, f"{expert.expert_id} is missing a persona"
            assert len(expert.persona) >= 20, (
                f"{expert.expert_id} persona is too short: {expert.persona!r}"
            )

    def test_performance_expert_has_knowledge_dir_override(self) -> None:
        expert = ExpertRegistry.get_expert_by_id("expert-performance")
        assert expert is not None
        assert expert.knowledge_dir == "performance"


class TestBusinessExperts:
    """Tests for business expert registration and merged access."""

    def test_register_business_experts_valid(self) -> None:
        experts = [
            _make_business_expert("expert-biz-strategy", "business-strategy"),
            _make_business_expert("expert-biz-finance", "business-finance", "Finance Expert"),
        ]
        ExpertRegistry.register_business_experts(experts)
        assert len(ExpertRegistry.get_business_experts()) == 2

    def test_id_collision_with_builtin_raises(self) -> None:
        experts = [_make_business_expert("expert-security", "business-strategy")]
        with pytest.raises(ValueError, match="collides with a built-in expert"):
            ExpertRegistry.register_business_experts(experts)

    def test_duplicate_ids_within_business_raises(self) -> None:
        experts = [
            _make_business_expert("expert-biz-dup", "business-strategy"),
            _make_business_expert("expert-biz-dup", "business-finance"),
        ]
        with pytest.raises(ValueError, match="Duplicate business expert ID"):
            ExpertRegistry.register_business_experts(experts)

    def test_get_all_experts_merged_includes_both(self) -> None:
        biz = [_make_business_expert()]
        ExpertRegistry.register_business_experts(biz)
        merged = ExpertRegistry.get_all_experts_merged()
        assert len(merged) == len(ExpertRegistry.BUILTIN_EXPERTS) + 1
        assert merged[-1].expert_id == "expert-biz-strategy"

    def test_get_expert_for_domain_merged_returns_builtin(self) -> None:
        biz = [_make_business_expert()]
        ExpertRegistry.register_business_experts(biz)
        expert = ExpertRegistry.get_expert_for_domain_merged("security")
        assert expert is not None
        assert expert.expert_id == "expert-security"

    def test_get_expert_for_domain_merged_returns_business(self) -> None:
        biz = [_make_business_expert()]
        ExpertRegistry.register_business_experts(biz)
        expert = ExpertRegistry.get_expert_for_domain_merged("business-strategy")
        assert expert is not None
        assert expert.expert_id == "expert-biz-strategy"

    def test_get_expert_for_domain_merged_returns_none_unknown(self) -> None:
        biz = [_make_business_expert()]
        ExpertRegistry.register_business_experts(biz)
        assert ExpertRegistry.get_expert_for_domain_merged("astrology") is None

    def test_get_business_domains(self) -> None:
        biz = [
            _make_business_expert("expert-biz-a", "business-strategy"),
            _make_business_expert("expert-biz-b", "business-finance", "Finance Expert"),
        ]
        ExpertRegistry.register_business_experts(biz)
        domains = ExpertRegistry.get_business_domains()
        assert domains == {"business-strategy", "business-finance"}

    def test_is_business_domain_true_for_registered(self) -> None:
        biz = [_make_business_expert()]
        ExpertRegistry.register_business_experts(biz)
        assert ExpertRegistry.is_business_domain("business-strategy") is True

    def test_is_business_domain_false_for_builtin(self) -> None:
        biz = [_make_business_expert()]
        ExpertRegistry.register_business_experts(biz)
        assert ExpertRegistry.is_business_domain("security") is False

    def test_clear_business_experts_resets_state(self) -> None:
        biz = [_make_business_expert()]
        ExpertRegistry.register_business_experts(biz)
        assert len(ExpertRegistry.get_business_experts()) == 1
        ExpertRegistry.clear_business_experts()
        assert len(ExpertRegistry.get_business_experts()) == 0
        assert ExpertRegistry.get_business_domains() == set()

    def test_empty_business_does_not_affect_builtin(self) -> None:
        # No business experts registered — all builtin queries work normally
        assert len(ExpertRegistry.get_business_experts()) == 0
        assert ExpertRegistry.get_business_domains() == set()
        assert ExpertRegistry.is_business_domain("security") is False
        merged = ExpertRegistry.get_all_experts_merged()
        assert len(merged) == len(ExpertRegistry.BUILTIN_EXPERTS)
        assert ExpertRegistry.get_expert_for_domain_merged("security") is not None

    def test_get_business_experts_returns_copy(self) -> None:
        biz = [_make_business_expert()]
        ExpertRegistry.register_business_experts(biz)
        a = ExpertRegistry.get_business_experts()
        b = ExpertRegistry.get_business_experts()
        assert a is not b
        assert a == b

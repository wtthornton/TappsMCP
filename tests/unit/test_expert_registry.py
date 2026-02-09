"""Unit tests for tapps_mcp.experts.registry."""

from __future__ import annotations

from tapps_mcp.experts.registry import ExpertRegistry


class TestExpertRegistry:
    """Tests for ExpertRegistry."""

    def test_has_16_experts(self) -> None:
        assert len(ExpertRegistry.BUILTIN_EXPERTS) == 16

    def test_has_16_domains(self) -> None:
        assert len(ExpertRegistry.TECHNICAL_DOMAINS) == 16

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

    def test_performance_expert_has_knowledge_dir_override(self) -> None:
        expert = ExpertRegistry.get_expert_by_id("expert-performance")
        assert expert is not None
        assert expert.knowledge_dir == "performance"

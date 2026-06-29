"""Tests for DocsMCP domain playbook enrichment."""

from __future__ import annotations

from docs_mcp.generators.domain_enrichment import build_domain_guidance, enrich_expert_guidance


class TestDomainEnrichment:
    def test_build_guidance_for_security_epic(self) -> None:
        guidance = build_domain_guidance("OAuth security hardening for API endpoints")
        assert guidance
        domains = {item["domain"] for item in guidance}
        assert "Application security" in domains

    def test_enrich_populates_expert_guidance(self) -> None:
        enrichment: dict[str, object] = {}
        enrich_expert_guidance("Improve pytest coverage for checkout flow", enrichment)
        assert "expert_guidance" in enrichment
        items = enrichment["expert_guidance"]
        assert isinstance(items, list)
        assert items
        assert items[0]["source"] == "domain_playbook"

    def test_enrich_skips_when_existing(self) -> None:
        enrichment = {"expert_guidance": [{"domain": "X", "advice": "keep", "confidence": "100%"}]}
        enrich_expert_guidance("security auth", enrichment)
        assert enrichment["expert_guidance"] == [{"domain": "X", "advice": "keep", "confidence": "100%"}]

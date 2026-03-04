"""Tests for business expert knowledge starter templates (Story 45.3)."""

from __future__ import annotations

from tapps_core.experts.business_templates import (
    generate_readme_template,
    generate_starter_knowledge,
)


class TestGenerateReadmeTemplate:
    """Tests for generate_readme_template."""

    def test_readme_includes_expert_name_and_domain(self) -> None:
        """README template includes the expert name and primary domain."""
        result = generate_readme_template(
            expert_name="Acme Payments",
            primary_domain="payment-processing",
        )
        assert "Acme Payments" in result
        assert "payment-processing" in result
        assert "# Acme Payments Knowledge Base" in result
        assert "Domain: **payment-processing**" in result

    def test_readme_is_valid_markdown_no_unclosed_code_blocks(self) -> None:
        """README template has balanced code block fences."""
        result = generate_readme_template(
            expert_name="Test Expert",
            primary_domain="testing",
        )
        fence_count = result.count("```")
        assert fence_count % 2 == 0, f"Unclosed code blocks: {fence_count} fences"

    def test_readme_handles_special_characters(self) -> None:
        """README template handles names with quotes, ampersands, etc."""
        result = generate_readme_template(
            expert_name='R&D "Alpha" Team',
            primary_domain="r&d-alpha",
            description="Handles <special> & 'chars'",
        )
        assert 'R&D "Alpha" Team' in result
        assert "r&d-alpha" in result


class TestGenerateStarterKnowledge:
    """Tests for generate_starter_knowledge."""

    def test_starter_includes_description(self) -> None:
        """Starter knowledge includes the provided description."""
        result = generate_starter_knowledge(
            expert_name="Billing Expert",
            primary_domain="billing",
            description="Handles invoice and payment workflows.",
        )
        assert "Handles invoice and payment workflows." in result
        assert "Billing Expert" in result

    def test_starter_uses_fallback_when_no_description(self) -> None:
        """Starter knowledge uses fallback description when none provided."""
        result = generate_starter_knowledge(
            expert_name="Billing Expert",
            primary_domain="billing",
        )
        assert "Domain knowledge for billing." in result

    def test_starter_has_getting_started_section(self) -> None:
        """Starter knowledge has a Getting Started section."""
        result = generate_starter_knowledge(
            expert_name="Ops Expert",
            primary_domain="operations",
        )
        assert "## Getting Started" in result
        assert "Start with what you know" in result

    def test_starter_handles_special_characters(self) -> None:
        """Starter knowledge handles names with special characters."""
        result = generate_starter_knowledge(
            expert_name="O'Brien & Associates",
            primary_domain="legal-compliance",
            description="Handles <legal> & 'compliance' issues.",
        )
        assert "O'Brien & Associates" in result
        assert "legal-compliance" in result
        assert "Handles <legal> & 'compliance' issues." in result

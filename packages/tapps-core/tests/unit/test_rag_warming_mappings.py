"""Unit tests for expanded tech stack domain mappings in rag_warming.py.

Epic 54.1: Verifies new Node.js/TypeScript and infrastructure entries
resolve to valid domains, case-insensitive matching works, and existing
Python mappings are unaffected.
"""

from __future__ import annotations

import pytest

from tapps_core.experts.rag_warming import (
    TECH_STACK_TO_EXPERT_DOMAINS,
    tech_stack_to_expert_domains,
)
from tapps_core.experts.registry import ExpertRegistry


# -- Valid domain check --


VALID_DOMAINS = {
    exp.primary_domain for exp in ExpertRegistry.get_all_experts()
}


class TestAllMappingsResolveToValidDomains:
    """Every value in TECH_STACK_TO_EXPERT_DOMAINS must be a registered domain."""

    def test_all_mapped_domains_are_valid(self) -> None:
        invalid: list[tuple[str, str]] = []
        for signal, domains in TECH_STACK_TO_EXPERT_DOMAINS.items():
            for domain in domains:
                if domain not in VALID_DOMAINS:
                    invalid.append((signal, domain))
        assert not invalid, f"Invalid domain mappings: {invalid}"


# -- New Node.js / TypeScript entries --


class TestNodeJsTypescriptMappings:
    """Verify new Node.js/TypeScript ecosystem entries exist and map correctly."""

    @pytest.mark.parametrize(
        "signal,expected_domain",
        [
            ("nodejs", "api-design-integration"),
            ("node", "software-architecture"),
            ("typescript", "code-quality-analysis"),
            ("javascript", "software-architecture"),
            ("nestjs", "api-design-integration"),
            ("nextjs", "user-experience"),
            ("deno", "api-design-integration"),
            ("bun", "api-design-integration"),
            ("prisma", "database-data-management"),
            ("drizzle", "database-data-management"),
            ("typeorm", "database-data-management"),
            ("sequelize", "database-data-management"),
            ("zod", "code-quality-analysis"),
            ("io-ts", "code-quality-analysis"),
            ("vitest", "testing-strategies"),
            ("playwright", "testing-strategies"),
            ("cypress", "testing-strategies"),
            ("mocha", "testing-strategies"),
        ],
    )
    def test_nodejs_signal_maps_to_domain(
        self, signal: str, expected_domain: str
    ) -> None:
        domains = TECH_STACK_TO_EXPERT_DOMAINS[signal]
        assert expected_domain in domains


# -- New infrastructure / IoT entries --


class TestInfrastructureMappings:
    """Verify new infrastructure entries exist and map correctly."""

    @pytest.mark.parametrize(
        "signal,expected_domain",
        [
            ("mqtt", "observability-monitoring"),
            ("influxdb", "database-data-management"),
            ("tailscale", "cloud-infrastructure"),
            ("wireguard", "security"),
            ("pulumi", "cloud-infrastructure"),
            ("ansible", "cloud-infrastructure"),
        ],
    )
    def test_infra_signal_maps_to_domain(
        self, signal: str, expected_domain: str
    ) -> None:
        domains = TECH_STACK_TO_EXPERT_DOMAINS[signal]
        assert expected_domain in domains


# -- Case-insensitive matching --


class TestCaseInsensitiveMatching:
    """tech_stack_to_expert_domains lowercases inputs before lookup."""

    def _make_tech_stack(
        self,
        *,
        languages: list[str] | None = None,
        frameworks: list[str] | None = None,
        libraries: list[str] | None = None,
        domains: list[str] | None = None,
    ) -> object:
        """Create a minimal TechStack-like object."""
        from unittest.mock import MagicMock

        ts = MagicMock()
        ts.languages = languages
        ts.frameworks = frameworks or []
        ts.libraries = libraries or []
        ts.domains = domains or []
        return ts

    def test_uppercase_framework_matches(self) -> None:
        ts = self._make_tech_stack(frameworks=["NestJS"])
        result = tech_stack_to_expert_domains(ts)  # type: ignore[arg-type]
        assert "api-design-integration" in result

    def test_mixed_case_library_matches(self) -> None:
        ts = self._make_tech_stack(libraries=["TypeScript"])
        result = tech_stack_to_expert_domains(ts)  # type: ignore[arg-type]
        assert "code-quality-analysis" in result

    def test_uppercase_domain_matches(self) -> None:
        ts = self._make_tech_stack(domains=["Web"])
        result = tech_stack_to_expert_domains(ts)  # type: ignore[arg-type]
        assert "user-experience" in result


# -- Existing Python mappings unaffected --


class TestExistingPythonMappings:
    """Ensure pre-existing Python-centric mappings are preserved."""

    @pytest.mark.parametrize(
        "signal,expected_domain",
        [
            ("fastapi", "api-design-integration"),
            ("django", "software-architecture"),
            ("pytest", "testing-strategies"),
            ("sqlalchemy", "database-data-management"),
            ("docker", "cloud-infrastructure"),
            ("prometheus", "observability-monitoring"),
            ("tensorflow", "ai-frameworks"),
        ],
    )
    def test_python_mapping_preserved(
        self, signal: str, expected_domain: str
    ) -> None:
        domains = TECH_STACK_TO_EXPERT_DOMAINS[signal]
        assert expected_domain in domains


# -- All keys are lowercase --


class TestKeysAreLowercase:
    """All dictionary keys must be lowercase for case-insensitive matching."""

    def test_all_keys_lowercase(self) -> None:
        for key in TECH_STACK_TO_EXPERT_DOMAINS:
            assert key == key.lower(), f"Key '{key}' is not lowercase"

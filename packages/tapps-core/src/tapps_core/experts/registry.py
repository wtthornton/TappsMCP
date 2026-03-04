"""Built-in expert registry — 17-domain expert catalogue + business experts.

Each expert is an immutable ``ExpertConfig`` entry with a primary domain,
knowledge-directory override (where it differs from the domain slug), and
a short description.  The registry is the single source of truth for which
experts ship with TappsMCP.

Business experts can be registered at runtime via
:meth:`ExpertRegistry.register_business_experts`.  Built-in experts always
take precedence in merged lookups.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from tapps_core.experts.models import ExpertConfig


class ExpertRegistry:
    """Registry of built-in domain experts and optional business experts.

    All 17 technical-domain experts are defined here.  Business experts
    can be registered at runtime via :meth:`register_business_experts`.
    Built-in experts always take priority in merged lookups.
    """

    # Business expert storage (populated at runtime)
    _business_experts: ClassVar[list[ExpertConfig]] = []
    _business_domains: ClassVar[set[str]] = set()

    TECHNICAL_DOMAINS: ClassVar[set[str]] = {
        "security",
        "performance-optimization",
        "testing-strategies",
        "code-quality-analysis",
        "software-architecture",
        "development-workflow",
        "data-privacy-compliance",
        "accessibility",
        "user-experience",
        "documentation-knowledge-management",
        "ai-frameworks",
        "agent-learning",
        "observability-monitoring",
        "api-design-integration",
        "cloud-infrastructure",
        "database-data-management",
        "github",
    }

    BUILTIN_EXPERTS: ClassVar[list[ExpertConfig]] = [
        ExpertConfig(
            expert_id="expert-security",
            expert_name="Security Expert",
            primary_domain="security",
            description="Application security, vulnerability analysis, secure coding practices.",
        ),
        ExpertConfig(
            expert_id="expert-performance",
            expert_name="Performance Expert",
            primary_domain="performance-optimization",
            description="Performance profiling, optimisation strategies, bottleneck analysis.",
            knowledge_dir="performance",
        ),
        ExpertConfig(
            expert_id="expert-testing",
            expert_name="Testing Expert",
            primary_domain="testing-strategies",
            description="Test strategy, coverage analysis, testing best practices.",
            knowledge_dir="testing",
        ),
        ExpertConfig(
            expert_id="expert-code-quality",
            expert_name="Code Quality & Analysis Expert",
            primary_domain="code-quality-analysis",
            description="Code quality metrics, static analysis, refactoring guidance.",
        ),
        ExpertConfig(
            expert_id="expert-software-architecture",
            expert_name="Software Architecture Expert",
            primary_domain="software-architecture",
            description="System design, architectural patterns, scalability.",
        ),
        ExpertConfig(
            expert_id="expert-devops",
            expert_name="Development Workflow Expert",
            primary_domain="development-workflow",
            description="CI/CD, build tooling, developer productivity.",
        ),
        ExpertConfig(
            expert_id="expert-data-privacy",
            expert_name="Data Privacy & Compliance Expert",
            primary_domain="data-privacy-compliance",
            description="GDPR, HIPAA, data protection, compliance requirements.",
        ),
        ExpertConfig(
            expert_id="expert-accessibility",
            expert_name="Accessibility Expert",
            primary_domain="accessibility",
            description="WCAG compliance, assistive technology, inclusive design.",
        ),
        ExpertConfig(
            expert_id="expert-user-experience",
            expert_name="User Experience Expert",
            primary_domain="user-experience",
            description="UX patterns, usability, frontend best practices.",
        ),
        ExpertConfig(
            expert_id="expert-documentation",
            expert_name="Documentation & Knowledge Management Expert",
            primary_domain="documentation-knowledge-management",
            description="Technical writing, API docs, knowledge-base management.",
        ),
        ExpertConfig(
            expert_id="expert-ai-frameworks",
            expert_name="AI Agent Framework Expert",
            primary_domain="ai-frameworks",
            description="AI/ML frameworks, agent architectures, prompt engineering.",
        ),
        ExpertConfig(
            expert_id="expert-agent-learning",
            expert_name="Agent Learning Best Practices Expert",
            primary_domain="agent-learning",
            description="Agent learning patterns, memory systems, adaptive behaviour.",
        ),
        ExpertConfig(
            expert_id="expert-observability",
            expert_name="Observability & Monitoring Expert",
            primary_domain="observability-monitoring",
            description="Logging, metrics, tracing, alerting, dashboards.",
        ),
        ExpertConfig(
            expert_id="expert-api-design",
            expert_name="API Design & Integration Expert",
            primary_domain="api-design-integration",
            description="REST/GraphQL design, API versioning, integration patterns.",
        ),
        ExpertConfig(
            expert_id="expert-cloud-infrastructure",
            expert_name="Cloud & Infrastructure Expert",
            primary_domain="cloud-infrastructure",
            description="AWS/Azure/GCP, Kubernetes, Docker, IaC.",
        ),
        ExpertConfig(
            expert_id="expert-database",
            expert_name="Database & Data Management Expert",
            primary_domain="database-data-management",
            description="SQL/NoSQL, schema design, query optimisation, migrations.",
        ),
        ExpertConfig(
            expert_id="expert-github",
            expert_name="GitHub Platform Expert",
            primary_domain="github",
            description=(
                "GitHub Actions, Issues, PRs, rulesets, Copilot agent integration, "
                "and repository governance."
            ),
        ),
    ]

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    @classmethod
    def get_all_experts(cls) -> list[ExpertConfig]:
        """Return a copy of all built-in experts."""
        return list(cls.BUILTIN_EXPERTS)

    @classmethod
    def get_expert_ids(cls) -> list[str]:
        """Return a list of all built-in expert IDs."""
        return [e.expert_id for e in cls.BUILTIN_EXPERTS]

    @classmethod
    def get_expert_by_id(cls, expert_id: str) -> ExpertConfig | None:
        """Look up an expert by ID."""
        for expert in cls.BUILTIN_EXPERTS:
            if expert.expert_id == expert_id:
                return expert
        return None

    @classmethod
    def get_expert_for_domain(cls, domain: str) -> ExpertConfig | None:
        """Look up the expert whose *primary_domain* matches *domain*."""
        for expert in cls.BUILTIN_EXPERTS:
            if expert.primary_domain == domain:
                return expert
        return None

    @classmethod
    def is_technical_domain(cls, domain: str) -> bool:
        """Return ``True`` if *domain* is a recognised technical domain."""
        return domain in cls.TECHNICAL_DOMAINS

    @classmethod
    def get_knowledge_base_path(cls) -> Path:
        """Return the path to the bundled knowledge-base directory."""
        return Path(__file__).parent / "knowledge"

    # ------------------------------------------------------------------
    # Business expert management
    # ------------------------------------------------------------------

    @classmethod
    def register_business_experts(cls, experts: list[ExpertConfig]) -> None:
        """Register business experts, validating no ID collisions.

        Raises ``ValueError`` if any expert ID collides with a built-in
        expert or if there are duplicate IDs within the provided list.
        """
        builtin_ids = {e.expert_id for e in cls.BUILTIN_EXPERTS}
        seen_ids: set[str] = set()

        for expert in experts:
            if expert.expert_id in builtin_ids:
                msg = (
                    f"Business expert ID '{expert.expert_id}' collides "
                    f"with a built-in expert"
                )
                raise ValueError(msg)
            if expert.expert_id in seen_ids:
                msg = (
                    f"Duplicate business expert ID '{expert.expert_id}'"
                )
                raise ValueError(msg)
            seen_ids.add(expert.expert_id)

        cls._business_experts = list(experts)
        cls._business_domains = {e.primary_domain for e in experts}

    @classmethod
    def clear_business_experts(cls) -> None:
        """Reset business expert state (for testing and re-loading)."""
        cls._business_experts = []
        cls._business_domains = set()

    @classmethod
    def get_all_experts_merged(cls) -> list[ExpertConfig]:
        """Return all experts: built-in first, then business."""
        return list(cls.BUILTIN_EXPERTS) + list(cls._business_experts)

    @classmethod
    def get_expert_for_domain_merged(cls, domain: str) -> ExpertConfig | None:
        """Look up expert by domain, checking built-in first then business."""
        builtin = cls.get_expert_for_domain(domain)
        if builtin is not None:
            return builtin
        for expert in cls._business_experts:
            if expert.primary_domain == domain:
                return expert
        return None

    @classmethod
    def get_business_experts(cls) -> list[ExpertConfig]:
        """Return a copy of registered business experts."""
        return list(cls._business_experts)

    @classmethod
    def get_business_domains(cls) -> set[str]:
        """Return the set of registered business domain slugs."""
        return set(cls._business_domains)

    @classmethod
    def is_business_domain(cls, domain: str) -> bool:
        """Return ``True`` if *domain* is a registered business domain."""
        return domain in cls._business_domains

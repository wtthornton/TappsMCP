"""Expert domain mapping — maps tech stack to relevant expert domain names.

The RAG warming infrastructure (VectorKnowledgeBase, ExpertRegistry) has been
removed. Only the tech-stack-to-domain mapping dict and helper function remain,
as they are used by session start to populate domain hints.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    class TechStack:
        """Structural type for tech-stack objects passed into warming helpers.

        Avoids a reverse-dependency on tapps_mcp, which owns the concrete
        TechStack pydantic model.
        """

        languages: list[str]
        libraries: list[str]
        frameworks: list[str]
        domains: list[str]

# Tech stack signals (lowercase) → expert domain names.
# When a tech_stack contains any of these signals, we warm that expert domain.
TECH_STACK_TO_EXPERT_DOMAINS: dict[str, list[str]] = {
    # Frameworks/libraries
    "fastapi": ["api-design-integration"],
    "flask": ["api-design-integration"],
    "django": ["api-design-integration", "software-architecture"],
    "express": ["api-design-integration"],
    "aiohttp": ["api-design-integration"],
    "react": ["user-experience"],
    "vue": ["user-experience"],
    "angular": ["user-experience"],
    "pytest": ["testing-strategies"],
    "jest": ["testing-strategies"],
    "unittest": ["testing-strategies"],
    "ruff": ["code-quality-analysis"],
    "mypy": ["code-quality-analysis"],
    "pylint": ["code-quality-analysis"],
    "docker": ["cloud-infrastructure", "development-workflow"],
    "kubernetes": ["cloud-infrastructure"],
    "terraform": ["cloud-infrastructure"],
    "aws": ["cloud-infrastructure"],
    "azure": ["cloud-infrastructure"],
    "gcp": ["cloud-infrastructure"],
    "sqlalchemy": ["database-data-management"],
    "postgres": ["database-data-management"],
    "redis": ["database-data-management"],
    "mongodb": ["database-data-management"],
    "prometheus": ["observability-monitoring"],
    "grafana": ["observability-monitoring"],
    "opentelemetry": ["observability-monitoring"],
    "tensorflow": ["ai-frameworks"],
    "pytorch": ["ai-frameworks"],
    "langchain": ["ai-frameworks"],
    # Node.js / TypeScript ecosystem
    "nodejs": ["api-design-integration", "software-architecture"],
    "node": ["api-design-integration", "software-architecture"],
    "typescript": ["code-quality-analysis", "software-architecture"],
    "javascript": ["software-architecture"],
    "nestjs": ["api-design-integration", "software-architecture"],
    "nextjs": ["user-experience", "software-architecture"],
    "deno": ["api-design-integration", "software-architecture"],
    "bun": ["api-design-integration", "software-architecture"],
    "prisma": ["database-data-management"],
    "drizzle": ["database-data-management"],
    "typeorm": ["database-data-management"],
    "sequelize": ["database-data-management"],
    "zod": ["code-quality-analysis", "api-design-integration"],
    "io-ts": ["code-quality-analysis"],
    "vitest": ["testing-strategies"],
    "playwright": ["testing-strategies"],
    "cypress": ["testing-strategies"],
    "mocha": ["testing-strategies"],
    # Infrastructure / IoT
    "mqtt": ["observability-monitoring", "software-architecture"],
    "influxdb": ["database-data-management", "observability-monitoring"],
    "tailscale": ["cloud-infrastructure", "security"],
    "wireguard": ["cloud-infrastructure", "security"],
    "pulumi": ["cloud-infrastructure"],
    "ansible": ["cloud-infrastructure"],
    # Domains from tech_stack.domains
    "web": ["user-experience", "api-design-integration"],
    "api": ["api-design-integration"],
    "testing": ["testing-strategies"],
    "database": ["database-data-management"],
    "cloud": ["cloud-infrastructure"],
    "devops": ["cloud-infrastructure", "development-workflow"],
    "ml": ["ai-frameworks"],
    "data": ["database-data-management"],
}


def tech_stack_to_expert_domains(tech_stack: TechStack) -> list[str]:
    """Map tech stack to relevant expert domain names.

    Args:
        tech_stack: Project tech stack from detect_project_profile.

    Returns:
        Deduplicated list of expert domain names to warm, ordered by
        relevance (domains first, then frameworks, then libraries).
    """
    seen: set[str] = set()
    result: list[str] = []

    all_signals: list[str] = []
    all_signals.extend(d.lower() for d in (tech_stack.domains or []))
    all_signals.extend(fw.lower() for fw in (tech_stack.frameworks or []))
    all_signals.extend(lib.lower() for lib in (tech_stack.libraries or []))

    for signal in all_signals:
        for expert_domain in TECH_STACK_TO_EXPERT_DOMAINS.get(signal, []):
            if expert_domain not in seen:
                seen.add(expert_domain)
                result.append(expert_domain)

    # Always include software-architecture and code-quality-analysis if Python
    defaults = ["software-architecture"]
    if "python" in [lang.lower() for lang in (tech_stack.languages or [])]:
        defaults.append("code-quality-analysis")
    for d in defaults:
        if d not in seen:
            seen.add(d)
            result.append(d)

    return result

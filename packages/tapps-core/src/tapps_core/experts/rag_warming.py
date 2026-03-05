"""Expert RAG index warming — pre-build vector indices from tech stack.

Maps tech stack (languages, frameworks, libraries, domains) to relevant
expert domains and pre-builds VectorKnowledgeBase indices so the first
tapps_consult_expert call for those domains is fast.

Also supports warming business expert RAG indices from project-local
knowledge directories.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from tapps_core.experts.domain_utils import sanitize_domain_for_path

if TYPE_CHECKING:
    from pathlib import Path

    from tapps_core.project.models import TechStack

logger = structlog.get_logger(__name__)

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


def warm_expert_rag_indices(
    tech_stack: TechStack,
    *,
    max_domains: int = 10,
    index_base_dir: Path | None = None,
) -> dict[str, object]:
    """Pre-build VectorKnowledgeBase indices for expert domains relevant to tech stack.

    When FAISS and sentence-transformers are installed, builds FAISS indices
    for each domain. When absent, this is a no-op (vector RAG falls back to
    simple search on first use).

    Args:
        tech_stack: Project tech stack.
        max_domains: Maximum number of domains to warm.
        index_base_dir: Base directory for per-domain indices. When provided,
            indices are stored at index_base_dir/{domain_slug}. When None,
            uses the default package-level location.

    Returns:
        Summary dict with warmed, attempted, domains, skipped reason.
    """
    from tapps_core.experts.registry import ExpertRegistry
    from tapps_core.experts.vector_rag import VectorKnowledgeBase

    domains = tech_stack_to_expert_domains(tech_stack)[:max_domains]

    if not domains:
        return {
            "warmed": 0,
            "attempted": 0,
            "domains": [],
            "skipped": "no_relevant_domains",
        }

    kb_path = ExpertRegistry.get_knowledge_base_path()
    warmed = 0
    failed_domains: list[str] = []

    for domain in domains:
        try:
            expert = ExpertRegistry.get_expert_for_domain(domain)
            if expert is None:
                continue

            dir_name = expert.knowledge_dir or sanitize_domain_for_path(domain)
            knowledge_dir = kb_path / dir_name

            if not knowledge_dir.exists():
                logger.debug("rag_warm_skip_domain", domain=domain, reason="no_knowledge_dir")
                continue

            idx_dir: Path | None = None
            if index_base_dir is not None:
                domain_slug = sanitize_domain_for_path(domain)
                idx_dir = index_base_dir / domain_slug

            vkb = VectorKnowledgeBase(
                knowledge_dir,
                domain=domain,
                index_dir=idx_dir,
            )
            # Trigger index build/load
            vkb.search("overview patterns best practices", max_results=1)

            if vkb.backend_type == "vector":
                warmed += 1
                logger.debug("rag_warm_domain", domain=domain)
        except (OSError, RuntimeError, ValueError, ImportError) as e:
            failed_domains.append(domain)
            logger.debug("rag_warm_failed", domain=domain, error=str(e))

    return {
        "warmed": warmed,
        "attempted": len(domains),
        "domains": domains,
        "failed_domains": failed_domains,
        "skipped": None if warmed > 0 else "faiss_unavailable_or_error",
    }


def warm_business_expert_rag_indices(
    project_root: Path,
    *,
    max_domains: int = 10,
) -> dict[str, Any]:
    """Pre-build VectorKnowledgeBase indices for registered business experts.

    Iterates over business experts from :class:`ExpertRegistry` and builds
    FAISS indices for those with ``rag_enabled=True`` and existing knowledge
    directories containing ``.md`` files.

    When FAISS is not installed, skips silently (graceful degradation).

    Args:
        project_root: Project root directory (knowledge lives under
            ``{project_root}/.tapps-mcp/knowledge/``).
        max_domains: Maximum number of business domains to warm.

    Returns:
        Summary dict with ``warmed``, ``skipped``, and ``errors`` lists.
    """
    from tapps_core.experts.business_knowledge import get_business_knowledge_path
    from tapps_core.experts.registry import ExpertRegistry
    from tapps_core.experts.vector_rag import VectorKnowledgeBase

    business_experts = ExpertRegistry.get_business_experts()
    if not business_experts:
        return {"warmed": [], "skipped": [], "errors": []}

    warmed: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    for expert in business_experts[:max_domains]:
        domain = expert.primary_domain

        if not expert.rag_enabled:
            skipped.append(domain)
            logger.debug("business_rag_warm_skip", domain=domain, reason="rag_disabled")
            continue

        knowledge_path = get_business_knowledge_path(project_root, expert)
        if not knowledge_path.exists():
            skipped.append(domain)
            logger.debug("business_rag_warm_skip", domain=domain, reason="no_knowledge_dir")
            continue

        md_files = list(knowledge_path.glob("*.md"))
        if not md_files:
            skipped.append(domain)
            logger.debug("business_rag_warm_skip", domain=domain, reason="no_md_files")
            continue

        try:
            vkb = VectorKnowledgeBase(
                knowledge_path,
                domain=domain,
            )
            # Trigger index build/load
            vkb.search("overview patterns best practices", max_results=1)

            if vkb.backend_type == "vector":
                warmed.append(domain)
                logger.debug("business_rag_warm_domain", domain=domain)
            else:
                skipped.append(domain)
                logger.debug(
                    "business_rag_warm_skip",
                    domain=domain,
                    reason="faiss_unavailable",
                )
        except (OSError, RuntimeError, ValueError, ImportError) as e:
            errors.append(domain)
            logger.debug("business_rag_warm_failed", domain=domain, error=str(e))

    return {"warmed": warmed, "skipped": skipped, "errors": errors}

"""Expert RAG index warming — pre-build vector indices from tech stack.

Maps tech stack (languages, frameworks, libraries, domains) to relevant
expert domains and pre-builds VectorKnowledgeBase indices so the first
tapps_consult_expert call for those domains is fast.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from tapps_mcp.experts.domain_utils import sanitize_domain_for_path

if TYPE_CHECKING:
    from pathlib import Path

    from tapps_mcp.project.models import TechStack

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
    from tapps_mcp.experts.registry import ExpertRegistry
    from tapps_mcp.experts.vector_rag import VectorKnowledgeBase

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
                logger.debug(
                    "rag_warm_skip_domain", domain=domain, reason="no_knowledge_dir"
                )
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

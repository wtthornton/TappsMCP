"""Canonical domain playbook registry (ADR-0025).

Replaces EPIC-94 vector experts with static playbooks + lookup hints.
"""

from __future__ import annotations

from tapps_core.playbooks.models import DomainPlaybook, LookupHint

DOMAIN_PLAYBOOKS: dict[str, DomainPlaybook] = {
    "testing-strategies": DomainPlaybook(
        domain_id="testing-strategies",
        display_name="Testing strategies",
        playbook_file="testing-strategies.md",
        lookup_hints=[
            LookupHint(library="pytest", topic="fixtures and parametrize"),
            LookupHint(library="pytest", topic="async tests"),
        ],
        recommended_tools=[
            "tapps_lookup_docs",
            "tapps_diff_impact",
            "tapps_quick_check",
            "tapps_validate_changed",
        ],
        checklist_task_type="qa",
        epic_keywords=["test", "testing", "pytest", "coverage", "e2e", "fixture"],
    ),
    "security": DomainPlaybook(
        domain_id="security",
        display_name="Application security",
        playbook_file="security.md",
        lookup_hints=[
            LookupHint(library="python-security", topic="input validation"),
            LookupHint(library="bandit", topic="configuration"),
        ],
        recommended_tools=[
            "tapps_lookup_docs",
            "tapps_security_scan",
            "tapps_dependency_scan",
            "tapps_validate_changed",
        ],
        checklist_task_type="security",
        epic_keywords=["security", "auth", "cve", "vulnerability", "owasp", "secret"],
    ),
    "user-experience": DomainPlaybook(
        domain_id="user-experience",
        display_name="Frontend / UX",
        playbook_file="user-experience.md",
        lookup_hints=[
            LookupHint(library="react", topic="accessibility"),
            LookupHint(library="nextjs", topic="routing"),
        ],
        recommended_tools=[
            "tapps_lookup_docs",
            "tapps_score_file",
            "tapps_quick_check",
            "tapps_validate_changed",
        ],
        checklist_task_type="frontend",
        epic_keywords=["ui", "frontend", "react", "vue", "accessibility", "a11y", "css"],
    ),
    "performance-optimization": DomainPlaybook(
        domain_id="performance-optimization",
        display_name="Performance optimization",
        playbook_file="performance-optimization.md",
        lookup_hints=[
            LookupHint(library="python", topic="profiling"),
        ],
        recommended_tools=[
            "tapps_call_graph",
            "tapps_impact_analysis",
            "tapps_quick_check",
        ],
        checklist_task_type="refactor",
        epic_keywords=["performance", "latency", "benchmark", "slow", "optimize"],
    ),
    "api-design-integration": DomainPlaybook(
        domain_id="api-design-integration",
        display_name="API design",
        playbook_file="api-design-integration.md",
        lookup_hints=[
            LookupHint(library="fastapi", topic="routing best practices"),
            LookupHint(library="pydantic", topic="models"),
        ],
        recommended_tools=[
            "tapps_lookup_docs",
            "tapps_impact_analysis",
            "tapps_quick_check",
        ],
        checklist_task_type="feature",
        epic_keywords=["api", "rest", "endpoint", "graphql", "openapi"],
    ),
    "software-architecture": DomainPlaybook(
        domain_id="software-architecture",
        display_name="Software architecture",
        playbook_file="software-architecture.md",
        lookup_hints=[],
        recommended_tools=[
            "tapps_impact_analysis",
            "tapps_call_graph",
            "tapps_dependency_graph",
        ],
        checklist_task_type="refactor",
        epic_keywords=["architecture", "refactor", "module", "boundary", "monolith"],
    ),
}

DOMAIN_ALIASES: dict[str, str] = {
    "testing": "testing-strategies",
    "frontend": "user-experience",
    "ux": "user-experience",
    "perf": "performance-optimization",
    "performance": "performance-optimization",
    "api": "api-design-integration",
    "architecture": "software-architecture",
}


def list_domain_ids() -> list[str]:
    """Return sorted canonical domain ids."""
    return sorted(DOMAIN_PLAYBOOKS.keys())


def resolve_domain_id(domain: str) -> str | None:
    """Resolve a domain id or alias to a canonical id."""
    key = domain.strip().lower()
    if key in DOMAIN_PLAYBOOKS:
        return key
    return DOMAIN_ALIASES.get(key)


def get_playbook(domain: str) -> DomainPlaybook | None:
    """Return playbook metadata for *domain* (id or alias), or None."""
    resolved = resolve_domain_id(domain)
    if resolved is None:
        return None
    return DOMAIN_PLAYBOOKS[resolved]


def suggest_domains_for_text(text: str, *, limit: int = 3) -> list[str]:
    """Rank domains by keyword hits in *text* (deterministic)."""
    lowered = text.lower()
    scores: list[tuple[int, str]] = []
    for domain_id, meta in DOMAIN_PLAYBOOKS.items():
        hits = sum(1 for kw in meta.epic_keywords if kw in lowered)
        if hits:
            scores.append((hits, domain_id))
    scores.sort(key=lambda item: (-item[0], item[1]))
    return [domain_id for _, domain_id in scores[:limit]]


def did_you_mean_domain(domain: str, *, limit: int = 3) -> list[str]:
    """Simple prefix/substring suggestions for unknown domain ids."""
    key = domain.strip().lower()
    options = list_domain_ids() + list(DOMAIN_ALIASES.keys())
    matches = [opt for opt in options if key in opt or opt.startswith(key)]
    return sorted(set(matches))[:limit]

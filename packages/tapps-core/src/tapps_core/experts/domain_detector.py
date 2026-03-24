"""Lightweight domain detector — maps questions and repo signals to expert domains.

This is a simplified version of the TappsCodingAgents ``DomainStackDetector``
stripped of its ``ProjectProfile`` dependency.  It provides two capabilities:

1. **Question routing** — keyword analysis to find the best domain for a user
   question.
2. **Repo signal detection** — file-system scanning to detect the project's
   technology stack and map it to relevant domains.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, ClassVar, Literal

if TYPE_CHECKING:
    from pathlib import Path

from tapps_core.experts.models import DomainMapping
from tapps_core.experts.query_expansion import expand_query
from tapps_core.experts.registry import ExpertRegistry

# ---------------------------------------------------------------------------
# Question → domain keyword map
# ---------------------------------------------------------------------------

# Each domain has a set of keywords.  A question is scored against every
# domain by counting keyword hits.  The highest-scoring domain wins.

DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "security": [
        "security",
        "vulnerability",
        "cve",
        "owasp",
        "xss",
        "sql injection",
        "csrf",
        "authentication",
        "authorization",
        "encryption",
        "tls",
        "ssl",
        "secret",
        "credential",
        "token",
        "jwt",
        "oauth",
        "cors",
        "sanitize",
        "exploit",
        "attack",
        "threat",
        "firewall",
        "penetration",
    ],
    "performance-optimization": [
        "performance",
        "speed",
        "latency",
        "throughput",
        "bottleneck",
        "profiling",
        "cache",
        "caching",
        "optimise",
        "optimize",
        "memory",
        "cpu",
        "benchmark",
        "slow",
        "fast",
        "concurrency",
        "async",
        "parallel",
        "thread",
        "pool",
        "batch",
    ],
    "testing-strategies": [
        "test",
        "testing",
        "unit test",
        "integration test",
        "e2e",
        "coverage",
        "mock",
        "stub",
        "fixture",
        "assert",
        "pytest",
        "jest",
        "junit",
        "tdd",
        "bdd",
        "regression",
        "snapshot",
        "cypress",
    ],
    "code-quality-analysis": [
        "code quality",
        "lint",
        "linting",
        "ruff",
        "pylint",
        "flake8",
        "static analysis",
        "complexity",
        "cyclomatic",
        "maintainability",
        "refactor",
        "clean code",
        "code smell",
        "technical debt",
        "mypy",
        "type check",
        "typing",
        "mypy strict",
        "bandit",
        "radon",
        "vulture",
        "quality gate",
        "scoring pipeline",
    ],
    "software-architecture": [
        "architecture",
        "design pattern",
        "microservice",
        "monolith",
        "modular",
        "dependency injection",
        "solid",
        "clean architecture",
        "hexagonal",
        "event driven",
        "cqrs",
        "domain driven",
        "layered",
        "system design",
        "scalability",
    ],
    "development-workflow": [
        "ci",
        "cd",
        "pipeline",
        "workflow",
        "deploy",
        "deployment",
        "build",
        "release",
        "git",
        "branch",
        "merge",
        "pr",
        "code review",
        "devops",
        "automation",
        "makefile",
        "docker compose",
        "github actions",
        "dependabot",
        "oidc",
        "trusted publishing",
        "trivy",
        "hadolint",
        "ghcr",
        "sarif",
    ],
    "data-privacy-compliance": [
        "privacy",
        "gdpr",
        "hipaa",
        "compliance",
        "regulation",
        "pii",
        "data protection",
        "consent",
        "audit",
        "retention",
        "anonymize",
        "pseudonymize",
        "data subject",
        "breach notification",
    ],
    "accessibility": [
        "accessibility",
        "a11y",
        "wcag",
        "aria",
        "screen reader",
        "keyboard navigation",
        "contrast",
        "alt text",
        "assistive",
        "inclusive",
        "disability",
    ],
    "user-experience": [
        "ux",
        "user experience",
        "usability",
        "ui",
        "frontend",
        "react",
        "vue",
        "angular",
        "css",
        "tailwind",
        "responsive",
        "mobile",
        "animation",
        "component",
        "layout",
        "design system",
        "design token",
        "dark mode",
        "theming",
        "form validation",
        "skeleton",
        "loading state",
        "core web vitals",
        "view transition",
        "container query",
        "shadcn",
        "radix",
        "next.js",
        "nextjs",
        "remix",
        "astro",
        "server component",
        "state management",
        "zustand",
        "react query",
        "optimistic ui",
        "pwa",
        "progressive web app",
        "wireframe",
        "prototype",
        "figma",
        "storybook",
        "material design",
        "fluent design",
        "polaris",
        "carbon design",
        "chakra",
        "mantine",
        "headless ui",
        "react aria",
        "heuristic",
        "nielsen",
        "user journey",
        "information architecture",
    ],
    "documentation-knowledge-management": [
        "documentation",
        "docs",
        "readme",
        "changelog",
        "api docs",
        "docstring",
        "sphinx",
        "mkdocs",
        "wiki",
        "knowledge base",
        "technical writing",
    ],
    "ai-frameworks": [
        "ai",
        "machine learning",
        "ml",
        "llm",
        "gpt",
        "claude",
        "transformer",
        "neural",
        "model",
        "prompt",
        "agent",
        "rag",
        "embedding",
        "fine-tune",
        "langchain",
        "openai",
    ],
    "agent-learning": [
        "agent learning",
        "memory",
        "adaptive",
        "reinforcement",
        "feedback loop",
        "self-improve",
        "experience",
        "session memory",
        "knowledge graph",
        "learning rate",
        "memory system",
        "memory store",
        "memory persistence",
        "memory decay",
        "memory tier",
        "shared memory",
        "contradiction detection",
    ],
    "observability-monitoring": [
        "observability",
        "monitoring",
        "logging",
        "metrics",
        "tracing",
        "alert",
        "dashboard",
        "prometheus",
        "grafana",
        "datadog",
        "sentry",
        "log level",
        "structured log",
        "opentelemetry",
    ],
    "api-design-integration": [
        "api",
        "rest",
        "graphql",
        "grpc",
        "endpoint",
        "route",
        "request",
        "response",
        "status code",
        "pagination",
        "versioning",
        "webhook",
        "swagger",
        "openapi",
        "integration",
    ],
    "cloud-infrastructure": [
        "cloud",
        "aws",
        "azure",
        "gcp",
        "kubernetes",
        "k8s",
        "docker",
        "terraform",
        "infrastructure",
        "iac",
        "serverless",
        "lambda",
        "ec2",
        "s3",
        "container",
        "helm",
        "istio",
    ],
    "database-data-management": [
        "database",
        "sql",
        "nosql",
        "postgres",
        "mysql",
        "mongodb",
        "redis",
        "migration",
        "schema",
        "query",
        "index",
        "orm",
        "sqlalchemy",
        "prisma",
        "transaction",
        "replication",
    ],
    "github": [
        "github",
        "github actions",
        "github workflow",
        "pull request template",
        "issue template",
        "issue form",
        "dependabot",
        "codeql",
        "code scanning",
        "secret scanning",
        "push protection",
        "codeowners",
        "copilot coding agent",
        "copilot agent",
        "copilot review",
        "agentic workflow",
        "copilot setup steps",
        "artifact attestation",
        "github runner",
        "github mcp",
        "github project",
        "merge queue",
        "branch protection",
        "ruleset",
        "github api",
    ],
}


def _score_keywords(
    question_clean: str,
    domain: str,
    keywords: list[str],
    expert_name: str,
) -> DomainMapping | None:
    """Score *question_clean* against *keywords* for a single domain.

    Uses word-boundary regex matching with multi-word keyword bonus weighting.
    Shared by both :meth:`DomainDetector.detect_from_question` and
    :meth:`DomainDetector.detect_from_question_merged`.

    Args:
        question_clean: Lowered, punctuation-stripped question text.
        domain: The domain slug to score against.
        keywords: Keyword list for the domain.
        expert_name: Human-readable expert name for the reasoning field.

    Returns:
        A :class:`DomainMapping` if at least one keyword matched, else ``None``.
    """
    hits: list[str] = []
    hit_weight = 0.0
    for kw in keywords:
        # Use word-boundary matching to avoid substring false positives
        # (e.g. "ci" matching inside "injection").
        pattern = r"\b" + re.escape(kw.lower()) + r"\b"
        if re.search(pattern, question_clean):
            hits.append(kw)
            # Multi-word keywords are stronger signals.
            word_count = len(kw.split())
            hit_weight += 1.0 + (word_count - 1) * 0.5
    if not hits:
        return None

    # Confidence based on weighted hit count, normalised.
    _min_divisor = 3
    confidence = min(1.0, hit_weight / _min_divisor)

    return DomainMapping(
        domain=domain,
        confidence=round(confidence, 3),
        signals=[f"keyword:{kw}" for kw in hits],
        reasoning=f"Matched {len(hits)} keyword(s) for {expert_name}.",
    )


class DomainDetector:
    """Detects the best expert domain for a question or project."""

    # Repo-file → technology signal map (file-system detection).
    REPO_FILE_SIGNALS: ClassVar[dict[str, list[str]]] = {
        "Dockerfile": ["cloud-infrastructure", "development-workflow"],
        "docker-compose.yml": ["cloud-infrastructure", "development-workflow"],
        "docker-compose.yaml": ["cloud-infrastructure", "development-workflow"],
        "k8s": ["cloud-infrastructure"],
        "kubernetes": ["cloud-infrastructure"],
        ".github/workflows": ["development-workflow"],
        ".gitlab-ci.yml": ["development-workflow"],
        "Makefile": ["development-workflow"],
        "pyproject.toml": ["code-quality-analysis"],
        "setup.py": ["code-quality-analysis"],
        "package.json": ["user-experience"],
        "tsconfig.json": ["user-experience"],
        "requirements.txt": ["code-quality-analysis"],
        "pytest.ini": ["testing-strategies"],
        "conftest.py": ["testing-strategies"],
        ".security": ["security"],
        "sonar-project.properties": ["code-quality-analysis"],
    }

    # ------------------------------------------------------------------
    # Question routing
    # ------------------------------------------------------------------

    @classmethod
    def detect_from_question(cls, question: str) -> list[DomainMapping]:
        """Score *question* against all built-in domains and return ranked results.

        Args:
            question: The user's question text.

        Returns:
            List of :class:`DomainMapping` sorted by confidence (descending).
            Only domains with a positive score are included.
        """
        # Expand synonyms before matching to improve recall.
        question_expanded = expand_query(question)
        question_lower = question_expanded.lower()
        # Strip punctuation for better keyword matching.
        question_clean = re.sub(r"[^\w\s-]", " ", question_lower)

        results: list[DomainMapping] = []

        for domain, keywords in DOMAIN_KEYWORDS.items():
            expert = ExpertRegistry.get_expert_for_domain(domain)
            expert_name = expert.expert_name if expert else domain
            merged_keywords = list(keywords)
            if expert is not None and expert.keywords:
                seen_lower = {k.lower() for k in merged_keywords}
                for extra in expert.keywords:
                    el = extra.lower()
                    if el not in seen_lower:
                        seen_lower.add(el)
                        merged_keywords.append(el)
            mapping = _score_keywords(
                question_clean, domain, merged_keywords, expert_name
            )
            if mapping is not None:
                results.append(mapping)

        results.sort(key=lambda m: m.confidence, reverse=True)
        return results

    # ------------------------------------------------------------------
    # Merged detection (built-in + business experts)
    # ------------------------------------------------------------------

    @classmethod
    def detect_from_question_merged(cls, question: str) -> list[DomainMapping]:
        """Score *question* against built-in AND business domains.

        When ``adaptive.enabled`` is True in settings, applies learned domain
        weights from feedback to adjust confidence scores (Epic 57). Falls back
        to static keyword matching otherwise.

        Calls :meth:`detect_from_question` for built-in domains, then scores
        against keywords from registered business experts.  All results are
        merged and re-sorted by confidence (descending).

        Args:
            question: The user's question text.

        Returns:
            List of :class:`DomainMapping` sorted by confidence (descending).
            Only domains with a positive score are included.
        """
        # Start with built-in domain results.
        results = cls.detect_from_question(question)

        # Score business expert keywords.
        business_experts = ExpertRegistry.get_business_experts()

        # Prepare question text the same way as detect_from_question.
        question_expanded = expand_query(question)
        question_lower = question_expanded.lower()
        question_clean = re.sub(r"[^\w\s-]", " ", question_lower)

        for expert in business_experts:
            if not expert.keywords:
                continue
            mapping = _score_keywords(
                question_clean,
                expert.primary_domain,
                expert.keywords,
                expert.expert_name,
            )
            if mapping is not None:
                results.append(mapping)

        # Apply adaptive weights if enabled (Epic 57).
        results = cls._apply_adaptive_weights(results)

        # Re-sort merged results by confidence.
        results.sort(key=lambda m: m.confidence, reverse=True)
        return results

    @classmethod
    def _apply_adaptive_weights(
        cls,
        results: list[DomainMapping],
    ) -> list[DomainMapping]:
        """Apply learned domain weights to adjust confidence scores.

        When adaptive.enabled is True, multiplies each domain's confidence
        by its learned weight from DomainWeightStore. Logs when adaptive
        routing changes the top result.

        Args:
            results: Domain mappings with base confidence scores.

        Returns:
            Domain mappings with weight-adjusted confidence scores.
        """
        import structlog

        from tapps_core.config.settings import load_settings

        logger = structlog.get_logger(__name__)
        settings = load_settings()

        if not settings.adaptive.enabled:
            return results

        if not results:
            return results

        try:
            from tapps_core.adaptive.persistence import DomainWeightStore

            store = DomainWeightStore(settings.project_root)
            business_domains = ExpertRegistry.get_business_domains()

            # Track original top domain for logging.
            original_top = results[0].domain if results else None

            adjusted: list[DomainMapping] = []
            for mapping in results:
                domain = mapping.domain
                is_business = domain in business_domains
                domain_type: Literal["technical", "business"] = (
                    "business" if is_business else "technical"
                )

                weight = store.get_weight_value(domain, domain_type=domain_type)
                adjusted_confidence = min(1.0, mapping.confidence * weight)

                # Create new mapping with adjusted confidence.
                adjusted.append(
                    DomainMapping(
                        domain=mapping.domain,
                        confidence=round(adjusted_confidence, 3),
                        signals=mapping.signals + [f"weight:{weight:.2f}"],
                        reasoning=mapping.reasoning,
                    )
                )

            # Sort by adjusted confidence.
            adjusted.sort(key=lambda m: m.confidence, reverse=True)

            # Log if adaptive routing changed the top result.
            if adjusted and adjusted[0].domain != original_top:
                logger.debug(
                    "adaptive_routing_override",
                    original_top=original_top,
                    new_top=adjusted[0].domain,
                )

            return adjusted

        except Exception:
            logger.debug("adaptive_weight_application_failed", exc_info=True)
            return results

    # ------------------------------------------------------------------
    # Repo-signal detection (lightweight)
    # ------------------------------------------------------------------

    @classmethod
    def detect_from_project(cls, project_root: Path) -> list[DomainMapping]:
        """Scan *project_root* for technology signals.

        Args:
            project_root: Root directory of the project.

        Returns:
            List of :class:`DomainMapping` sorted by confidence.
        """
        domain_hits: dict[str, list[str]] = {}

        for marker, domains in cls.REPO_FILE_SIGNALS.items():
            target = project_root / marker
            if target.exists():
                for d in domains:
                    domain_hits.setdefault(d, []).append(marker)

        results: list[DomainMapping] = []
        for domain, signals in domain_hits.items():
            confidence = min(1.0, len(signals) * 0.4)
            expert = ExpertRegistry.get_expert_for_domain(domain)
            expert_name = expert.expert_name if expert else domain
            results.append(
                DomainMapping(
                    domain=domain,
                    confidence=round(confidence, 3),
                    signals=[f"file:{s}" for s in signals],
                    reasoning=f"Found {len(signals)} file signal(s) for {expert_name}.",
                )
            )

        results.sort(key=lambda m: m.confidence, reverse=True)
        return results

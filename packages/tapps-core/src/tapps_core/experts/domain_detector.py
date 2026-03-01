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
from typing import TYPE_CHECKING, ClassVar

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
        "responsive",
        "mobile",
        "animation",
        "component",
        "layout",
        "design system",
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
        """Score *question* against all domains and return ranked results.

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
            hits: list[str] = []
            hit_weight = 0.0
            for kw in keywords:
                # Use word-boundary matching to avoid substring false positives
                # (e.g. "ci" matching inside "injection").
                pattern = r"\b" + re.escape(kw) + r"\b"
                if re.search(pattern, question_clean):
                    hits.append(kw)
                    # Multi-word keywords are stronger signals.
                    word_count = len(kw.split())
                    hit_weight += 1.0 + (word_count - 1) * 0.5
            if not hits:
                continue

            # Confidence based on weighted hit count, normalised.
            _min_divisor = 3
            confidence = min(1.0, hit_weight / _min_divisor)

            expert = ExpertRegistry.get_expert_for_domain(domain)
            expert_name = expert.expert_name if expert else domain

            results.append(
                DomainMapping(
                    domain=domain,
                    confidence=round(confidence, 3),
                    signals=[f"keyword:{kw}" for kw in hits],
                    reasoning=f"Matched {len(hits)} keyword(s) for {expert_name}.",
                )
            )

        results.sort(key=lambda m: m.confidence, reverse=True)
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

"""Domain detection quality dataset -- 20 parameterized queries.

Verifies detection accuracy across three tiers:
1. Static keyword matches -- regression guard (10 queries)
2. Synonym-expansion-dependent matches (5 queries)
3. Adaptive routing benefit -- queries only the adaptive detector catches (5 queries)

Accuracy thresholds:
- Static only:          >= 10/20 (the 10 direct keyword queries)
- Static + synonyms:    >= 15/20 (adds the 5 synonym-dependent queries)
- Adaptive (mocked):    >= 18/20 (adds the 5 adaptive-only queries)
"""

from __future__ import annotations

import re
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from tapps_core.experts.adaptive_domain_detector import AdaptiveDomainDetector, DomainSuggestion
from tapps_core.experts.domain_detector import DOMAIN_KEYWORDS, DomainDetector

# ---------------------------------------------------------------------------
# Tier labels for categorisation
# ---------------------------------------------------------------------------
TIER_STATIC = "static"
TIER_SYNONYM = "synonym"
TIER_ADAPTIVE = "adaptive"

# ---------------------------------------------------------------------------
# 20-query test dataset
# ---------------------------------------------------------------------------

_DETECTION_CASES: list[Any] = [
    # --- 1-10: Direct keyword matches (regression guard, tier=static) ---
    pytest.param(
        "How do I prevent SQL injection in my API?",
        "security",
        TIER_STATIC,
        "direct keyword: sql injection",
        id="direct-sql-injection",
    ),
    pytest.param(
        "My application has high latency and low throughput",
        "performance-optimization",
        TIER_STATIC,
        "direct keywords: latency, throughput",
        id="direct-latency-throughput",
    ),
    pytest.param(
        "How should I structure my pytest unit tests?",
        "testing-strategies",
        TIER_STATIC,
        "direct keywords: pytest, unit test",
        id="direct-pytest-unit-tests",
    ),
    pytest.param(
        "What is the best way to design a PostgreSQL schema?",
        "database-data-management",
        TIER_STATIC,
        "direct keyword: schema + postgres",
        id="direct-postgres-schema",
    ),
    pytest.param(
        "How do I configure ruff rules?",
        "code-quality-analysis",
        TIER_STATIC,
        "direct keyword: ruff",
        id="direct-ruff-rules",
    ),
    pytest.param(
        "Best practices for Kubernetes deployment?",
        "cloud-infrastructure",
        TIER_STATIC,
        "direct keyword: kubernetes",
        id="direct-kubernetes",
    ),
    pytest.param(
        "How to set up GitHub Actions CI pipeline?",
        "development-workflow",
        TIER_STATIC,
        "direct keywords: github actions, pipeline",
        id="direct-github-actions",
    ),
    pytest.param(
        "How to implement GDPR compliance?",
        "data-privacy-compliance",
        TIER_STATIC,
        "direct keywords: gdpr, compliance",
        id="direct-gdpr-compliance",
    ),
    pytest.param(
        "How to add ARIA labels for accessibility?",
        "accessibility",
        TIER_STATIC,
        "direct keywords: aria, accessibility",
        id="direct-aria-accessibility",
    ),
    pytest.param(
        "How to design a REST API with proper versioning?",
        "api-design-integration",
        TIER_STATIC,
        "direct keywords: rest, api, versioning",
        id="direct-rest-api-versioning",
    ),
    # --- 11-15: Synonym-dependent matches (tier=synonym) ---
    pytest.param(
        "How to find vulns in my code?",
        "security",
        TIER_SYNONYM,
        "synonym expansion: vulns -> vulnerability",
        id="synonym-vulns",
    ),
    pytest.param(
        "How to write unittests?",
        "testing-strategies",
        TIER_SYNONYM,
        "synonym expansion: unittests -> unit test",
        id="synonym-unittests",
    ),
    pytest.param(
        "How to connect to a db?",
        "database-data-management",
        TIER_SYNONYM,
        "synonym expansion: db -> database",
        id="synonym-db",
    ),
    pytest.param(
        "How to use gql queries?",
        "api-design-integration",
        TIER_SYNONYM,
        "synonym expansion: gql -> graphql",
        id="synonym-gql",
    ),
    pytest.param(
        "Tips for refactoring legacy code?",
        "code-quality-analysis",
        TIER_SYNONYM,
        "synonym expansion: refactoring -> refactor",
        id="synonym-refactoring",
    ),
    # --- 16-20: Adaptive routing benefit (tier=adaptive) ---
    # These queries contain terms NOT in DOMAIN_KEYWORDS or SYNONYMS,
    # but ARE matched by AdaptiveDomainDetector.DOMAIN_KEYWORDS.
    pytest.param(
        "How to handle user login with MFA?",
        "authentication",
        TIER_ADAPTIVE,
        "adaptive: login + mfa -> authentication domain",
        id="adaptive-login-mfa",
    ),
    pytest.param(
        "Best approach for cache invalidation with Redis?",
        "caching",
        TIER_ADAPTIVE,
        "adaptive: cache invalidation + redis -> caching domain",
        id="adaptive-cache-invalidation",
    ),
    pytest.param(
        "How to set up RabbitMQ task queues?",
        "queue",
        TIER_ADAPTIVE,
        "adaptive: rabbitmq + task queue -> queue domain",
        id="adaptive-rabbitmq-queue",
    ),
    pytest.param(
        "Implementing RBAC for access control",
        "authorization",
        TIER_ADAPTIVE,
        "adaptive: rbac + access control -> authorization domain",
        id="adaptive-rbac-access-control",
    ),
    pytest.param(
        "How to build full-text search with Elasticsearch?",
        "search",
        TIER_ADAPTIVE,
        "adaptive: elasticsearch + full-text -> search domain",
        id="adaptive-elasticsearch-search",
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _static_detect_without_expansion(question: str) -> list[str]:
    """Run keyword matching WITHOUT synonym expansion (pure static)."""
    question_lower = question.lower()
    question_clean = re.sub(r"[^\w\s-]", " ", question_lower)

    matched_domains: list[str] = []
    for domain, keywords in DOMAIN_KEYWORDS.items():
        for kw in keywords:
            pattern = r"\b" + re.escape(kw) + r"\b"
            if re.search(pattern, question_clean):
                matched_domains.append(domain)
                break
    return matched_domains


def _count_tier_passes(
    tier_filter: str | None, use_expansion: bool
) -> tuple[int, int, list[str]]:
    """Count how many cases pass, optionally filtering by tier."""
    passed = 0
    total = 0
    failures: list[str] = []

    for case in _DETECTION_CASES:
        query, expected_domain, tier, description = case.values
        if tier_filter and tier != tier_filter:
            # For cumulative checks, include static+synonym but skip adaptive.
            if tier_filter == "cumulative_static_synonym" and tier == TIER_ADAPTIVE:
                continue
            elif tier_filter not in (TIER_STATIC, TIER_SYNONYM, TIER_ADAPTIVE,
                                     "cumulative_static_synonym"):
                continue
        if tier == TIER_ADAPTIVE:
            continue  # Adaptive queries don't use the static detector.

        total += 1
        if use_expansion:
            results = DomainDetector.detect_from_question(query)
            domains = [r.domain for r in results]
        else:
            domains = _static_detect_without_expansion(query)

        if expected_domain in domains:
            passed += 1
        else:
            failures.append(f"  {query!r} -> expected {expected_domain}, got {domains}")

    return passed, total, failures


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestDomainDetectionQuality:
    """20-query quality dataset for domain detection accuracy."""

    # ------------------------------------------------------------------
    # Individual parameterized tests (full pipeline for static + synonym)
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        ("query", "expected_domain", "tier", "description"),
        [c for c in _DETECTION_CASES if c.values[2] != TIER_ADAPTIVE],
    )
    def test_static_and_synonym_detection(
        self, query: str, expected_domain: str, tier: str, description: str
    ) -> None:
        """Verify that *query* maps to *expected_domain* via static + synonym pipeline."""
        results = DomainDetector.detect_from_question(query)
        domains = [r.domain for r in results]
        assert expected_domain in domains, (
            f"Expected '{expected_domain}' in detected domains {domains} "
            f"for query: {query!r} ({description})"
        )

    @pytest.mark.parametrize(
        ("query", "expected_domain", "tier", "description"),
        [c for c in _DETECTION_CASES if c.values[2] == TIER_ADAPTIVE],
    )
    @pytest.mark.asyncio
    async def test_adaptive_detection(
        self, query: str, expected_domain: str, tier: str, description: str
    ) -> None:
        """Verify that *query* maps to *expected_domain* via the adaptive detector."""
        detector = AdaptiveDomainDetector()
        # Patch out _get_existing_domains so the adaptive detector doesn't
        # filter out domains that happen to be registered already.
        with patch.object(AdaptiveDomainDetector, "_get_existing_domains", return_value=set()):
            results = await detector.detect_domains(prompt=query)
        domains = [s.domain for s in results]
        assert expected_domain in domains, (
            f"Expected '{expected_domain}' in adaptive domains {domains} "
            f"for query: {query!r} ({description})"
        )

    # ------------------------------------------------------------------
    # Tiered accuracy thresholds
    # ------------------------------------------------------------------

    def test_static_only_accuracy(self) -> None:
        """Static detection (no synonyms) should match >= 10/20 static-tier queries."""
        passed = 0
        total = 0
        failures: list[str] = []

        for case in _DETECTION_CASES:
            query, expected_domain, tier, _desc = case.values
            if tier != TIER_STATIC:
                continue
            total += 1
            domains = _static_detect_without_expansion(query)
            if expected_domain in domains:
                passed += 1
            else:
                failures.append(f"  {query!r} -> expected {expected_domain}, got {domains}")

        detail = "\n".join(failures) if failures else "(none)"
        assert passed >= 10, (  # noqa: PLR2004
            f"Static-only accuracy {passed}/{total} is below 10.\nFailures:\n{detail}"
        )

    def test_static_plus_synonyms_accuracy(self) -> None:
        """Static + synonym expansion should match >= 15/20 (static + synonym tiers)."""
        passed = 0
        total = 0
        failures: list[str] = []

        for case in _DETECTION_CASES:
            query, expected_domain, tier, _desc = case.values
            if tier == TIER_ADAPTIVE:
                continue
            total += 1
            results = DomainDetector.detect_from_question(query)
            domains = [r.domain for r in results]
            if expected_domain in domains:
                passed += 1
            else:
                failures.append(f"  {query!r} -> expected {expected_domain}, got {domains}")

        detail = "\n".join(failures) if failures else "(none)"
        assert passed >= 15, (  # noqa: PLR2004
            f"Static+synonym accuracy {passed}/{total} is below 15.\nFailures:\n{detail}"
        )

    @pytest.mark.asyncio
    async def test_adaptive_overall_accuracy(self) -> None:
        """Full pipeline (static + synonym + adaptive) should match >= 18/20."""
        passed = 0
        total = len(_DETECTION_CASES)
        failures: list[str] = []

        detector = AdaptiveDomainDetector()

        for case in _DETECTION_CASES:
            query, expected_domain, tier, _desc = case.values

            if tier == TIER_ADAPTIVE:
                # Use the adaptive detector for adaptive-tier queries.
                with patch.object(
                    AdaptiveDomainDetector, "_get_existing_domains", return_value=set()
                ):
                    results = await detector.detect_domains(prompt=query)
                domains = [s.domain for s in results]
            else:
                # Use the static+synonym pipeline for the rest.
                results_static = DomainDetector.detect_from_question(query)
                domains = [r.domain for r in results_static]

            if expected_domain in domains:
                passed += 1
            else:
                failures.append(
                    f"  [{tier}] {query!r} -> expected {expected_domain}, got {domains}"
                )

        detail = "\n".join(failures) if failures else "(none)"
        assert passed >= 18, (  # noqa: PLR2004
            f"Full-pipeline accuracy {passed}/{total} is below 18/20.\nFailures:\n{detail}"
        )

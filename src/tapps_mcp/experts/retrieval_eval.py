"""Retrieval evaluation harness — benchmark queries, metrics, and quality gates.

Provides a standard benchmark query set across domains and measures retrieval
quality: top-k relevance, resolution accuracy, latency, and fallback rate.
Used by CI and manual evaluation to prevent regressions when tuning
ranking, fuzzy matching, or hybrid retrieval.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

from tapps_mcp.experts.models import KnowledgeChunk
from tapps_mcp.experts.rag import SimpleKnowledgeBase
from tapps_mcp.experts.registry import ExpertRegistry
from tapps_mcp.experts.vector_rag import VectorKnowledgeBase

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Benchmark query set
# ---------------------------------------------------------------------------

@dataclass
class BenchmarkQuery:
    """A single benchmark query with expected retrieval properties."""

    domain: str
    query: str
    expected_keywords: list[str] = field(default_factory=list)
    min_chunks: int = 1
    description: str = ""


# Representative queries across domains — each should return relevant results.
BENCHMARK_QUERIES: list[BenchmarkQuery] = [
    BenchmarkQuery(
        domain="security",
        query="How to prevent SQL injection in Python?",
        expected_keywords=["sql", "injection", "parameterized", "query"],
        description="Core security topic — must return relevant chunks",
    ),
    BenchmarkQuery(
        domain="security",
        query="What are OWASP top 10 vulnerabilities?",
        expected_keywords=["owasp"],
        description="Well-known security framework",
    ),
    BenchmarkQuery(
        domain="testing-strategies",
        query="How to write pytest fixtures for database tests?",
        expected_keywords=["pytest", "fixture"],
        description="Testing best practice",
    ),
    BenchmarkQuery(
        domain="testing-strategies",
        query="How to configure base URLs and environment variables in tests?",
        expected_keywords=["url", "config"],
        description="Testing KB expansion validation (10.4)",
    ),
    BenchmarkQuery(
        domain="api-design-integration",
        query="How to design RESTful API endpoints?",
        expected_keywords=["api", "rest", "endpoint"],
        description="API design fundamentals",
    ),
    BenchmarkQuery(
        domain="database-data-management",
        query="What are best practices for database migrations?",
        expected_keywords=["migration", "database"],
        description="Database management topic",
    ),
    BenchmarkQuery(
        domain="performance-optimization",
        query="How to profile and optimize slow queries?",
        expected_keywords=["profile", "performance"],
        description="Performance optimization",
    ),
    BenchmarkQuery(
        domain="software-architecture",
        query="What design patterns work for microservices?",
        expected_keywords=["pattern", "microservice"],
        description="Architecture fundamentals",
    ),
    BenchmarkQuery(
        domain="cloud-infrastructure",
        query="How to write a secure Dockerfile?",
        expected_keywords=["docker"],
        description="Infrastructure security",
    ),
    BenchmarkQuery(
        domain="code-quality-analysis",
        query="How to enforce type hints and linting?",
        expected_keywords=["type", "lint"],
        description="Code quality enforcement",
    ),
]


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

@dataclass
class QueryResult:
    """Result of evaluating a single benchmark query."""

    query: BenchmarkQuery
    chunks_found: int = 0
    top_score: float = 0.0
    keyword_hits: int = 0
    keyword_total: int = 0
    latency_ms: float = 0.0
    passed: bool = False
    backend_type: str = "unknown"


@dataclass
class EvalReport:
    """Aggregate evaluation report."""

    total_queries: int = 0
    passed_queries: int = 0
    failed_queries: int = 0
    pass_rate: float = 0.0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    avg_top_score: float = 0.0
    avg_keyword_coverage: float = 0.0
    fallback_rate: float = 0.0
    results: list[QueryResult] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_queries": self.total_queries,
            "passed_queries": self.passed_queries,
            "failed_queries": self.failed_queries,
            "pass_rate": round(self.pass_rate, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "p95_latency_ms": round(self.p95_latency_ms, 2),
            "avg_top_score": round(self.avg_top_score, 4),
            "avg_keyword_coverage": round(self.avg_keyword_coverage, 4),
            "fallback_rate": round(self.fallback_rate, 4),
            "failures": self.failures,
        }


# ---------------------------------------------------------------------------
# Quality gate thresholds
# ---------------------------------------------------------------------------

# Minimum pass rate for the benchmark suite.
QUALITY_GATE_PASS_RATE = 0.6
# Maximum acceptable p95 latency (ms).
QUALITY_GATE_P95_LATENCY_MS = 500.0
# Minimum average keyword coverage.
QUALITY_GATE_MIN_KEYWORD_COVERAGE = 0.3


# ---------------------------------------------------------------------------
# Evaluation engine
# ---------------------------------------------------------------------------

def _evaluate_query(bq: BenchmarkQuery, kb: VectorKnowledgeBase) -> QueryResult:
    """Evaluate a single benchmark query against a knowledge base."""
    start = time.perf_counter()
    chunks: list[KnowledgeChunk] = kb.search(bq.query, max_results=5)
    latency_ms = (time.perf_counter() - start) * 1000.0

    top_score = chunks[0].score if chunks else 0.0

    # Keyword coverage: how many expected keywords appear in retrieved content.
    all_text = " ".join(c.content.lower() for c in chunks)
    keyword_hits = sum(1 for kw in bq.expected_keywords if kw.lower() in all_text)
    keyword_total = len(bq.expected_keywords)
    keyword_coverage = keyword_hits / keyword_total if keyword_total > 0 else 1.0

    passed = len(chunks) >= bq.min_chunks and keyword_coverage >= 0.25

    return QueryResult(
        query=bq,
        chunks_found=len(chunks),
        top_score=top_score,
        keyword_hits=keyword_hits,
        keyword_total=keyword_total,
        latency_ms=latency_ms,
        passed=passed,
        backend_type=kb.backend_type,
    )


def run_retrieval_eval(
    queries: list[BenchmarkQuery] | None = None,
) -> EvalReport:
    """Run the retrieval evaluation harness.

    Args:
        queries: Optional override for benchmark queries (defaults to BENCHMARK_QUERIES).

    Returns:
        An EvalReport with per-query results and aggregate metrics.
    """
    benchmark = queries or BENCHMARK_QUERIES
    results: list[QueryResult] = []
    failures: list[str] = []

    # Cache knowledge bases by domain to avoid re-loading.
    kb_cache: dict[str, VectorKnowledgeBase] = {}

    for bq in benchmark:
        if bq.domain not in kb_cache:
            expert = ExpertRegistry.get_expert_for_domain(bq.domain)
            if expert is None:
                failures.append(f"No expert for domain: {bq.domain}")
                continue
            from tapps_mcp.experts.domain_utils import sanitize_domain_for_path

            dir_name = expert.knowledge_dir or sanitize_domain_for_path(expert.primary_domain)
            kb_path = ExpertRegistry.get_knowledge_base_path() / dir_name
            kb_cache[bq.domain] = VectorKnowledgeBase(kb_path, domain=bq.domain)

        kb = kb_cache[bq.domain]
        qr = _evaluate_query(bq, kb)
        results.append(qr)
        if not qr.passed:
            failures.append(
                f"FAIL [{bq.domain}] \"{bq.query[:60]}\" — "
                f"chunks={qr.chunks_found}, keywords={qr.keyword_hits}/{qr.keyword_total}"
            )

    # Aggregate.
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    latencies = sorted(r.latency_ms for r in results)
    avg_latency = sum(latencies) / total if total else 0.0
    p95_idx = int(total * 0.95) if total else 0
    p95_latency = latencies[min(p95_idx, total - 1)] if total else 0.0
    top_scores = [r.top_score for r in results]
    avg_top = sum(top_scores) / total if total else 0.0
    coverages = [
        r.keyword_hits / r.keyword_total if r.keyword_total > 0 else 1.0
        for r in results
    ]
    avg_coverage = sum(coverages) / total if total else 0.0
    fallback_count = sum(1 for r in results if r.chunks_found == 0)
    fallback_rate = fallback_count / total if total else 0.0

    return EvalReport(
        total_queries=total,
        passed_queries=passed,
        failed_queries=total - passed,
        pass_rate=passed / total if total else 0.0,
        avg_latency_ms=avg_latency,
        p95_latency_ms=p95_latency,
        avg_top_score=avg_top,
        avg_keyword_coverage=avg_coverage,
        fallback_rate=fallback_rate,
        results=results,
        failures=failures,
    )


def check_quality_gates(report: EvalReport) -> tuple[bool, list[str]]:
    """Check whether the eval report passes quality gates.

    Returns:
        (passed, violations) — True if all gates pass, with list of violation messages.
    """
    violations: list[str] = []

    if report.pass_rate < QUALITY_GATE_PASS_RATE:
        violations.append(
            f"Pass rate {report.pass_rate:.1%} below threshold {QUALITY_GATE_PASS_RATE:.0%}"
        )

    if report.p95_latency_ms > QUALITY_GATE_P95_LATENCY_MS:
        violations.append(
            f"p95 latency {report.p95_latency_ms:.0f}ms exceeds {QUALITY_GATE_P95_LATENCY_MS:.0f}ms"
        )

    if report.avg_keyword_coverage < QUALITY_GATE_MIN_KEYWORD_COVERAGE:
        violations.append(
            f"Avg keyword coverage {report.avg_keyword_coverage:.1%} "
            f"below threshold {QUALITY_GATE_MIN_KEYWORD_COVERAGE:.0%}"
        )

    return len(violations) == 0, violations

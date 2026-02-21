"""Unit tests for tapps_mcp.experts.retrieval_eval — evaluation harness."""

from __future__ import annotations

import pytest

from tapps_mcp.experts.retrieval_eval import (
    BENCHMARK_QUERIES,
    QUALITY_GATE_PASS_RATE,
    BenchmarkQuery,
    EvalReport,
    check_quality_gates,
    run_retrieval_eval,
)


class TestBenchmarkQueries:
    """Validate the benchmark query set itself."""

    def test_has_queries(self) -> None:
        assert len(BENCHMARK_QUERIES) >= 8

    def test_each_query_has_domain(self) -> None:
        for bq in BENCHMARK_QUERIES:
            assert bq.domain, f"Query missing domain: {bq.query}"

    def test_each_query_has_expected_keywords(self) -> None:
        for bq in BENCHMARK_QUERIES:
            assert len(bq.expected_keywords) > 0, f"Query missing keywords: {bq.query}"


class TestRunRetrievalEval:
    """Test the evaluation harness end-to-end."""

    def test_returns_eval_report(self) -> None:
        report = run_retrieval_eval()
        assert isinstance(report, EvalReport)
        assert report.total_queries == len(BENCHMARK_QUERIES)

    def test_pass_rate_above_minimum(self) -> None:
        report = run_retrieval_eval()
        assert report.pass_rate >= QUALITY_GATE_PASS_RATE, (
            f"Pass rate {report.pass_rate:.1%} below gate {QUALITY_GATE_PASS_RATE:.0%}. "
            f"Failures: {report.failures}"
        )

    def test_latency_reasonable(self) -> None:
        report = run_retrieval_eval()
        # p95 latency should be under 2 seconds even in CI.
        assert report.p95_latency_ms < 2000.0

    def test_report_to_dict(self) -> None:
        report = run_retrieval_eval()
        d = report.to_dict()
        assert "pass_rate" in d
        assert "avg_latency_ms" in d
        assert "failures" in d

    def test_custom_queries(self) -> None:
        custom = [
            BenchmarkQuery(
                domain="security",
                query="SQL injection prevention",
                expected_keywords=["sql", "injection"],
            ),
        ]
        report = run_retrieval_eval(queries=custom)
        assert report.total_queries == 1


class TestQualityGates:
    """Test quality gate checking."""

    def test_passing_report(self) -> None:
        report = EvalReport(
            total_queries=10,
            passed_queries=8,
            pass_rate=0.8,
            avg_latency_ms=50.0,
            p95_latency_ms=100.0,
            avg_keyword_coverage=0.6,
        )
        passed, violations = check_quality_gates(report)
        assert passed
        assert violations == []

    def test_failing_pass_rate(self) -> None:
        report = EvalReport(
            total_queries=10,
            passed_queries=3,
            pass_rate=0.3,
            avg_latency_ms=50.0,
            p95_latency_ms=100.0,
            avg_keyword_coverage=0.6,
        )
        passed, violations = check_quality_gates(report)
        assert not passed
        assert any("Pass rate" in v for v in violations)

    def test_failing_latency(self) -> None:
        report = EvalReport(
            total_queries=10,
            passed_queries=8,
            pass_rate=0.8,
            avg_latency_ms=200.0,
            p95_latency_ms=600.0,
            avg_keyword_coverage=0.6,
        )
        passed, violations = check_quality_gates(report)
        assert not passed
        assert any("latency" in v.lower() for v in violations)

    def test_failing_keyword_coverage(self) -> None:
        report = EvalReport(
            total_queries=10,
            passed_queries=8,
            pass_rate=0.8,
            avg_latency_ms=50.0,
            p95_latency_ms=100.0,
            avg_keyword_coverage=0.1,
        )
        passed, violations = check_quality_gates(report)
        assert not passed
        assert any("keyword" in v.lower() for v in violations)

    @pytest.mark.integration
    def test_real_eval_passes_gates(self) -> None:
        """The real benchmark suite should pass quality gates."""
        report = run_retrieval_eval()
        passed, violations = check_quality_gates(report)
        assert passed, f"Quality gate failures: {violations}"

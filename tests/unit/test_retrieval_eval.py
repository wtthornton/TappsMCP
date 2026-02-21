"""Unit tests for tapps_mcp.experts.retrieval_eval — evaluation harness."""

from __future__ import annotations

import pytest

from tapps_mcp.experts.retrieval_eval import (
    BENCHMARK_QUERIES,
    QUALITY_GATE_MIN_KEYWORD_COVERAGE,
    QUALITY_GATE_P95_LATENCY_MS,
    QUALITY_GATE_PASS_RATE,
    BenchmarkQuery,
    EvalReport,
    QueryResult,
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

    def test_each_query_has_min_chunks_positive(self) -> None:
        for bq in BENCHMARK_QUERIES:
            assert bq.min_chunks >= 1, f"Query has invalid min_chunks: {bq.query}"

    def test_domains_are_valid(self) -> None:
        """All benchmark domains should exist in the expert registry."""
        from tapps_mcp.experts.registry import ExpertRegistry
        valid_domains = {e.primary_domain for e in ExpertRegistry.get_all_experts()}
        for bq in BENCHMARK_QUERIES:
            assert bq.domain in valid_domains, f"Invalid domain: {bq.domain}"


class TestBenchmarkQueryDataclass:
    """Test BenchmarkQuery defaults and fields."""

    def test_default_min_chunks(self) -> None:
        bq = BenchmarkQuery(domain="test", query="test query")
        assert bq.min_chunks == 1

    def test_default_expected_keywords(self) -> None:
        bq = BenchmarkQuery(domain="test", query="test query")
        assert bq.expected_keywords == []

    def test_default_description(self) -> None:
        bq = BenchmarkQuery(domain="test", query="test query")
        assert bq.description == ""


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

    def test_custom_query_with_no_keywords(self) -> None:
        """Query with empty expected_keywords should pass if chunks found."""
        custom = [
            BenchmarkQuery(
                domain="security",
                query="security best practices",
                expected_keywords=[],
            ),
        ]
        report = run_retrieval_eval(queries=custom)
        assert report.total_queries == 1
        # With no expected keywords, keyword_coverage defaults to 1.0
        if report.results:
            assert report.results[0].keyword_total == 0


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

    def test_all_gates_fail(self) -> None:
        """All three quality gates fail at once."""
        report = EvalReport(
            total_queries=10,
            passed_queries=1,
            pass_rate=0.1,
            avg_latency_ms=600.0,
            p95_latency_ms=1000.0,
            avg_keyword_coverage=0.1,
        )
        passed, violations = check_quality_gates(report)
        assert not passed
        assert len(violations) == 3

    def test_boundary_pass_rate_exact(self) -> None:
        """Pass rate exactly at threshold → passes."""
        report = EvalReport(
            total_queries=10,
            passed_queries=6,
            pass_rate=QUALITY_GATE_PASS_RATE,
            avg_latency_ms=50.0,
            p95_latency_ms=100.0,
            avg_keyword_coverage=0.5,
        )
        passed, violations = check_quality_gates(report)
        assert passed

    def test_boundary_latency_exact(self) -> None:
        """p95 latency exactly at threshold → passes (not greater than)."""
        report = EvalReport(
            total_queries=10,
            passed_queries=8,
            pass_rate=0.8,
            avg_latency_ms=100.0,
            p95_latency_ms=QUALITY_GATE_P95_LATENCY_MS,
            avg_keyword_coverage=0.5,
        )
        passed, violations = check_quality_gates(report)
        assert passed

    def test_boundary_coverage_exact(self) -> None:
        """Keyword coverage exactly at threshold → passes."""
        report = EvalReport(
            total_queries=10,
            passed_queries=8,
            pass_rate=0.8,
            avg_latency_ms=50.0,
            p95_latency_ms=100.0,
            avg_keyword_coverage=QUALITY_GATE_MIN_KEYWORD_COVERAGE,
        )
        passed, violations = check_quality_gates(report)
        assert passed

    @pytest.mark.integration
    def test_real_eval_passes_gates(self) -> None:
        """The real benchmark suite should pass quality gates."""
        report = run_retrieval_eval()
        passed, violations = check_quality_gates(report)
        assert passed, f"Quality gate failures: {violations}"


class TestEvalReport:
    """Test EvalReport data structure."""

    def test_default_values(self) -> None:
        report = EvalReport()
        assert report.total_queries == 0
        assert report.passed_queries == 0
        assert report.pass_rate == 0.0
        assert report.failures == []

    def test_to_dict_rounds_values(self) -> None:
        report = EvalReport(
            pass_rate=0.33333,
            avg_latency_ms=123.456789,
            p95_latency_ms=456.789,
            avg_top_score=0.88888,
            avg_keyword_coverage=0.77777,
            fallback_rate=0.11111,
        )
        d = report.to_dict()
        assert d["pass_rate"] == 0.3333
        assert d["avg_latency_ms"] == 123.46
        assert d["p95_latency_ms"] == 456.79
        assert d["avg_top_score"] == 0.8889
        assert d["avg_keyword_coverage"] == 0.7778

    def test_to_dict_includes_failures(self) -> None:
        report = EvalReport(failures=["Failure 1", "Failure 2"])
        d = report.to_dict()
        assert len(d["failures"]) == 2


class TestQueryResult:
    """Test QueryResult data structure."""

    def test_default_values(self) -> None:
        bq = BenchmarkQuery(domain="test", query="test query")
        qr = QueryResult(query=bq)
        assert qr.chunks_found == 0
        assert qr.top_score == 0.0
        assert qr.passed is False
        assert qr.backend_type == "unknown"

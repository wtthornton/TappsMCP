"""Unit tests for tapps_core.experts.retrieval_eval — evaluation harness."""

from __future__ import annotations

import pytest

from tapps_core.experts.retrieval_eval import (
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

    def test_has_enough_queries(self) -> None:
        assert len(BENCHMARK_QUERIES) >= 8

    def test_all_queries_valid(self) -> None:
        """Each query has domain, keywords, and valid min_chunks."""
        from tapps_core.experts.registry import ExpertRegistry

        valid_domains = {e.primary_domain for e in ExpertRegistry.get_all_experts()}
        for bq in BENCHMARK_QUERIES:
            assert bq.domain, f"Missing domain: {bq.query}"
            assert bq.domain in valid_domains, f"Invalid domain: {bq.domain}"
            assert len(bq.expected_keywords) > 0, f"Missing keywords: {bq.query}"
            assert bq.min_chunks >= 1, f"Invalid min_chunks: {bq.query}"


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
        assert report.p95_latency_ms < 2000.0

    def test_report_to_dict(self) -> None:
        report = run_retrieval_eval()
        d = report.to_dict()
        assert all(k in d for k in ("pass_rate", "avg_latency_ms", "failures"))

    def test_custom_queries(self) -> None:
        custom = [
            BenchmarkQuery(
                domain="security",
                query="SQL injection prevention",
                expected_keywords=["sql", "injection"],
            )
        ]
        report = run_retrieval_eval(queries=custom)
        assert report.total_queries == 1

    def test_custom_query_with_no_keywords(self) -> None:
        custom = [
            BenchmarkQuery(domain="security", query="security best practices", expected_keywords=[])
        ]
        report = run_retrieval_eval(queries=custom)
        if report.results:
            assert report.results[0].keyword_total == 0


class TestQualityGates:
    """Test quality gate checking."""

    def _report(self, **overrides) -> EvalReport:
        """Create a passing EvalReport with optional overrides."""
        defaults = {
            "total_queries": 10,
            "passed_queries": 8,
            "pass_rate": 0.8,
            "avg_latency_ms": 50.0,
            "p95_latency_ms": 100.0,
            "avg_keyword_coverage": 0.6,
        }
        defaults.update(overrides)
        return EvalReport(**defaults)

    def test_passing_report(self) -> None:
        passed, violations = check_quality_gates(self._report())
        assert passed and violations == []

    @pytest.mark.parametrize(
        "field,value,violation_keyword",
        [
            ("pass_rate", 0.3, "Pass rate"),
            ("p95_latency_ms", 600.0, "latency"),
            ("avg_keyword_coverage", 0.1, "keyword"),
        ],
        ids=["pass-rate", "latency", "keyword-coverage"],
    )
    def test_individual_gate_failure(self, field, value, violation_keyword) -> None:
        passed, violations = check_quality_gates(self._report(**{field: value}))
        assert not passed
        assert any(violation_keyword.lower() in v.lower() for v in violations)

    def test_all_gates_fail(self) -> None:
        report = self._report(pass_rate=0.1, p95_latency_ms=1000.0, avg_keyword_coverage=0.1)
        passed, violations = check_quality_gates(report)
        assert not passed and len(violations) == 3

    @pytest.mark.parametrize(
        "field,value",
        [
            ("pass_rate", QUALITY_GATE_PASS_RATE),
            ("p95_latency_ms", QUALITY_GATE_P95_LATENCY_MS),
            ("avg_keyword_coverage", QUALITY_GATE_MIN_KEYWORD_COVERAGE),
        ],
        ids=["pass-rate-boundary", "latency-boundary", "coverage-boundary"],
    )
    def test_boundary_values_pass(self, field, value) -> None:
        """Exact threshold values should pass (not fail)."""
        passed, _ = check_quality_gates(self._report(**{field: value}))
        assert passed

    @pytest.mark.integration
    def test_real_eval_passes_gates(self) -> None:
        report = run_retrieval_eval()
        passed, violations = check_quality_gates(report)
        assert passed, f"Quality gate failures: {violations}"


class TestEvalReportDataclass:
    def test_default_values(self) -> None:
        report = EvalReport()
        assert report.total_queries == 0 and report.pass_rate == 0.0 and report.failures == []

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
        assert d["avg_top_score"] == 0.8889


class TestQueryResultDataclass:
    def test_default_values(self) -> None:
        qr = QueryResult(query=BenchmarkQuery(domain="test", query="test query"))
        assert qr.chunks_found == 0 and qr.passed is False and qr.backend_type == "unknown"

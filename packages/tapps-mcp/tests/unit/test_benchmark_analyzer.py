"""Unit tests for benchmark analyzer and reporter (Epic 30, Story 5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.benchmark.analyzer import ResultsAnalyzer, _extract_repo
from tapps_mcp.benchmark.models import (
    BenchmarkResult,
    ComparisonReport,
    ContextMode,
)
from tapps_mcp.benchmark.reporter import ReportGenerator, ResultsPersistence

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(
    instance_id: str = "org__repo__001",
    *,
    resolved: bool = True,
    token_usage: int = 10000,
    inference_cost: float = 0.30,
    steps: int = 8,
    duration_ms: int = 60000,
    context_mode: ContextMode = ContextMode.NONE,
    engagement_level: str = "medium",
) -> BenchmarkResult:
    """Build a ``BenchmarkResult`` with sensible defaults."""
    return BenchmarkResult(
        instance_id=instance_id,
        context_mode=context_mode,
        engagement_level=engagement_level,
        resolved=resolved,
        token_usage=token_usage,
        inference_cost=inference_cost,
        steps=steps,
        duration_ms=duration_ms,
    )


# ---------------------------------------------------------------------------
# _extract_repo helper
# ---------------------------------------------------------------------------


class TestExtractRepo:
    """Tests for the _extract_repo utility."""

    def test_double_underscore(self) -> None:
        assert _extract_repo("owner__repo__42") == "owner/repo"

    def test_slash_convention(self) -> None:
        assert _extract_repo("owner/repo-42") == "owner/repo"

    def test_slash_no_hyphen(self) -> None:
        assert _extract_repo("owner/repo") == "owner/repo"

    def test_unknown_fallback(self) -> None:
        assert _extract_repo("plain-id") == "unknown"


# ---------------------------------------------------------------------------
# ResultsAnalyzer.aggregate
# ---------------------------------------------------------------------------


class TestAggregate:
    """Tests for ResultsAnalyzer.aggregate."""

    def test_aggregate_basic(self) -> None:
        results = [
            _make_result("org__repo__1", resolved=True, token_usage=9000),
            _make_result("org__repo__2", resolved=False, token_usage=12000),
            _make_result("org__repo__3", resolved=True, token_usage=9000),
        ]
        analyzer = ResultsAnalyzer()
        summary = analyzer.aggregate(results)

        assert summary.total_instances == 3
        assert summary.resolved_count == 2
        assert summary.avg_tokens == pytest.approx(10000.0)
        assert summary.avg_cost == pytest.approx(0.30)
        assert summary.avg_steps == pytest.approx(8.0)
        assert summary.resolution_rate == pytest.approx(2 / 3)

    def test_aggregate_empty(self) -> None:
        analyzer = ResultsAnalyzer()
        summary = analyzer.aggregate([])

        assert summary.total_instances == 0
        assert summary.resolved_count == 0
        assert summary.avg_tokens == 0.0
        assert summary.avg_cost == 0.0
        assert summary.avg_steps == 0.0
        assert summary.resolution_rate == 0.0

    def test_aggregate_per_repo_breakdown(self) -> None:
        results = [
            _make_result("alpha__core__1", resolved=True),
            _make_result("alpha__core__2", resolved=False),
            _make_result("beta__lib__1", resolved=True),
        ]
        analyzer = ResultsAnalyzer()
        summary = analyzer.aggregate(results)

        assert len(summary.per_repo_breakdown) == 2
        assert summary.per_repo_breakdown["alpha/core"].total == 2
        assert summary.per_repo_breakdown["alpha/core"].resolved == 1
        assert summary.per_repo_breakdown["alpha/core"].resolution_rate == pytest.approx(0.5)
        assert summary.per_repo_breakdown["beta/lib"].total == 1
        assert summary.per_repo_breakdown["beta/lib"].resolved == 1

    def test_aggregate_all_resolved(self) -> None:
        results = [_make_result(f"org__repo__{i}", resolved=True) for i in range(5)]
        analyzer = ResultsAnalyzer()
        summary = analyzer.aggregate(results)

        assert summary.total_instances == 5
        assert summary.resolved_count == 5
        assert summary.resolution_rate == pytest.approx(1.0)

    def test_aggregate_none_resolved(self) -> None:
        results = [_make_result(f"org__repo__{i}", resolved=False) for i in range(4)]
        analyzer = ResultsAnalyzer()
        summary = analyzer.aggregate(results)

        assert summary.total_instances == 4
        assert summary.resolved_count == 0
        assert summary.resolution_rate == pytest.approx(0.0)

    def test_aggregate_context_mode_from_first_result(self) -> None:
        results = [
            _make_result("x__y__1", context_mode=ContextMode.TAPPS),
            _make_result("x__y__2", context_mode=ContextMode.TAPPS),
        ]
        analyzer = ResultsAnalyzer()
        summary = analyzer.aggregate(results)

        assert summary.context_mode is ContextMode.TAPPS
        assert summary.engagement_level == "medium"


# ---------------------------------------------------------------------------
# ResultsAnalyzer.compare_conditions
# ---------------------------------------------------------------------------


class TestCompareConditions:
    """Tests for ResultsAnalyzer.compare_conditions."""

    def test_positive_delta(self) -> None:
        baseline = [
            _make_result("org__repo__1", resolved=False),
            _make_result("org__repo__2", resolved=False),
            _make_result("org__repo__3", resolved=True),
        ]
        treatment = [
            _make_result(
                "org__repo__1",
                resolved=True,
                context_mode=ContextMode.TAPPS,
            ),
            _make_result(
                "org__repo__2",
                resolved=True,
                context_mode=ContextMode.TAPPS,
            ),
            _make_result(
                "org__repo__3",
                resolved=True,
                context_mode=ContextMode.TAPPS,
            ),
        ]
        analyzer = ResultsAnalyzer()
        report = analyzer.compare_conditions(baseline, treatment)

        # Baseline: 1/3, Treatment: 3/3 -> delta = +2/3
        assert report.resolution_delta == pytest.approx(2 / 3)
        assert report.treatment.resolution_rate == pytest.approx(1.0)
        assert report.baseline.resolution_rate == pytest.approx(1 / 3)

    def test_negative_delta(self) -> None:
        baseline = [
            _make_result("org__repo__1", resolved=True),
            _make_result("org__repo__2", resolved=True),
        ]
        treatment = [
            _make_result(
                "org__repo__1",
                resolved=False,
                context_mode=ContextMode.TAPPS,
            ),
            _make_result(
                "org__repo__2",
                resolved=False,
                context_mode=ContextMode.TAPPS,
            ),
        ]
        analyzer = ResultsAnalyzer()
        report = analyzer.compare_conditions(baseline, treatment)

        assert report.resolution_delta == pytest.approx(-1.0)

    def test_zero_delta(self) -> None:
        baseline = [
            _make_result("org__repo__1", resolved=True),
            _make_result("org__repo__2", resolved=False),
        ]
        treatment = [
            _make_result(
                "org__repo__1",
                resolved=True,
                context_mode=ContextMode.TAPPS,
            ),
            _make_result(
                "org__repo__2",
                resolved=False,
                context_mode=ContextMode.TAPPS,
            ),
        ]
        analyzer = ResultsAnalyzer()
        report = analyzer.compare_conditions(baseline, treatment)

        assert report.resolution_delta == pytest.approx(0.0)

    def test_mcnemar_significant(self) -> None:
        """Large asymmetric improvement should be significant."""
        # 15 instances resolved only in treatment, 1 only in baseline
        baseline_results: list[BenchmarkResult] = []
        treatment_results: list[BenchmarkResult] = []
        for i in range(20):
            iid = f"org__repo__{i}"
            if i < 15:
                # Resolved in treatment only
                baseline_results.append(_make_result(iid, resolved=False))
                treatment_results.append(
                    _make_result(iid, resolved=True, context_mode=ContextMode.TAPPS)
                )
            elif i == 15:
                # Resolved in baseline only
                baseline_results.append(_make_result(iid, resolved=True))
                treatment_results.append(
                    _make_result(iid, resolved=False, context_mode=ContextMode.TAPPS)
                )
            else:
                # Both resolved
                baseline_results.append(_make_result(iid, resolved=True))
                treatment_results.append(
                    _make_result(iid, resolved=True, context_mode=ContextMode.TAPPS)
                )

        analyzer = ResultsAnalyzer()
        report = analyzer.compare_conditions(baseline_results, treatment_results)

        assert report.statistically_significant is True
        assert report.p_value is not None
        assert report.p_value < 0.05

    def test_mcnemar_not_significant(self) -> None:
        """Small symmetric difference should not be significant."""
        baseline = [
            _make_result("org__repo__1", resolved=True),
            _make_result("org__repo__2", resolved=False),
            _make_result("org__repo__3", resolved=True),
            _make_result("org__repo__4", resolved=False),
        ]
        treatment = [
            _make_result(
                "org__repo__1",
                resolved=False,
                context_mode=ContextMode.TAPPS,
            ),
            _make_result(
                "org__repo__2",
                resolved=True,
                context_mode=ContextMode.TAPPS,
            ),
            _make_result(
                "org__repo__3",
                resolved=True,
                context_mode=ContextMode.TAPPS,
            ),
            _make_result(
                "org__repo__4",
                resolved=False,
                context_mode=ContextMode.TAPPS,
            ),
        ]
        analyzer = ResultsAnalyzer()
        report = analyzer.compare_conditions(baseline, treatment)

        assert report.statistically_significant is False

    def test_per_repo_deltas(self) -> None:
        baseline = [
            _make_result("alpha__core__1", resolved=True),
            _make_result("alpha__core__2", resolved=False),
            _make_result("beta__lib__1", resolved=False),
        ]
        treatment = [
            _make_result(
                "alpha__core__1",
                resolved=True,
                context_mode=ContextMode.TAPPS,
            ),
            _make_result(
                "alpha__core__2",
                resolved=True,
                context_mode=ContextMode.TAPPS,
            ),
            _make_result(
                "beta__lib__1",
                resolved=True,
                context_mode=ContextMode.TAPPS,
            ),
        ]
        analyzer = ResultsAnalyzer()
        report = analyzer.compare_conditions(baseline, treatment)

        assert "alpha/core" in report.per_repo_deltas
        assert "beta/lib" in report.per_repo_deltas
        # alpha/core: 0.5 -> 1.0 = +0.5
        assert report.per_repo_deltas["alpha/core"] == pytest.approx(0.5)
        # beta/lib: 0.0 -> 1.0 = +1.0
        assert report.per_repo_deltas["beta/lib"] == pytest.approx(1.0)

    def test_token_and_cost_deltas(self) -> None:
        baseline = [
            _make_result(
                "org__repo__1",
                token_usage=10000,
                inference_cost=0.30,
            ),
        ]
        treatment = [
            _make_result(
                "org__repo__1",
                token_usage=15000,
                inference_cost=0.45,
                context_mode=ContextMode.TAPPS,
            ),
        ]
        analyzer = ResultsAnalyzer()
        report = analyzer.compare_conditions(baseline, treatment)

        assert report.token_delta == pytest.approx(5000.0)
        assert report.cost_delta == pytest.approx(0.15)


# ---------------------------------------------------------------------------
# ResultsAnalyzer.compare_engagement_levels
# ---------------------------------------------------------------------------


class TestCompareEngagement:
    """Tests for ResultsAnalyzer.compare_engagement_levels."""

    def test_recommends_most_efficient_level(self) -> None:
        results_by_level = {
            "high": [
                _make_result(
                    f"org__repo__{i}",
                    resolved=(i < 8),
                    inference_cost=0.50,
                    engagement_level="high",
                )
                for i in range(10)
            ],
            "medium": [
                _make_result(
                    f"org__repo__{i}",
                    resolved=(i < 7),
                    inference_cost=0.20,
                    engagement_level="medium",
                )
                for i in range(10)
            ],
            "low": [
                _make_result(
                    f"org__repo__{i}",
                    resolved=(i < 3),
                    inference_cost=0.10,
                    engagement_level="low",
                )
                for i in range(10)
            ],
        }
        analyzer = ResultsAnalyzer()
        report = analyzer.compare_engagement_levels(results_by_level)

        # medium: 0.7/0.20 = 3.5, high: 0.8/0.50 = 1.6, low: 0.3/0.10 = 3.0
        assert report.recommended_level == "medium"
        assert "efficiency" in report.recommendation_reason.lower()
        assert len(report.results_by_level) == 3

    def test_single_level(self) -> None:
        results_by_level = {
            "high": [
                _make_result("org__repo__1", engagement_level="high"),
            ],
        }
        analyzer = ResultsAnalyzer()
        report = analyzer.compare_engagement_levels(results_by_level)

        assert report.recommended_level == "high"
        assert "only level" in report.recommendation_reason.lower()

    def test_zero_cost_prefers_higher_rate(self) -> None:
        results_by_level = {
            "high": [
                _make_result(
                    "org__repo__1",
                    resolved=True,
                    inference_cost=0.0,
                    engagement_level="high",
                ),
                _make_result(
                    "org__repo__2",
                    resolved=True,
                    inference_cost=0.0,
                    engagement_level="high",
                ),
            ],
            "low": [
                _make_result(
                    "org__repo__1",
                    resolved=True,
                    inference_cost=0.0,
                    engagement_level="low",
                ),
                _make_result(
                    "org__repo__2",
                    resolved=False,
                    inference_cost=0.0,
                    engagement_level="low",
                ),
            ],
        }
        analyzer = ResultsAnalyzer()
        report = analyzer.compare_engagement_levels(results_by_level)

        # Both free, but high has 100% vs low 50%
        assert report.recommended_level == "high"


# ---------------------------------------------------------------------------
# ResultsPersistence
# ---------------------------------------------------------------------------


class TestResultsPersistence:
    """Tests for ResultsPersistence save/load/list."""

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        persistence = ResultsPersistence(tmp_path)
        original = [
            _make_result("org__repo__1", resolved=True, token_usage=5000),
            _make_result("org__repo__2", resolved=False, token_usage=8000),
        ]
        run_dir = persistence.save_results(original, "run-001")

        assert run_dir.exists()
        assert (run_dir / "results.jsonl").exists()
        assert (run_dir / "summary.csv").exists()
        assert (run_dir / "metadata.json").exists()

        loaded = persistence.load_results("run-001")
        assert len(loaded) == 2
        assert loaded[0].instance_id == "org__repo__1"
        assert loaded[0].resolved is True
        assert loaded[0].token_usage == 5000
        assert loaded[1].instance_id == "org__repo__2"
        assert loaded[1].resolved is False

    def test_list_runs(self, tmp_path: Path) -> None:
        persistence = ResultsPersistence(tmp_path)

        r1 = [_make_result("org__repo__1")]
        r2 = [_make_result("org__repo__1"), _make_result("org__repo__2")]

        persistence.save_results(r1, "run-alpha")
        persistence.save_results(r2, "run-beta")

        runs = persistence.list_runs()
        assert len(runs) == 2
        run_ids = {m.run_id for m in runs}
        assert run_ids == {"run-alpha", "run-beta"}

    def test_load_nonexistent_raises(self, tmp_path: Path) -> None:
        persistence = ResultsPersistence(tmp_path)
        with pytest.raises(FileNotFoundError, match="not found"):
            persistence.load_results("does-not-exist")

    def test_list_runs_empty_dir(self, tmp_path: Path) -> None:
        persistence = ResultsPersistence(tmp_path)
        runs = persistence.list_runs()
        assert runs == []

    def test_csv_has_rows(self, tmp_path: Path) -> None:
        persistence = ResultsPersistence(tmp_path)
        results = [
            _make_result("org__repo__1"),
            _make_result("org__repo__2"),
        ]
        run_dir = persistence.save_results(results, "run-csv")
        csv_content = (run_dir / "summary.csv").read_text(encoding="utf-8")
        lines = csv_content.strip().split("\n")
        assert len(lines) == 3  # header + 2 rows
        assert "instance_id" in lines[0]


# ---------------------------------------------------------------------------
# ReportGenerator
# ---------------------------------------------------------------------------


class TestReportGenerator:
    """Tests for ReportGenerator."""

    @pytest.fixture()
    def sample_comparison(self) -> ComparisonReport:
        """Build a comparison report for testing."""
        analyzer = ResultsAnalyzer()
        baseline = [
            _make_result("alpha__core__1", resolved=True),
            _make_result("alpha__core__2", resolved=False),
            _make_result("beta__lib__1", resolved=False),
        ]
        treatment = [
            _make_result(
                "alpha__core__1",
                resolved=True,
                context_mode=ContextMode.TAPPS,
            ),
            _make_result(
                "alpha__core__2",
                resolved=True,
                context_mode=ContextMode.TAPPS,
            ),
            _make_result(
                "beta__lib__1",
                resolved=True,
                context_mode=ContextMode.TAPPS,
            ),
        ]
        return analyzer.compare_conditions(baseline, treatment)

    def test_markdown_report_has_sections(
        self,
        sample_comparison: ComparisonReport,
    ) -> None:
        gen = ReportGenerator()
        md = gen.generate_markdown(sample_comparison)

        assert "# Benchmark Comparison Report" in md
        assert "## Summary" in md
        assert "## Resolution Rates" in md
        assert "## Token & Cost Comparison" in md
        assert "## Per-Repository Breakdown" in md
        assert "## Statistical Significance" in md

    def test_markdown_contains_data(
        self,
        sample_comparison: ComparisonReport,
    ) -> None:
        gen = ReportGenerator()
        md = gen.generate_markdown(sample_comparison)

        assert "Baseline" in md
        assert "Treatment" in md
        assert "Delta" in md

    def test_csv_has_header_and_rows(self) -> None:
        results = [
            _make_result("org__repo__1", resolved=True, token_usage=5000),
            _make_result("org__repo__2", resolved=False, token_usage=8000),
            _make_result("org__repo__3", resolved=True, token_usage=6000),
        ]
        gen = ReportGenerator()
        csv_str = gen.generate_csv(results)
        lines = csv_str.strip().split("\n")

        assert len(lines) == 4  # 1 header + 3 data rows
        header = lines[0]
        assert "instance_id" in header
        assert "context_mode" in header
        assert "resolved" in header
        assert "token_usage" in header
        assert "inference_cost" in header
        assert "steps" in header
        assert "duration_ms" in header

    def test_csv_empty_results(self) -> None:
        gen = ReportGenerator()
        csv_str = gen.generate_csv([])
        lines = csv_str.strip().split("\n")
        assert len(lines) == 1  # header only

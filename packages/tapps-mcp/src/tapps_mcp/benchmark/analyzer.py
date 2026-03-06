"""Results aggregation and comparison for benchmark runs.

Provides ``ResultsAnalyzer`` which aggregates raw
``BenchmarkResult`` lists into summaries, computes condition deltas,
runs McNemar's test for statistical significance, and compares
engagement levels.
"""

from __future__ import annotations

import math
from collections import defaultdict

import structlog

from tapps_mcp.benchmark.models import (
    BenchmarkResult,
    BenchmarkSummary,
    ComparisonReport,
    ContextMode,
    EngagementReport,
    RepoBreakdown,
)

__all__ = ["ResultsAnalyzer"]

logger = structlog.get_logger(__name__)

# Minimum parts from split("__") to identify owner/repo.
_MIN_REPO_PARTS = 2

# McNemar's test requires at least 2 paired instances.
_MIN_PAIRED_INSTANCES = 2

# Significance threshold (alpha) for McNemar's test.
_SIGNIFICANCE_ALPHA = 0.05


# ---------------------------------------------------------------------------
# Chi-squared survival function (p-value) for df=1
# ---------------------------------------------------------------------------

# Pre-computed critical values for chi2 df=1 so we avoid scipy.
# Maps chi2 threshold -> p-value (right tail).
_CHI2_TABLE: list[tuple[float, float]] = [
    (10.828, 0.001),
    (7.879, 0.005),
    (6.635, 0.01),
    (5.024, 0.025),
    (3.841, 0.05),
    (2.706, 0.10),
    (1.642, 0.20),
    (0.455, 0.50),
]


def _chi2_sf_df1(chi2: float) -> float:
    """Approximate the survival function (1 - CDF) for chi-squared df=1.

    Uses the incomplete gamma function relationship:
        p = erfc(sqrt(chi2 / 2))

    This is exact for df=1.  Falls back to the lookup table when
    ``math.erfc`` is not available (should not happen on CPython 3.12+).
    """
    if chi2 <= 0.0:
        return 1.0
    try:
        return math.erfc(math.sqrt(chi2 / 2.0))
    except (ValueError, OverflowError):
        # Fallback: interpolate from the lookup table.
        for threshold, p_val in _CHI2_TABLE:
            if chi2 >= threshold:
                return p_val
        return 1.0


# ---------------------------------------------------------------------------
# Repo extraction from instance_id
# ---------------------------------------------------------------------------


def _extract_repo(instance_id: str) -> str:
    """Extract repository name from an instance_id.

    Supports common conventions:
    - ``org__repo__number``  (SWE-bench / AGENTBench double-underscore)
    - ``org/repo-number``    (slash-separated with trailing id)

    Returns ``"unknown"`` when no repo can be extracted.
    """
    # Double-underscore convention: "owner__repo__42"
    parts = instance_id.split("__")
    if len(parts) >= _MIN_REPO_PARTS:
        return f"{parts[0]}/{parts[1]}"

    # Slash convention: "owner/repo-42"
    if "/" in instance_id:
        # Take everything up to the last hyphen after the slash
        slash_idx = instance_id.index("/")
        after_slash = instance_id[slash_idx + 1 :]
        last_hyphen = after_slash.rfind("-")
        if last_hyphen >= 0:
            repo_part = after_slash[:last_hyphen]
            return f"{instance_id[:slash_idx]}/{repo_part}"
        return instance_id  # Already looks like owner/repo

    return "unknown"


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class ResultsAnalyzer:
    """Aggregate, compare, and analyze benchmark results."""

    def aggregate(
        self,
        results: list[BenchmarkResult],
    ) -> BenchmarkSummary:
        """Aggregate a list of results into a summary.

        Computes totals, averages, and per-repo breakdowns.  The
        ``context_mode`` and ``engagement_level`` are taken from the
        first result (all results in a run should share these).

        Args:
            results: Individual benchmark results to aggregate.

        Returns:
            Aggregated ``BenchmarkSummary``.
        """
        total = len(results)
        if total == 0:
            return BenchmarkSummary(
                total_instances=0,
                resolved_count=0,
                avg_tokens=0.0,
                avg_cost=0.0,
                avg_steps=0.0,
                context_mode=ContextMode.NONE,
                engagement_level="medium",
            )

        resolved_count = sum(1 for r in results if r.resolved)
        avg_tokens = sum(r.token_usage for r in results) / total
        avg_cost = sum(r.inference_cost for r in results) / total
        avg_steps = sum(r.steps for r in results) / total

        # Per-repo breakdown
        repo_totals: dict[str, int] = defaultdict(int)
        repo_resolved: dict[str, int] = defaultdict(int)
        for r in results:
            repo = _extract_repo(r.instance_id)
            repo_totals[repo] += 1
            if r.resolved:
                repo_resolved[repo] += 1

        per_repo: dict[str, RepoBreakdown] = {}
        for repo, count in sorted(repo_totals.items()):
            per_repo[repo] = RepoBreakdown(
                repo=repo,
                total=count,
                resolved=repo_resolved.get(repo, 0),
            )

        context_mode = results[0].context_mode
        engagement_level = results[0].engagement_level

        logger.debug(
            "benchmark_aggregate",
            total=total,
            resolved=resolved_count,
            repos=len(per_repo),
        )

        return BenchmarkSummary(
            total_instances=total,
            resolved_count=resolved_count,
            avg_tokens=avg_tokens,
            avg_cost=avg_cost,
            avg_steps=avg_steps,
            per_repo_breakdown=per_repo,
            context_mode=context_mode,
            engagement_level=engagement_level,
        )

    def compare_conditions(
        self,
        baseline: list[BenchmarkResult],
        treatment: list[BenchmarkResult],
    ) -> ComparisonReport:
        """Compare baseline vs treatment benchmark runs.

        Computes resolution, token, and cost deltas.  Runs McNemar's
        test on paired binary outcomes for statistical significance.

        Both lists must cover the same set of instance_ids for the
        McNemar test to be meaningful.

        Args:
            baseline: Results from the baseline (control) run.
            treatment: Results from the treatment (experimental) run.

        Returns:
            ``ComparisonReport`` with deltas and significance info.
        """
        baseline_summary = self.aggregate(baseline)
        treatment_summary = self.aggregate(treatment)

        resolution_delta = treatment_summary.resolution_rate - baseline_summary.resolution_rate
        token_delta = treatment_summary.avg_tokens - baseline_summary.avg_tokens
        cost_delta = treatment_summary.avg_cost - baseline_summary.avg_cost

        # Per-repo deltas
        all_repos = set(baseline_summary.per_repo_breakdown.keys()) | set(
            treatment_summary.per_repo_breakdown.keys()
        )
        per_repo_deltas: dict[str, float] = {}
        for repo in sorted(all_repos):
            baseline_rate = (
                baseline_summary.per_repo_breakdown[repo].resolution_rate
                if repo in baseline_summary.per_repo_breakdown
                else 0.0
            )
            treatment_rate = (
                treatment_summary.per_repo_breakdown[repo].resolution_rate
                if repo in treatment_summary.per_repo_breakdown
                else 0.0
            )
            per_repo_deltas[repo] = treatment_rate - baseline_rate

        # McNemar's test on paired binary outcomes
        p_value, significant = self._mcnemar_test(baseline, treatment)

        logger.debug(
            "benchmark_compare",
            resolution_delta=round(resolution_delta, 4),
            token_delta=round(token_delta, 1),
            p_value=round(p_value, 4) if p_value is not None else None,
            significant=significant,
        )

        return ComparisonReport(
            baseline=baseline_summary,
            treatment=treatment_summary,
            resolution_delta=resolution_delta,
            token_delta=token_delta,
            cost_delta=cost_delta,
            per_repo_deltas=per_repo_deltas,
            statistically_significant=significant,
            p_value=p_value,
        )

    def compare_engagement_levels(
        self,
        results_by_level: dict[str, list[BenchmarkResult]],
    ) -> EngagementReport:
        """Compare results across engagement levels.

        Aggregates each level's results, then recommends the level
        with the best resolution_rate / avg_cost ratio (efficiency).
        When cost is zero, resolution rate alone determines the
        winner.

        Args:
            results_by_level: Mapping of engagement level name to
                results for that level.

        Returns:
            ``EngagementReport`` with per-level summaries and a
            recommendation.
        """
        summaries: dict[str, BenchmarkSummary] = {}
        for level, results in results_by_level.items():
            summaries[level] = self.aggregate(results)

        # Find the most efficient level (best resolution / cost ratio).
        best_level = ""
        best_efficiency = -1.0
        best_rate = -1.0
        for level, summary in summaries.items():
            rate = summary.resolution_rate
            cost = summary.avg_cost
            # Efficiency: resolution_rate / cost. When cost is 0, use
            # rate * a large multiplier so free+effective wins.
            efficiency = rate / cost if cost > 0 else rate * 1e6
            if efficiency > best_efficiency or (efficiency == best_efficiency and rate > best_rate):
                best_efficiency = efficiency
                best_rate = rate
                best_level = level

        # Build recommendation reason
        if len(summaries) == 1:
            reason = f"Only level tested ({best_level})."
        else:
            best_summary = summaries[best_level]
            rate_pct = best_summary.resolution_rate * 100
            cost_str = f"${best_summary.avg_cost:.2f}"
            reason = (
                f"Best efficiency: {rate_pct:.1f}% resolution rate "
                f"at {cost_str} avg cost per instance."
            )

        logger.debug(
            "benchmark_engagement_comparison",
            levels=list(summaries.keys()),
            recommended=best_level,
        )

        return EngagementReport(
            results_by_level=summaries,
            recommended_level=best_level,
            recommendation_reason=reason,
        )

    @staticmethod
    def _mcnemar_test(
        baseline: list[BenchmarkResult],
        treatment: list[BenchmarkResult],
    ) -> tuple[float | None, bool | None]:
        """Run McNemar's test on paired binary outcomes.

        Pairs results by ``instance_id``.  Counts discordant pairs:
        - b = resolved in treatment but not baseline
        - c = resolved in baseline but not treatment

        Chi-square = (|b - c| - 1)^2 / (b + c)  if b + c > 0.

        Returns:
            Tuple of (p_value, is_significant).  Both ``None``
            when there are no discordant pairs or fewer than 2
            paired instances.
        """
        baseline_map = {r.instance_id: r.resolved for r in baseline}
        treatment_map = {r.instance_id: r.resolved for r in treatment}

        common_ids = set(baseline_map.keys()) & set(treatment_map.keys())
        if len(common_ids) < _MIN_PAIRED_INSTANCES:
            return None, None

        b_count = 0  # Treatment resolved, baseline not
        c_count = 0  # Baseline resolved, treatment not
        for iid in common_ids:
            b_resolved = baseline_map[iid]
            t_resolved = treatment_map[iid]
            if t_resolved and not b_resolved:
                b_count += 1
            elif b_resolved and not t_resolved:
                c_count += 1

        bc_sum = b_count + c_count
        if bc_sum == 0:
            return 1.0, False

        # McNemar chi-square with continuity correction
        chi2 = (abs(b_count - c_count) - 1) ** 2 / bc_sum
        p_value = _chi2_sf_df1(chi2)
        significant = p_value < _SIGNIFICANCE_ALPHA

        return p_value, significant

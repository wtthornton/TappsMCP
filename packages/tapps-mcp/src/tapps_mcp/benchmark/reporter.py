"""Persistence and reporting for benchmark results.

``ResultsPersistence`` saves and loads benchmark run data (JSONL results,
CSV summary, JSON metadata).  ``ReportGenerator`` produces human-readable
Markdown and CSV reports from comparison and result data.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from tapps_mcp.benchmark.models import (
    BenchmarkConfig,
    BenchmarkResult,
    ComparisonReport,
    RunMetadata,
)

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["ReportGenerator", "ResultsPersistence"]

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Results persistence
# ---------------------------------------------------------------------------


class ResultsPersistence:
    """Save and load benchmark results to/from disk.

    Results are stored under ``{output_dir}/{run_id}/`` with three
    files: ``results.jsonl``, ``summary.csv``, and ``metadata.json``.
    """

    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def save_results(
        self,
        results: list[BenchmarkResult],
        run_id: str,
        config: BenchmarkConfig | None = None,
    ) -> Path:
        """Persist results, CSV summary, and metadata for a run.

        Args:
            results: List of benchmark results to save.
            run_id: Unique identifier for this run.
            config: Optional config to embed in metadata.

        Returns:
            Path to the run directory.
        """
        run_dir = self._output_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # Write JSONL
        jsonl_path = run_dir / "results.jsonl"
        with jsonl_path.open("w", encoding="utf-8") as f:
            for result in results:
                f.write(result.model_dump_json() + "\n")

        # Write summary CSV
        csv_path = run_dir / "summary.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "instance_id",
                    "context_mode",
                    "engagement_level",
                    "resolved",
                    "token_usage",
                    "inference_cost",
                    "steps",
                    "duration_ms",
                ]
            )
            for result in results:
                writer.writerow(
                    [
                        result.instance_id,
                        result.context_mode.value,
                        result.engagement_level,
                        result.resolved,
                        result.token_usage,
                        result.inference_cost,
                        result.steps,
                        result.duration_ms,
                    ]
                )

        # Write metadata
        effective_config = config or BenchmarkConfig()
        context_mode = results[0].context_mode if results else effective_config.context_mode
        metadata = RunMetadata(
            run_id=run_id,
            config=effective_config,
            instance_count=len(results),
            context_mode=context_mode,
        )
        meta_path = run_dir / "metadata.json"
        meta_path.write_text(
            metadata.model_dump_json(indent=2),
            encoding="utf-8",
        )

        logger.debug(
            "benchmark_results_saved",
            run_id=run_id,
            count=len(results),
            path=str(run_dir),
        )

        return run_dir

    def load_results(self, run_id: str) -> list[BenchmarkResult]:
        """Load results from a saved run.

        Args:
            run_id: Run identifier to load.

        Returns:
            List of ``BenchmarkResult`` parsed from JSONL.

        Raises:
            FileNotFoundError: If the run directory or JSONL file
                does not exist.
        """
        jsonl_path = self._output_dir / run_id / "results.jsonl"
        if not jsonl_path.exists():
            msg = f"Results file not found: {jsonl_path}"
            raise FileNotFoundError(msg)

        results: list[BenchmarkResult] = []
        with jsonl_path.open(encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    results.append(BenchmarkResult.model_validate_json(stripped))

        logger.debug(
            "benchmark_results_loaded",
            run_id=run_id,
            count=len(results),
        )

        return results

    def list_runs(self) -> list[RunMetadata]:
        """List all saved runs, sorted newest first.

        Scans the output directory for subdirectories containing
        ``metadata.json``.

        Returns:
            List of ``RunMetadata`` sorted by timestamp descending.
        """
        runs: list[RunMetadata] = []
        if not self._output_dir.exists():
            return runs

        for child in self._output_dir.iterdir():
            if not child.is_dir():
                continue
            meta_path = child / "metadata.json"
            if not meta_path.exists():
                continue
            try:
                raw = meta_path.read_text(encoding="utf-8")
                metadata = RunMetadata.model_validate_json(raw)
                runs.append(metadata)
            except Exception as exc:
                logger.debug(
                    "benchmark_metadata_parse_failed",
                    path=str(meta_path),
                    reason=str(exc),
                )

        # Sort by timestamp descending (newest first).
        runs.sort(key=lambda m: m.timestamp, reverse=True)
        return runs


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


class ReportGenerator:
    """Generate human-readable reports from benchmark data."""

    def generate_markdown(self, comparison: ComparisonReport) -> str:
        """Generate a Markdown comparison report.

        Includes header, summary, resolution rates, token/cost
        comparison, per-repo breakdown, and statistical significance.

        Args:
            comparison: Comparison report to render.

        Returns:
            Markdown-formatted string.
        """
        now = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
        baseline = comparison.baseline
        treatment = comparison.treatment

        lines: list[str] = [
            "# Benchmark Comparison Report",
            "",
            f"Generated: {now}",
            "",
            "## Summary",
            "",
            f"- **Baseline**: {baseline.context_mode.value} context, "
            f"{baseline.engagement_level} engagement",
            f"- **Treatment**: {treatment.context_mode.value} context, "
            f"{treatment.engagement_level} engagement",
            f"- **Instances**: {baseline.total_instances} baseline, "
            f"{treatment.total_instances} treatment",
            "",
            "## Resolution Rates",
            "",
            "| Condition | Resolved | Total | Rate |",
            "|-----------|----------|-------|------|",
            f"| Baseline  | {baseline.resolved_count} "
            f"| {baseline.total_instances} "
            f"| {baseline.resolution_rate:.1%} |",
            f"| Treatment | {treatment.resolved_count} "
            f"| {treatment.total_instances} "
            f"| {treatment.resolution_rate:.1%} |",
            f"| **Delta** | | | **{comparison.resolution_delta:+.1%}** |",
            "",
            "## Token & Cost Comparison",
            "",
            "| Metric | Baseline | Treatment | Delta |",
            "|--------|----------|-----------|-------|",
            f"| Avg Tokens | {baseline.avg_tokens:,.0f} "
            f"| {treatment.avg_tokens:,.0f} "
            f"| {comparison.token_delta:+,.0f} |",
            f"| Avg Cost | ${baseline.avg_cost:.4f} "
            f"| ${treatment.avg_cost:.4f} "
            f"| ${comparison.cost_delta:+.4f} |",
            "",
        ]

        # Per-repo breakdown
        if comparison.per_repo_deltas:
            lines.extend(
                [
                    "## Per-Repository Breakdown",
                    "",
                    "| Repository | Baseline Rate | Treatment Rate | Delta |",
                    "|------------|--------------|----------------|-------|",
                ]
            )
            for repo, delta in sorted(comparison.per_repo_deltas.items()):
                b_rate = (
                    baseline.per_repo_breakdown[repo].resolution_rate
                    if repo in baseline.per_repo_breakdown
                    else 0.0
                )
                t_rate = (
                    treatment.per_repo_breakdown[repo].resolution_rate
                    if repo in treatment.per_repo_breakdown
                    else 0.0
                )
                lines.append(f"| {repo} | {b_rate:.1%} | {t_rate:.1%} | {delta:+.1%} |")
            lines.append("")

        # Statistical significance
        lines.append("## Statistical Significance")
        lines.append("")
        if comparison.p_value is not None:
            lines.append(f"- **McNemar's test p-value**: {comparison.p_value:.4f}")
            if comparison.statistically_significant:
                lines.append("- **Result**: Statistically significant (p < 0.05)")
            else:
                lines.append("- **Result**: Not statistically significant (p >= 0.05)")
        else:
            lines.append(
                "- Statistical significance could not be computed (insufficient paired data)."
            )
        lines.append("")

        return "\n".join(lines)

    def generate_csv(self, results: list[BenchmarkResult]) -> str:
        """Generate a CSV string from benchmark results.

        Columns: instance_id, context_mode, resolved, token_usage,
        inference_cost, steps, duration_ms.

        Args:
            results: Results to export.

        Returns:
            CSV-formatted string with header row.
        """
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "instance_id",
                "context_mode",
                "resolved",
                "token_usage",
                "inference_cost",
                "steps",
                "duration_ms",
            ]
        )
        for r in results:
            writer.writerow(
                [
                    r.instance_id,
                    r.context_mode.value,
                    r.resolved,
                    r.token_usage,
                    r.inference_cost,
                    r.steps,
                    r.duration_ms,
                ]
            )
        return output.getvalue()

"""Quality aggregator for multi-file scoring.

Aggregates quality scores across multiple files for project-wide analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FileScore:
    """Score entry for a single file."""

    file_path: str
    overall_score: float
    categories: dict[str, float] = field(default_factory=dict)
    violation_count: int = 0
    gate_passed: bool = False


@dataclass
class AggregateReport:
    """Aggregated quality report across multiple files."""

    total_files: int = 0
    avg_score: float = 0.0
    min_score: float = 0.0
    max_score: float = 0.0
    category_averages: dict[str, float] = field(default_factory=dict)
    total_violations: int = 0
    gate_pass_rate: float = 0.0
    best_files: list[str] = field(default_factory=list)
    worst_files: list[str] = field(default_factory=list)
    score_distribution: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_files": self.total_files,
            "avg_score": self.avg_score,
            "min_score": self.min_score,
            "max_score": self.max_score,
            "category_averages": self.category_averages,
            "total_violations": self.total_violations,
            "gate_pass_rate": self.gate_pass_rate,
            "best_files": self.best_files,
            "worst_files": self.worst_files,
            "score_distribution": self.score_distribution,
        }


class QualityAggregator:
    """Aggregate quality scores across files."""

    def aggregate_scores(self, files: list[FileScore]) -> AggregateReport:
        """Compute aggregate metrics from file scores."""
        if not files:
            return AggregateReport()

        scores = [f.overall_score for f in files]
        avg = sum(scores) / len(scores)
        gate_passed = sum(1 for f in files if f.gate_passed)
        total_violations = sum(f.violation_count for f in files)

        # Category averages
        cat_sums: dict[str, list[float]] = {}
        for f in files:
            for cat, val in f.categories.items():
                cat_sums.setdefault(cat, []).append(val)
        cat_avgs = {cat: round(sum(vals) / len(vals), 2) for cat, vals in cat_sums.items()}

        # Best/worst files
        sorted_files = sorted(files, key=lambda f: f.overall_score, reverse=True)
        best = [f.file_path for f in sorted_files[:3]]
        worst = [f.file_path for f in sorted_files[-3:]] if len(sorted_files) > 3 else []

        # Score distribution buckets
        distribution: dict[str, int] = {
            "90-100": 0,
            "80-89": 0,
            "70-79": 0,
            "60-69": 0,
            "0-59": 0,
        }
        for s in scores:
            if s >= 90:
                distribution["90-100"] += 1
            elif s >= 80:
                distribution["80-89"] += 1
            elif s >= 70:
                distribution["70-79"] += 1
            elif s >= 60:
                distribution["60-69"] += 1
            else:
                distribution["0-59"] += 1

        return AggregateReport(
            total_files=len(files),
            avg_score=round(avg, 2),
            min_score=round(min(scores), 2),
            max_score=round(max(scores), 2),
            category_averages=cat_avgs,
            total_violations=total_violations,
            gate_pass_rate=round(gate_passed / len(files), 4) if files else 0.0,
            best_files=best,
            worst_files=worst,
            score_distribution=distribution,
        )

    def compare_files(self, files: list[FileScore]) -> dict[str, Any]:
        """Compare files side-by-side."""
        if not files:
            return {"rankings": [], "range": 0.0}

        sorted_files = sorted(files, key=lambda f: f.overall_score, reverse=True)
        rankings = [
            {
                "rank": i + 1,
                "file_path": f.file_path,
                "overall_score": round(f.overall_score, 2),
                "gate_passed": f.gate_passed,
            }
            for i, f in enumerate(sorted_files)
        ]

        scores = [f.overall_score for f in files]
        return {
            "rankings": rankings,
            "range": round(max(scores) - min(scores), 2),
            "best": sorted_files[0].file_path,
            "worst": sorted_files[-1].file_path,
        }

    def generate_quality_report(self, files: list[FileScore]) -> dict[str, Any]:
        """Generate a combined quality report."""
        aggregate = self.aggregate_scores(files)
        comparison = self.compare_files(files)
        return {
            "aggregate": aggregate.to_dict(),
            "comparison": comparison,
        }

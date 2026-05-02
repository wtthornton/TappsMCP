"""Diataxis balance validator for project documentation.

Scans all markdown files in a project, classifies each into Diataxis
quadrants, and produces a coverage report with balance scoring and
recommendations for underrepresented quadrants.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import structlog

from docs_mcp.analyzers.diataxis import DiataxisClassifier, DiataxisCoverage, DiataxisResult
from docs_mcp.validators._scan_filters import matches_any_pattern

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

_MAX_FILES = 200


class DiataxisValidator:
    """Validates Diataxis coverage balance across project documentation."""

    SKIP_DIRS: ClassVar[frozenset[str]] = frozenset(
        {
            "__pycache__",
            ".git",
            ".venv",
            "venv",
            "node_modules",
            ".tox",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            "dist",
            "build",
            ".eggs",
            "site-packages",
        }
    )

    # Ideal distribution targets (adjustable per project type)
    _IDEAL_BALANCE: ClassVar[dict[str, float]] = {
        "tutorial": 15.0,
        "how-to": 30.0,
        "reference": 35.0,
        "explanation": 20.0,
    }

    def __init__(self, classifier: DiataxisClassifier | None = None) -> None:
        self._classifier = classifier or DiataxisClassifier()

    def validate(
        self,
        project_root: Path,
        *,
        doc_dirs: list[str] | None = None,
        max_unclassified_samples: int = 20,
        archive_paths: list[str] | None = None,
    ) -> DiataxisCoverage:
        """Scan and classify all markdown files, producing a coverage report.

        Args:
            project_root: Root directory of the project.
            doc_dirs: Optional list of documentation directories to scan.
                Defaults to scanning root + docs/ + doc/.
            max_unclassified_samples: Maximum number of unclassified file paths
                to return in the report. Defaults to 20.

        Returns:
            DiataxisCoverage with per-file classifications and balance score.
        """
        project_root = project_root.resolve()
        md_files = self._find_markdown_files(project_root, doc_dirs)

        excluded_count = 0
        if archive_paths:
            kept: list[Path] = []
            for f in md_files:
                try:
                    rel = str(f.relative_to(project_root)).replace("\\", "/")
                except ValueError:
                    rel = str(f).replace("\\", "/")
                if matches_any_pattern(rel, archive_paths):
                    excluded_count += 1
                else:
                    kept.append(f)
            md_files = kept

        total_scanned = len(md_files)

        if not md_files:
            return DiataxisCoverage(
                balance_score=0.0,
                adjusted_balance_score=0.0,
                classification_coverage=0.0,
                recommendations=["No markdown documentation files found."],
                scoring_note=(
                    "No files scanned; adjusted_balance_score is the trustworthy metric."
                ),
                excluded_paths_count=excluded_count,
            )

        # Classify each file. Track unclassified paths (read failures or capped by _MAX_FILES).
        results: list[DiataxisResult] = []
        unclassified: list[str] = []

        def _rel(p: Path) -> str:
            try:
                return str(p.relative_to(project_root)).replace("\\", "/")
            except ValueError:
                return str(p).replace("\\", "/")

        for md_file in md_files[:_MAX_FILES]:
            try:
                content = md_file.read_text(encoding="utf-8", errors="replace")
                rel_path = _rel(md_file)
                result = self._classifier.classify(content, file_path=rel_path)
                results.append(result)
            except Exception:
                logger.debug("diataxis_classify_failed", file=str(md_file))
                unclassified.append(_rel(md_file))

        # Files beyond the scan cap are also unclassified.
        for md_file in md_files[_MAX_FILES:]:
            unclassified.append(_rel(md_file))

        classified_count = len(results)
        unclassified_count = total_scanned - classified_count
        classification_coverage = (
            round(classified_count / total_scanned * 100, 1) if total_scanned > 0 else 0.0
        )
        unclassified_sample = unclassified[: max(0, max_unclassified_samples)]

        if not results:
            return DiataxisCoverage(
                balance_score=0.0,
                adjusted_balance_score=0.0,
                classification_coverage=classification_coverage,
                total_files=total_scanned,
                total_scanned=total_scanned,
                classified_files=0,
                classified_count=0,
                unclassified_count=unclassified_count,
                unclassified_files=unclassified_sample,
                recommendations=["Failed to classify any documentation files."],
                scoring_note=(
                    "No files classified; adjusted_balance_score is the trustworthy metric."
                ),
                excluded_paths_count=excluded_count,
            )

        # Calculate coverage percentages (of classified files)
        counts: dict[str, int] = {
            "tutorial": 0,
            "how-to": 0,
            "reference": 0,
            "explanation": 0,
        }
        for r in results:
            if r.primary_quadrant in counts:
                counts[r.primary_quadrant] += 1

        total = len(results)
        coverage = DiataxisCoverage(
            tutorial_pct=round(counts["tutorial"] / total * 100, 1),
            howto_pct=round(counts["how-to"] / total * 100, 1),
            reference_pct=round(counts["reference"] / total * 100, 1),
            explanation_pct=round(counts["explanation"] / total * 100, 1),
            total_files=total_scanned,
            total_scanned=total_scanned,
            classified_files=total,
            classified_count=total,
            unclassified_count=unclassified_count,
            unclassified_files=unclassified_sample,
            classification_coverage=classification_coverage,
            per_file=results,
            excluded_paths_count=excluded_count,
        )

        # Calculate balance score (existing, unchanged)
        coverage.balance_score = self._calculate_balance_score(coverage)

        # Adjusted score penalises "perfect balance on a small sample".
        coverage.adjusted_balance_score = round(
            coverage.balance_score * classification_coverage / 100, 1
        )

        coverage.scoring_note = (
            "Prefer adjusted_balance_score; it reflects both quadrant balance "
            "and classification_coverage."
        )

        # Generate recommendations
        coverage.recommendations = self._generate_recommendations(coverage, counts, total)

        return coverage

    def _find_markdown_files(
        self,
        project_root: Path,
        doc_dirs: list[str] | None,
    ) -> list[Path]:
        """Find all markdown files to classify."""
        files: list[Path] = []

        # Root-level markdown files
        for f in sorted(project_root.iterdir()):
            if f.is_file() and f.suffix.lower() in (".md", ".mdx"):
                name_lower = f.name.lower()
                if name_lower not in ("license.md",):
                    files.append(f)

        # Documentation directories
        scan_dirs = doc_dirs or ["docs", "doc", "documentation"]
        for dir_name in scan_dirs:
            doc_dir = project_root / dir_name
            if doc_dir.is_dir():
                for f in sorted(doc_dir.rglob("*.md")):
                    if not any(p in self.SKIP_DIRS for p in f.parts):
                        files.append(f)
                for f in sorted(doc_dir.rglob("*.mdx")):
                    if not any(p in self.SKIP_DIRS for p in f.parts):
                        files.append(f)

        return files

    def _calculate_balance_score(self, coverage: DiataxisCoverage) -> float:
        """Calculate balance score (0-100) based on quadrant distribution.

        A perfectly balanced distribution scores 100. Missing quadrants
        reduce the score significantly.
        """
        actual = {
            "tutorial": coverage.tutorial_pct,
            "how-to": coverage.howto_pct,
            "reference": coverage.reference_pct,
            "explanation": coverage.explanation_pct,
        }

        # Penalise missing quadrants heavily
        missing_count = sum(1 for v in actual.values() if v == 0)
        if missing_count >= 3:
            return 10.0
        if missing_count == 2:
            return 25.0

        # Calculate deviation from ideal
        total_deviation = 0.0
        for quadrant, ideal in self._IDEAL_BALANCE.items():
            deviation = abs(actual[quadrant] - ideal)
            total_deviation += deviation

        # Max possible deviation is 200 (all in one quadrant)
        # Score: 100 - (deviation / 2)
        score = max(0.0, 100.0 - total_deviation / 2)

        # Bonus for having all four quadrants present
        if missing_count == 0:
            score = min(100.0, score + 10.0)

        return round(score, 1)

    def _generate_recommendations(
        self,
        coverage: DiataxisCoverage,
        counts: dict[str, int],
        total: int,
    ) -> list[str]:
        """Generate actionable recommendations for underrepresented quadrants."""
        recs: list[str] = []

        # Identify missing quadrants
        quadrant_labels = {
            "tutorial": "Tutorials (getting-started, walkthroughs)",
            "how-to": "How-to Guides (task-oriented recipes)",
            "reference": "Reference (API docs, parameter tables)",
            "explanation": "Explanations (architecture, design decisions, ADRs)",
        }
        for quadrant, label in quadrant_labels.items():
            if counts.get(quadrant, 0) == 0:
                recs.append(f"Missing: {label}. Add at least one document in this category.")

        # Identify over-represented quadrants
        for quadrant, label in quadrant_labels.items():
            pct = counts.get(quadrant, 0) / total * 100 if total > 0 else 0
            if pct > 60:
                recs.append(
                    f"Over-represented: {label} ({pct:.0f}%). "
                    f"Consider adding other content types for balance."
                )

        # General balance advice
        if coverage.balance_score < 50:
            recs.append(
                "Documentation is heavily skewed toward one content type. "
                "The Diataxis framework recommends a mix of all four types."
            )

        return recs

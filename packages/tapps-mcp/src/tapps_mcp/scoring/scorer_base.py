"""Abstract base class for language-specific code scorers.

This module defines the `ScorerBase` abstract class that all language
scorers must implement. It establishes the common interface for scoring
files across different programming languages.

Epic 56: Non-Python Language Scoring
Story 56.1: Abstract Scorer Base Class
"""

from __future__ import annotations

import abc
from pathlib import Path
from typing import TYPE_CHECKING

from tapps_mcp.scoring.models import CategoryScore, ScoreResult

if TYPE_CHECKING:
    from tapps_core.config.settings import ScoringWeights, TappsMCPSettings


class ScorerBase(abc.ABC):
    """Abstract base class for language-specific code scorers.

    All language scorers (Python, TypeScript, Go, Rust, etc.) inherit from
    this class and implement the abstract methods to provide language-specific
    scoring logic.

    The base class defines:
    - The common interface for scoring files
    - Shared utility methods for score calculation
    - Category and weight management

    Subclasses must implement:
    - ``language`` property: The language identifier (e.g., "python", "typescript")
    - ``supported_categories`` property: List of categories this scorer supports
    - ``file_extensions`` property: Set of file extensions this scorer handles
    - ``score_file`` method: Full async scoring with all available tools
    - ``score_file_quick`` method: Fast ruff-only (or equivalent) scoring
    """

    def __init__(
        self,
        settings: TappsMCPSettings | None = None,
        weights: ScoringWeights | None = None,
    ) -> None:
        """Initialize the scorer with optional settings and weights.

        Args:
            settings: TappsMCP settings. If None, loaded via ``load_settings()``.
            weights: Category weights for overall score calculation. If None,
                uses weights from settings.
        """
        from tapps_core.config.settings import load_settings

        self._settings = settings or load_settings()
        self._weights = weights or self._settings.scoring_weights

    # ------------------------------------------------------------------
    # Abstract properties (must be implemented by subclasses)
    # ------------------------------------------------------------------

    @property
    @abc.abstractmethod
    def language(self) -> str:
        """Return the language identifier (e.g., 'python', 'typescript', 'go').

        This identifier is used for routing, reporting, and configuration
        lookup. It should be lowercase and match common conventions.
        """

    @property
    @abc.abstractmethod
    def supported_categories(self) -> list[str]:
        """Return the list of scoring categories this scorer supports.

        Standard categories are:
        - complexity: Cyclomatic complexity / branching
        - security: Security vulnerabilities and risky patterns
        - maintainability: Code clarity, documentation, size
        - test_coverage: Test file presence / test markers
        - performance: Performance anti-patterns
        - structure: Project layout and organization
        - devex: Developer experience signals

        A scorer may support a subset of these categories based on
        the availability of language-specific analysis tools.
        """

    @property
    @abc.abstractmethod
    def file_extensions(self) -> frozenset[str]:
        """Return the set of file extensions this scorer handles.

        Extensions should include the leading dot (e.g., '.py', '.ts').
        """

    # ------------------------------------------------------------------
    # Abstract methods (must be implemented by subclasses)
    # ------------------------------------------------------------------

    @abc.abstractmethod
    async def score_file(self, file_path: Path, *, mode: str = "subprocess") -> ScoreResult:
        """Score a file using all available tools (full mode).

        This method runs language-specific linters, type checkers, security
        scanners, and complexity analyzers to produce a comprehensive score.

        Args:
            file_path: Path to the file to score.
            mode: Execution mode for external tools. One of:
                - ``"subprocess"``: Run tools as subprocesses (default)
                - ``"direct"``: Use library APIs when available
                - ``"auto"``: Choose based on availability

        Returns:
            A ScoreResult with per-category scores and an overall score.
        """

    @abc.abstractmethod
    def score_file_quick(self, file_path: Path) -> ScoreResult:
        """Score a file using only fast linting (quick mode).

        This method runs only the fastest linting tool (e.g., ruff for Python,
        eslint for TypeScript) to provide rapid feedback during edit loops.
        Target latency is < 500ms.

        Args:
            file_path: Path to the file to score.

        Returns:
            A ScoreResult with a linting-only score. The ``degraded`` flag
            will typically be False since quick mode is intentionally limited.
        """

    def score_file_quick_enriched(self, file_path: Path) -> ScoreResult:
        """Quick mode with AST enrichment (Python only).

        Default implementation delegates to ``score_file_quick``. The Python
        scorer overrides this to add AST-based heuristics on top of ruff.
        """
        return self.score_file_quick(file_path)

    # ------------------------------------------------------------------
    # Concrete methods (shared by all scorers)
    # ------------------------------------------------------------------

    def can_handle(self, file_path: Path) -> bool:
        """Return True if this scorer can handle the given file.

        The default implementation checks if the file extension is in
        ``file_extensions``. Subclasses may override for more complex logic.

        Args:
            file_path: Path to the file to check.

        Returns:
            True if this scorer supports the file's extension.
        """
        return file_path.suffix.lower() in self.file_extensions

    def score_category(self, file_path: Path, category: str) -> CategoryScore:
        """Score a single category for a file.

        This is a convenience method that runs the full scorer and extracts
        a single category. For scoring all categories, use ``score_file()``.

        Args:
            file_path: Path to the file to score.
            category: The category to extract (e.g., "complexity", "security").

        Returns:
            The CategoryScore for the requested category.

        Raises:
            ValueError: If the category is not supported by this scorer.
        """
        import asyncio

        if category not in self.supported_categories:
            msg = (
                f"Category '{category}' not supported by {self.language} scorer. "
                f"Supported: {self.supported_categories}"
            )
            raise ValueError(msg)

        result = asyncio.run(self.score_file(file_path))
        if category not in result.categories:
            msg = f"Category '{category}' not found in score result"
            raise ValueError(msg)
        return result.categories[category]

    def score_file_sync(self, file_path: Path) -> ScoreResult:
        """Synchronous wrapper around the async ``score_file``.

        Useful for callers that cannot use async/await.

        Args:
            file_path: Path to the file to score.

        Returns:
            A ScoreResult from the full scoring run.
        """
        import asyncio

        return asyncio.run(self.score_file(file_path))

    # ------------------------------------------------------------------
    # Score calculation helpers
    # ------------------------------------------------------------------

    def _calculate_overall(self, categories: dict[str, CategoryScore]) -> float:
        """Calculate the weighted overall score (0-100).

        The complexity category is inverted: (10 - complexity_score) * weight
        because lower complexity is better.

        Categories with weight=0 are informational and excluded.

        Args:
            categories: Dictionary of category name to CategoryScore.

        Returns:
            The overall score on a 0-100 scale.
        """
        from tapps_mcp.scoring.constants import clamp_overall

        total = 0.0
        for cat in categories.values():
            if cat.weight <= 0:
                continue
            if cat.name == "complexity":
                total += (10.0 - cat.score) * cat.weight
            else:
                total += cat.score * cat.weight
        return clamp_overall(total * 10.0)

    def _error_result(self, path: str) -> ScoreResult:
        """Return a zeroed ScoreResult for files that cannot be scored.

        Args:
            path: The file path to include in the result.

        Returns:
            A ScoreResult with overall_score=0 and degraded=True.
        """
        return ScoreResult(
            file_path=path,
            categories={},
            overall_score=0.0,
            degraded=True,
            missing_tools=[],
        )


# Standard scoring categories used across all language scorers.
STANDARD_CATEGORIES: list[str] = [
    "complexity",
    "security",
    "maintainability",
    "test_coverage",
    "performance",
    "structure",
    "devex",
]

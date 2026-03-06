"""Unit tests for ScorerBase abstract class.

Epic 56: Non-Python Language Scoring
Story 56.1: Abstract Scorer Base Class
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pytest

from tapps_mcp.scoring.models import CategoryScore, ScoreResult
from tapps_mcp.scoring.scorer import CodeScorer
from tapps_mcp.scoring.scorer_base import STANDARD_CATEGORIES, ScorerBase


class TestScorerBaseAbstract:
    """Test that ScorerBase cannot be instantiated directly."""

    def test_cannot_instantiate_abstract(self) -> None:
        """ScorerBase is abstract and should not be instantiated."""
        with pytest.raises(TypeError, match="abstract"):
            ScorerBase()  # type: ignore[abstract]


class TestScorerBaseInterface:
    """Test the ScorerBase interface via the concrete CodeScorer."""

    def test_language_property(self) -> None:
        """CodeScorer should return 'python' as its language."""
        scorer = CodeScorer()
        assert scorer.language == "python"

    def test_supported_categories_property(self) -> None:
        """CodeScorer should support all standard categories."""
        scorer = CodeScorer()
        assert scorer.supported_categories == STANDARD_CATEGORIES

    def test_file_extensions_property(self) -> None:
        """CodeScorer should handle .py and .pyi files."""
        scorer = CodeScorer()
        assert scorer.file_extensions == frozenset({".py", ".pyi"})

    def test_can_handle_python_files(self) -> None:
        """can_handle should return True for Python files."""
        scorer = CodeScorer()
        assert scorer.can_handle(Path("test.py")) is True
        assert scorer.can_handle(Path("types.pyi")) is True
        assert scorer.can_handle(Path("src/module/file.py")) is True

    def test_can_handle_non_python_files(self) -> None:
        """can_handle should return False for non-Python files."""
        scorer = CodeScorer()
        assert scorer.can_handle(Path("test.ts")) is False
        assert scorer.can_handle(Path("main.go")) is False
        assert scorer.can_handle(Path("lib.rs")) is False
        assert scorer.can_handle(Path("script.js")) is False


class TestScorerBaseInheritance:
    """Test that CodeScorer properly inherits from ScorerBase."""

    def test_is_subclass(self) -> None:
        """CodeScorer should be a subclass of ScorerBase."""
        assert issubclass(CodeScorer, ScorerBase)

    def test_is_instance(self) -> None:
        """CodeScorer instances should be instances of ScorerBase."""
        scorer = CodeScorer()
        assert isinstance(scorer, ScorerBase)

    def test_inherits_calculate_overall(self) -> None:
        """CodeScorer should inherit _calculate_overall from ScorerBase."""
        scorer = CodeScorer()
        # _calculate_overall is inherited from ScorerBase
        categories = {
            "complexity": CategoryScore(name="complexity", score=3.0, weight=0.18),
            "security": CategoryScore(name="security", score=8.0, weight=0.27),
        }
        # Complexity is inverted: (10 - 3) * 0.18 = 1.26
        # Security: 8 * 0.27 = 2.16
        # Total: (1.26 + 2.16) * 10 = 34.2
        result = scorer._calculate_overall(categories)
        assert 34.0 <= result <= 35.0

    def test_inherits_error_result(self) -> None:
        """CodeScorer should inherit _error_result from ScorerBase."""
        scorer = CodeScorer()
        result = scorer._error_result("/path/to/file.py")
        assert result.file_path == "/path/to/file.py"
        assert result.overall_score == 0.0
        assert result.degraded is True
        assert result.categories == {}


class TestScorerBaseSyncWrapper:
    """Test the synchronous wrapper method inherited from ScorerBase."""

    def test_score_file_sync_exists(self) -> None:
        """score_file_sync should be available on CodeScorer."""
        scorer = CodeScorer()
        assert hasattr(scorer, "score_file_sync")
        assert callable(scorer.score_file_sync)

    def test_score_file_sync_works(self, tmp_path: Path) -> None:
        """score_file_sync should return a ScoreResult."""
        test_file = tmp_path / "test.py"
        test_file.write_text("x = 1\n")

        scorer = CodeScorer()
        result = scorer.score_file_sync(test_file)

        assert isinstance(result, ScoreResult)
        assert str(test_file) in result.file_path


class TestScorerBaseScoreCategory:
    """Test the score_category convenience method."""

    def test_score_category_for_valid_category(self, tmp_path: Path) -> None:
        """score_category should return a CategoryScore for a valid category."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    pass\n")

        scorer = CodeScorer()
        result = scorer.score_category(test_file, "complexity")

        assert isinstance(result, CategoryScore)
        assert result.name == "complexity"

    def test_score_category_for_invalid_category(self, tmp_path: Path) -> None:
        """score_category should raise ValueError for unsupported categories."""
        test_file = tmp_path / "test.py"
        test_file.write_text("x = 1\n")

        scorer = CodeScorer()

        with pytest.raises(ValueError, match="not supported"):
            scorer.score_category(test_file, "nonexistent_category")


class TestStandardCategories:
    """Test the STANDARD_CATEGORIES constant."""

    def test_standard_categories_list(self) -> None:
        """STANDARD_CATEGORIES should contain the expected categories."""
        expected = [
            "complexity",
            "security",
            "maintainability",
            "test_coverage",
            "performance",
            "structure",
            "devex",
        ]
        assert STANDARD_CATEGORIES == expected

    def test_standard_categories_count(self) -> None:
        """STANDARD_CATEGORIES should have 7 categories."""
        assert len(STANDARD_CATEGORIES) == 7


class ConcreteTestScorer(ScorerBase):
    """Concrete implementation of ScorerBase for testing."""

    @property
    def language(self) -> str:
        return "test"

    @property
    def supported_categories(self) -> list[str]:
        return ["complexity", "security"]

    @property
    def file_extensions(self) -> frozenset[str]:
        return frozenset({".test"})

    async def score_file(self, file_path: Path, *, mode: str = "subprocess") -> ScoreResult:
        return ScoreResult(
            file_path=str(file_path),
            categories={
                "complexity": CategoryScore(name="complexity", score=5.0, weight=0.18),
                "security": CategoryScore(name="security", score=8.0, weight=0.27),
            },
            overall_score=75.0,
        )

    def score_file_quick(self, file_path: Path) -> ScoreResult:
        return ScoreResult(
            file_path=str(file_path),
            categories={
                "linting": CategoryScore(name="linting", score=9.0, weight=1.0),
            },
            overall_score=90.0,
        )


class TestConcreteImplementation:
    """Test creating a concrete ScorerBase implementation."""

    def test_concrete_scorer_instantiation(self) -> None:
        """A concrete implementation should be instantiable."""
        scorer = ConcreteTestScorer()
        assert scorer.language == "test"
        assert scorer.supported_categories == ["complexity", "security"]
        assert scorer.file_extensions == frozenset({".test"})

    def test_concrete_scorer_can_handle(self) -> None:
        """Concrete implementation should use inherited can_handle."""
        scorer = ConcreteTestScorer()
        assert scorer.can_handle(Path("file.test")) is True
        assert scorer.can_handle(Path("file.py")) is False

    def test_concrete_scorer_score_file_quick(self) -> None:
        """Concrete implementation's score_file_quick should work."""
        scorer = ConcreteTestScorer()
        result = scorer.score_file_quick(Path("file.test"))
        assert result.overall_score == 90.0

    @pytest.mark.asyncio
    async def test_concrete_scorer_score_file(self) -> None:
        """Concrete implementation's score_file should work."""
        scorer = ConcreteTestScorer()
        result = await scorer.score_file(Path("file.test"))
        assert result.overall_score == 75.0
        assert "complexity" in result.categories
        assert "security" in result.categories

    def test_concrete_scorer_score_file_sync(self) -> None:
        """Concrete implementation's score_file_sync should work."""
        scorer = ConcreteTestScorer()
        result = scorer.score_file_sync(Path("file.test"))
        assert result.overall_score == 75.0

    def test_concrete_scorer_score_category(self) -> None:
        """Concrete implementation's score_category should work."""
        scorer = ConcreteTestScorer()
        result = scorer.score_category(Path("file.test"), "complexity")
        assert result.name == "complexity"
        assert result.score == 5.0

    def test_concrete_scorer_score_category_invalid(self) -> None:
        """score_category should reject unsupported categories."""
        scorer = ConcreteTestScorer()
        with pytest.raises(ValueError, match="not supported"):
            scorer.score_category(Path("file.test"), "performance")


class TestCalculateOverall:
    """Test the _calculate_overall method from ScorerBase."""

    def test_complexity_inverted(self) -> None:
        """Complexity score should be inverted in overall calculation."""
        scorer = ConcreteTestScorer()
        categories = {
            "complexity": CategoryScore(name="complexity", score=2.0, weight=1.0),
        }
        # (10 - 2) * 1.0 * 10 = 80
        result = scorer._calculate_overall(categories)
        assert result == 80.0

    def test_non_complexity_direct(self) -> None:
        """Non-complexity scores should be used directly."""
        scorer = ConcreteTestScorer()
        categories = {
            "security": CategoryScore(name="security", score=8.0, weight=1.0),
        }
        # 8 * 1.0 * 10 = 80
        result = scorer._calculate_overall(categories)
        assert result == 80.0

    def test_zero_weight_excluded(self) -> None:
        """Categories with weight=0 should be excluded."""
        scorer = ConcreteTestScorer()
        categories = {
            "security": CategoryScore(name="security", score=8.0, weight=0.5),
            "linting": CategoryScore(name="linting", score=2.0, weight=0.0),
        }
        # Only security counts: 8 * 0.5 * 10 = 40
        result = scorer._calculate_overall(categories)
        assert result == 40.0

    def test_mixed_categories(self) -> None:
        """Overall should be weighted sum of all categories."""
        scorer = ConcreteTestScorer()
        categories = {
            "complexity": CategoryScore(name="complexity", score=4.0, weight=0.2),
            "security": CategoryScore(name="security", score=8.0, weight=0.3),
            "maintainability": CategoryScore(name="maintainability", score=7.0, weight=0.5),
        }
        # complexity: (10 - 4) * 0.2 = 1.2
        # security: 8 * 0.3 = 2.4
        # maintainability: 7 * 0.5 = 3.5
        # total: (1.2 + 2.4 + 3.5) * 10 = 71.0
        result = scorer._calculate_overall(categories)
        assert result == 71.0

    def test_result_clamped_to_100(self) -> None:
        """Overall score should be clamped to maximum 100."""
        scorer = ConcreteTestScorer()
        categories = {
            "complexity": CategoryScore(name="complexity", score=0.0, weight=1.0),
            "security": CategoryScore(name="security", score=10.0, weight=1.0),
        }
        # complexity: (10 - 0) * 1.0 = 10
        # security: 10 * 1.0 = 10
        # total: (10 + 10) * 10 = 200 -> clamped to 100
        result = scorer._calculate_overall(categories)
        assert result == 100.0

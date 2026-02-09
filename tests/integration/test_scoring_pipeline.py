"""Integration test: end-to-end scoring pipeline.

Tests the full scoring flow from file creation through CodeScorer
to ScoreResult, using real file I/O but mocked external tool subprocesses.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tapps_mcp.scoring.scorer import CodeScorer
from tapps_mcp.tools.parallel import ParallelResults

SAMPLE_CODE = '''\
"""A sample module for scoring tests."""

from __future__ import annotations


def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


def greet(name: str) -> str:
    """Return a greeting."""
    return f"Hello, {name}!"
'''


@pytest.mark.integration
class TestScoringPipeline:
    """End-to-end scoring pipeline tests."""

    @pytest.fixture
    def project(self, tmp_path: Path) -> Path:
        """Create a minimal project structure."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        (tmp_path / ".git").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "README.md").write_text("# Test")
        src = tmp_path / "src"
        src.mkdir()
        f = src / "sample.py"
        f.write_text(SAMPLE_CODE, encoding="utf-8")
        return f

    @pytest.fixture
    def project_with_test(self, tmp_path: Path) -> Path:
        """Create a project with matching test file."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        (tmp_path / ".git").mkdir()
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_app.py").write_text("pass", encoding="utf-8")
        f = tmp_path / "app.py"
        f.write_text(SAMPLE_CODE, encoding="utf-8")
        return f

    def test_quick_score_clean_file(self, project: Path):
        """Quick mode scores a clean file to 100."""
        with patch("tapps_mcp.scoring.scorer.run_ruff_check") as mock_ruff:
            mock_ruff.return_value = []
            scorer = CodeScorer()
            result = scorer.score_file_quick(project)

        assert result.overall_score == 100.0
        assert result.degraded is False
        assert "linting" in result.categories

    @pytest.mark.asyncio
    async def test_full_score_with_all_tools(self, project: Path):
        """Full mode produces all 7+2 categories."""
        parallel = ParallelResults(
            lint_issues=[],
            type_issues=[],
            security_issues=[],
            radon_cc=[{"name": "add", "complexity": 1}, {"name": "greet", "complexity": 1}],
            radon_mi=90.0,
        )

        with patch(
            "tapps_mcp.scoring.scorer.run_all_tools",
            new_callable=AsyncMock,
            return_value=parallel,
        ):
            scorer = CodeScorer()
            result = await scorer.score_file(project)

        # Should have all 7 weighted + 2 informational categories
        expected_cats = {
            "complexity",
            "security",
            "maintainability",
            "test_coverage",
            "performance",
            "structure",
            "devex",
            "linting",
            "type_checking",
        }
        assert set(result.categories.keys()) == expected_cats
        assert 0 <= result.overall_score <= 100
        assert result.degraded is False

    @pytest.mark.asyncio
    async def test_degraded_mode(self, project: Path):
        """Degraded results when external tools are missing."""
        parallel = ParallelResults(
            missing_tools=["bandit", "radon", "mypy"],
            degraded=True,
        )

        with patch(
            "tapps_mcp.scoring.scorer.run_all_tools",
            new_callable=AsyncMock,
            return_value=parallel,
        ):
            scorer = CodeScorer()
            result = await scorer.score_file(project)

        assert result.degraded is True
        assert len(result.missing_tools) == 3
        # Fallback heuristics should still produce a reasonable score
        assert result.overall_score > 0

    @pytest.mark.asyncio
    async def test_test_coverage_heuristic(self, project_with_test: Path):
        """Test coverage heuristic detects matching test file."""
        parallel = ParallelResults()

        with patch(
            "tapps_mcp.scoring.scorer.run_all_tools",
            new_callable=AsyncMock,
            return_value=parallel,
        ):
            scorer = CodeScorer()
            result = await scorer.score_file(project_with_test)

        assert result.categories["test_coverage"].score == 5.0

    @pytest.mark.asyncio
    async def test_structure_score_reflects_layout(self, project: Path):
        """Structure score reflects project layout quality."""
        parallel = ParallelResults()

        with patch(
            "tapps_mcp.scoring.scorer.run_all_tools",
            new_callable=AsyncMock,
            return_value=parallel,
        ):
            scorer = CodeScorer()
            result = await scorer.score_file(project)

        # Project has pyproject.toml, .git, tests/, README.md → good score
        assert result.categories["structure"].score >= 5.0

    @pytest.mark.asyncio
    async def test_complexity_inversion(self, project: Path):
        """High complexity raw score should result in lower overall contribution."""
        parallel_low_cc = ParallelResults(
            radon_cc=[{"name": "f", "complexity": 1}],
            radon_mi=80.0,
        )
        parallel_high_cc = ParallelResults(
            radon_cc=[{"name": "f", "complexity": 30}],
            radon_mi=80.0,
        )

        scorer = CodeScorer()

        with patch(
            "tapps_mcp.scoring.scorer.run_all_tools",
            new_callable=AsyncMock,
            return_value=parallel_low_cc,
        ):
            result_low = await scorer.score_file(project)

        with patch(
            "tapps_mcp.scoring.scorer.run_all_tools",
            new_callable=AsyncMock,
            return_value=parallel_high_cc,
        ):
            result_high = await scorer.score_file(project)

        # Lower complexity → higher overall score
        assert result_low.overall_score > result_high.overall_score

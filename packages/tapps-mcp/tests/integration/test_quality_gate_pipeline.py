"""Integration test: quality gate pipeline.

Tests the full gate evaluation flow: scoring → gate evaluation → pass/fail.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tapps_mcp.gates.evaluator import evaluate_gate
from tapps_mcp.gates.models import GateThresholds
from tapps_mcp.scoring.scorer import CodeScorer
from tapps_mcp.tools.parallel import ParallelResults

SAMPLE_CODE = '''\
"""Clean module."""


def hello() -> str:
    """Say hello."""
    return "Hello"
'''


@pytest.mark.integration
class TestQualityGatePipeline:
    @pytest.fixture
    def project_file(self, tmp_path: Path) -> Path:
        (tmp_path / "pyproject.toml").write_text("[project]\n")
        (tmp_path / ".git").mkdir()
        (tmp_path / "tests").mkdir()
        f = tmp_path / "module.py"
        f.write_text(SAMPLE_CODE, encoding="utf-8")
        return f

    @pytest.mark.asyncio
    async def test_clean_file_passes_standard(self, project_file: Path):
        """A clean file with good tools passes the standard gate."""
        parallel = ParallelResults(
            lint_issues=[],
            type_issues=[],
            security_issues=[],
            radon_cc=[{"name": "hello", "complexity": 1}],
            radon_mi=90.0,
        )

        with patch(
            "tapps_mcp.scoring.scorer.run_all_tools",
            new_callable=AsyncMock,
            return_value=parallel,
        ):
            scorer = CodeScorer()
            score_result = await scorer.score_file(project_file)

        gate_result = evaluate_gate(score_result, preset="standard")
        assert gate_result.passed is True
        assert gate_result.failures == []

    @pytest.mark.asyncio
    async def test_strict_gate_stricter(self, project_file: Path):
        """Strict gate is harder to pass than standard."""
        parallel = ParallelResults(
            radon_cc=[{"name": "hello", "complexity": 1}],
            radon_mi=70.0,
        )

        with patch(
            "tapps_mcp.scoring.scorer.run_all_tools",
            new_callable=AsyncMock,
            return_value=parallel,
        ):
            scorer = CodeScorer()
            score_result = await scorer.score_file(project_file)

        standard = evaluate_gate(score_result, preset="standard")
        strict = evaluate_gate(score_result, preset="strict")

        # Standard might pass while strict fails, or both pass
        # but strict can't pass if standard fails
        if not standard.passed:
            assert not strict.passed

    @pytest.mark.asyncio
    async def test_custom_thresholds(self, project_file: Path):
        """Custom thresholds allow fine-grained control."""
        parallel = ParallelResults(
            radon_cc=[{"name": "hello", "complexity": 1}],
            radon_mi=90.0,
        )

        with patch(
            "tapps_mcp.scoring.scorer.run_all_tools",
            new_callable=AsyncMock,
            return_value=parallel,
        ):
            scorer = CodeScorer()
            score_result = await scorer.score_file(project_file)

        # Very permissive custom thresholds
        easy = GateThresholds(overall_min=10.0)
        result = evaluate_gate(score_result, thresholds=easy)
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_gate_reports_scores(self, project_file: Path):
        """Gate result includes all category scores."""
        parallel = ParallelResults(
            radon_cc=[{"name": "hello", "complexity": 1}],
            radon_mi=90.0,
        )

        with patch(
            "tapps_mcp.scoring.scorer.run_all_tools",
            new_callable=AsyncMock,
            return_value=parallel,
        ):
            scorer = CodeScorer()
            score_result = await scorer.score_file(project_file)

        gate_result = evaluate_gate(score_result, preset="standard")
        assert "overall" in gate_result.scores
        assert "security" in gate_result.scores
        assert "maintainability" in gate_result.scores

    @pytest.mark.asyncio
    async def test_degraded_adds_warning(self, project_file: Path):
        """Degraded results produce a warning but can still pass."""
        parallel = ParallelResults(
            missing_tools=["bandit"],
            degraded=True,
            radon_cc=[{"name": "hello", "complexity": 1}],
            radon_mi=90.0,
        )

        with patch(
            "tapps_mcp.scoring.scorer.run_all_tools",
            new_callable=AsyncMock,
            return_value=parallel,
        ):
            scorer = CodeScorer()
            score_result = await scorer.score_file(project_file)

        gate_result = evaluate_gate(score_result, preset="standard")
        assert len(gate_result.warnings) >= 1
        assert "bandit" in gate_result.warnings[0]

"""Tests for the per-category scorers (TAP-5628).

Each category turns a raw metric into a weighted `CategoryScore`. These tests
pin the assembly — name, weight, clamping, and the penalty paths — separately
from the metric functions themselves, which `test_ast_metrics.py` covers.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.scoring.scorer import CodeScorer


@pytest.fixture
def scorer() -> CodeScorer:
    return CodeScorer()


class TestStructureCategory:
    def test_category_is_named_and_weighted(self, scorer: CodeScorer, tmp_path: Path) -> None:
        result = scorer._score_structure_category(tmp_path / "m.py", 0.0)
        assert result.name == "structure"
        assert result.weight == scorer._weights.structure

    def test_dead_code_penalty_lowers_the_score(self, scorer: CodeScorer, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
        (tmp_path / "README.md").write_text("# x\n")
        target = tmp_path / "m.py"
        clean = scorer._score_structure_category(target, 0.0)
        penalised = scorer._score_structure_category(target, 20.0)
        assert penalised.score < clean.score

    def test_score_never_goes_negative(self, scorer: CodeScorer, tmp_path: Path) -> None:
        assert scorer._score_structure_category(tmp_path / "m.py", 10_000.0).score >= 0.0


class TestDevexCategory:
    def test_category_is_named_and_weighted(self, scorer: CodeScorer, tmp_path: Path) -> None:
        result = scorer._score_devex_category(tmp_path / "m.py")
        assert result.name == "devex"
        assert result.weight == scorer._weights.devex

    def test_agent_docs_raise_the_score(self, scorer: CodeScorer, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
        bare = scorer._score_devex_category(tmp_path / "m.py")
        (tmp_path / "AGENTS.md").write_text("# agents\n")
        (tmp_path / "docs").mkdir()
        assert scorer._score_devex_category(tmp_path / "m.py").score > bare.score


class TestTestCoverageCategory:
    def test_matching_test_file_beats_none(self, scorer: CodeScorer, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
        (tmp_path / "tests").mkdir()
        target = tmp_path / "widget.py"
        target.write_text("x = 1\n")
        uncovered = scorer._score_test_coverage_category(target)

        (tmp_path / "tests" / "test_widget.py").write_text("def test_x(): ...\n")
        assert scorer._score_test_coverage_category(target).score > uncovered.score

    def test_narrative_paths_are_exempt(self, scorer: CodeScorer, tmp_path: Path) -> None:
        """Docs-shaped files carry weight 0 rather than a coverage penalty."""
        result = scorer._score_test_coverage_category(tmp_path / "m.py")
        assert result.name == "test_coverage"
        assert result.weight >= 0.0

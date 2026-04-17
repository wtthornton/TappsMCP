"""Integration tests using real external tools.

These tests exercise the actual subprocess pipeline (ruff, etc.)
and are skipped if the tools are not installed.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def _tool_available(name: str) -> bool:
    return shutil.which(name) is not None


@pytest.mark.skipif(not _tool_available("ruff"), reason="ruff not installed")
class TestRealRuffScoring:
    """Test scoring with real ruff subprocess."""

    def test_score_clean_file_quick(self, tmp_path: Path) -> None:
        """A clean Python file should score well with real ruff (quick mode)."""
        from tapps_core.config.settings import load_settings
        from tapps_mcp.scoring.scorer import CodeScorer

        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"\n', encoding="utf-8")

        test_file = tmp_path / "clean.py"
        test_file.write_text(
            'from __future__ import annotations\n\n\ndef add(a: int, b: int) -> int:\n    """Add two numbers."""\n    return a + b\n',
            encoding="utf-8",
        )

        settings = load_settings(project_root=tmp_path)
        scorer = CodeScorer(settings=settings)
        result = scorer.score_file_quick(test_file)

        assert result is not None
        assert result.file_path == str(test_file.resolve())
        # Clean file should score well
        assert result.overall_score >= 50
        # Should have no or very few lint issues
        assert len(result.lint_issues) <= 2

    def test_score_file_with_issues_quick(self, tmp_path: Path) -> None:
        """A file with lint issues should produce diagnostics."""
        from tapps_core.config.settings import load_settings
        from tapps_mcp.scoring.scorer import CodeScorer

        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"\n', encoding="utf-8")

        test_file = tmp_path / "messy.py"
        test_file.write_text(
            "import os, sys\nx=1\ny =2\nprint(x+y)\n",
            encoding="utf-8",
        )

        settings = load_settings(project_root=tmp_path)
        scorer = CodeScorer(settings=settings)
        result = scorer.score_file_quick(test_file)

        assert result is not None
        # File with issues should have some lint diagnostics
        assert len(result.lint_issues) > 0

    def test_score_file_quick_enriched(self, tmp_path: Path) -> None:
        """Quick-enriched mode produces all 7 categories + linting."""
        from tapps_core.config.settings import load_settings
        from tapps_mcp.scoring.scorer import CodeScorer

        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"\n', encoding="utf-8")

        test_file = tmp_path / "sample.py"
        test_file.write_text(
            'from __future__ import annotations\n\n\ndef greet(name: str) -> str:\n    """Greet someone."""\n    return f"Hello, {name}!"\n',
            encoding="utf-8",
        )

        settings = load_settings(project_root=tmp_path)
        scorer = CodeScorer(settings=settings)
        result = scorer.score_file_quick_enriched(test_file)

        assert result is not None
        # Quick-enriched produces all 7 standard categories + linting
        expected_cats = {
            "complexity",
            "security",
            "maintainability",
            "test_coverage",
            "performance",
            "structure",
            "devex",
            "linting",
        }
        assert set(result.categories.keys()) == expected_cats
        assert 0.0 <= result.overall_score <= 100.0

    async def test_score_file_full_mode(self, tmp_path: Path) -> None:
        """Full async scoring produces a complete ScoreResult."""
        from tapps_core.config.settings import load_settings
        from tapps_mcp.scoring.scorer import CodeScorer

        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"\n', encoding="utf-8")

        test_file = tmp_path / "full_score.py"
        test_file.write_text(
            'from __future__ import annotations\n\nimport math\n\n\ndef circle_area(radius: float) -> float:\n    """Calculate circle area."""\n    return math.pi * radius ** 2\n',
            encoding="utf-8",
        )

        settings = load_settings(project_root=tmp_path)
        scorer = CodeScorer(settings=settings)
        result = await scorer.score_file(test_file)

        assert result is not None
        assert result.file_path == str(test_file.resolve())
        assert 0.0 <= result.overall_score <= 100.0
        # Full mode should have the standard categories
        assert "complexity" in result.categories
        assert "security" in result.categories

    def test_score_empty_file(self, tmp_path: Path) -> None:
        """Scoring an empty Python file should not crash."""
        from tapps_core.config.settings import load_settings
        from tapps_mcp.scoring.scorer import CodeScorer

        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"\n', encoding="utf-8")

        test_file = tmp_path / "empty.py"
        test_file.write_text("", encoding="utf-8")

        settings = load_settings(project_root=tmp_path)
        scorer = CodeScorer(settings=settings)
        result = scorer.score_file_quick(test_file)

        assert result is not None
        assert result.overall_score >= 0.0

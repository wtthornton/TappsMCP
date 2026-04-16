"""Tests for docs_mcp.validators.completeness — completeness checking."""

from __future__ import annotations

from pathlib import Path

from docs_mcp.validators.completeness import (
    CompletenessCategory,
    CompletenessChecker,
    CompletenessReport,
    _check_development_docs,
    _check_essential_docs,
    _check_project_docs,
    _file_exists_case_insensitive,
)

# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestCompletenessCategoryModel:
    """Test CompletenessCategory Pydantic model."""

    def test_defaults(self) -> None:
        cat = CompletenessCategory(name="test")
        assert cat.score == 0.0
        assert cat.present == []
        assert cat.missing == []
        assert cat.weight == 1.0

    def test_full_construction(self) -> None:
        cat = CompletenessCategory(
            name="essential_docs",
            score=0.5,
            present=["README.md"],
            missing=["LICENSE"],
            weight=3.0,
        )
        assert cat.name == "essential_docs"
        assert cat.weight == 3.0


class TestCompletenessReportModel:
    """Test CompletenessReport Pydantic model."""

    def test_defaults(self) -> None:
        report = CompletenessReport()
        assert report.overall_score == 0.0
        assert report.categories == []
        assert report.recommendations == []


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelpers:
    """Test helper functions."""

    def test_file_exists_case_insensitive_exact(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# Readme", encoding="utf-8")
        result = _file_exists_case_insensitive(tmp_path, "README.md")
        assert result == "README.md"

    def test_file_exists_case_insensitive_different_case(self, tmp_path: Path) -> None:
        (tmp_path / "readme.md").write_text("# Readme", encoding="utf-8")
        result = _file_exists_case_insensitive(tmp_path, "README.md")
        assert result == "readme.md"

    def test_file_exists_case_insensitive_stem_match(self, tmp_path: Path) -> None:
        """LICENSE without extension should match LICENSE.md."""
        (tmp_path / "LICENSE").write_text("MIT", encoding="utf-8")
        result = _file_exists_case_insensitive(tmp_path, "LICENSE.md")
        assert result is not None

    def test_file_not_found(self, tmp_path: Path) -> None:
        result = _file_exists_case_insensitive(tmp_path, "MISSING.md")
        assert result is None

    def test_check_essential_docs_all_present(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# Readme", encoding="utf-8")
        (tmp_path / "LICENSE").write_text("MIT", encoding="utf-8")
        cat = _check_essential_docs(tmp_path)
        assert cat.score == 1.0
        assert len(cat.present) == 2
        assert cat.missing == []

    def test_check_essential_docs_missing(self, tmp_path: Path) -> None:
        cat = _check_essential_docs(tmp_path)
        assert cat.score == 0.0
        assert len(cat.missing) == 2

    def test_check_development_docs(self, tmp_path: Path) -> None:
        (tmp_path / "CONTRIBUTING.md").write_text("# Contributing", encoding="utf-8")
        cat = _check_development_docs(tmp_path)
        assert cat.score == 0.5
        assert len(cat.present) == 1
        assert "CHANGELOG.md" in cat.missing

    def test_check_project_docs_present(self, tmp_path: Path) -> None:
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "guide.md").write_text("# Guide", encoding="utf-8")
        cat = _check_project_docs(tmp_path)
        assert cat.score == 1.0
        assert len(cat.present) > 0

    def test_check_project_docs_missing(self, tmp_path: Path) -> None:
        cat = _check_project_docs(tmp_path)
        assert cat.score == 0.0
        assert "docs/" in cat.missing


# ---------------------------------------------------------------------------
# CompletenessChecker tests
# ---------------------------------------------------------------------------


class TestCompletenessChecker:
    """Test CompletenessChecker.check()."""

    def test_nonexistent_root(self) -> None:
        checker = CompletenessChecker()
        report = checker.check(Path("/nonexistent/path"))
        assert report.overall_score == 0.0
        assert len(report.recommendations) > 0

    def test_empty_project(self, tmp_path: Path) -> None:
        checker = CompletenessChecker()
        report = checker.check(tmp_path)
        assert report.overall_score == 0.0
        assert len(report.recommendations) > 0

    def test_full_docs_high_score(self, tmp_path: Path) -> None:
        """A project with all docs should score near 100."""
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        (tmp_path / "LICENSE").write_text("MIT License\n", encoding="utf-8")
        (tmp_path / "CONTRIBUTING.md").write_text("# Contributing\n", encoding="utf-8")
        (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")

        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "guide.md").write_text("# Guide\n", encoding="utf-8")

        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text(
            '"""App module."""\n\ndef run() -> None:\n    """Run the app."""\n    pass\n',
            encoding="utf-8",
        )

        checker = CompletenessChecker()
        report = checker.check(tmp_path)
        # Essential (3) + Development (2) + project_docs (1) all perfect
        # API and inline depend on analysis but should be nonzero
        assert report.overall_score > 50.0

    def test_missing_readme_lower_score(self, tmp_path: Path) -> None:
        """Missing README should significantly lower the score."""
        (tmp_path / "LICENSE").write_text("MIT License\n", encoding="utf-8")

        checker = CompletenessChecker()
        report = checker.check(tmp_path)

        # Score should be lower than if README existed
        assert report.overall_score < 50.0
        # Should recommend adding README
        has_readme_rec = any("README" in r for r in report.recommendations)
        assert has_readme_rec

    def test_weight_based_scoring(self, tmp_path: Path) -> None:
        """Categories with higher weights should affect score more."""
        checker = CompletenessChecker()

        # Only essential docs (weight=3)
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        (tmp_path / "LICENSE").write_text("MIT\n", encoding="utf-8")

        report = checker.check(tmp_path)
        # Essential docs score 1.0 with weight 3, others score 0 with lower weights
        # Weighted: (1.0*3 + 0*2 + 0*2 + 0*1 + 0*1) / (3+2+2+1+1) = 3/9 = 0.333 -> 33.3
        assert report.overall_score > 30.0

    def test_all_categories_returned(self, tmp_path: Path) -> None:
        """All 5 categories should always be present."""
        checker = CompletenessChecker()
        report = checker.check(tmp_path)
        category_names = {c.name for c in report.categories}
        assert "essential_docs" in category_names
        assert "development_docs" in category_names
        assert "api_documentation" in category_names
        assert "inline_docs" in category_names
        assert "project_docs" in category_names

    def test_api_docs_coverage(self, tmp_path: Path) -> None:
        """Modules with docstrings should be counted as documented."""
        src = tmp_path / "src"
        src.mkdir()
        # Well-documented module
        (src / "good.py").write_text(
            '"""Good module."""\n\n'
            'def func_a() -> None:\n    """Documented function."""\n    pass\n\n'
            'class ClassA:\n    """Documented class."""\n    pass\n',
            encoding="utf-8",
        )
        # Undocumented module
        (src / "bad.py").write_text(
            "def func_b() -> None:\n    pass\n\nclass ClassB:\n    pass\n",
            encoding="utf-8",
        )

        checker = CompletenessChecker()
        report = checker.check(tmp_path)

        # Find the api_documentation category
        api_cat = next(c for c in report.categories if c.name == "api_documentation")
        # One module is well-documented, one isn't
        assert len(api_cat.present) + len(api_cat.missing) > 0

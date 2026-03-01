"""Tests for scoring.models."""

import pytest
from pydantic import ValidationError

from tapps_mcp.scoring.models import (
    CategoryScore,
    LintIssue,
    ScoreResult,
    SecurityIssue,
    TypeIssue,
)


class TestCategoryScore:
    def test_basic_creation(self):
        cat = CategoryScore(name="security", score=8.0, weight=0.2)
        assert cat.name == "security"
        assert cat.score == 8.0
        assert cat.weight == 0.2
        assert cat.details == {}

    def test_with_details(self):
        cat = CategoryScore(
            name="linting",
            score=9.0,
            weight=0.0,
            details={"issue_count": 3},
        )
        assert cat.details["issue_count"] == 3

    def test_min_score(self):
        cat = CategoryScore(name="test", score=0.0, weight=0.0)
        assert cat.score == 0.0

    def test_max_score(self):
        cat = CategoryScore(name="test", score=10.0, weight=1.0)
        assert cat.score == 10.0

    def test_score_below_min_rejected(self):
        with pytest.raises(ValidationError):
            CategoryScore(name="test", score=-1.0, weight=0.5)

    def test_score_above_max_rejected(self):
        with pytest.raises(ValidationError):
            CategoryScore(name="test", score=10.1, weight=0.5)

    def test_weight_below_min_rejected(self):
        with pytest.raises(ValidationError):
            CategoryScore(name="test", score=5.0, weight=-0.1)

    def test_weight_above_max_rejected(self):
        with pytest.raises(ValidationError):
            CategoryScore(name="test", score=5.0, weight=1.1)


class TestLintIssue:
    def test_basic(self):
        issue = LintIssue(code="E501", message="Line too long", file="test.py", line=10)
        assert issue.code == "E501"
        assert issue.column == 0
        assert issue.severity == "warning"

    def test_with_all_fields(self):
        issue = LintIssue(
            code="F401",
            message="Unused import",
            file="app.py",
            line=1,
            column=5,
            severity="error",
        )
        assert issue.severity == "error"
        assert issue.column == 5


class TestTypeIssue:
    def test_basic(self):
        issue = TypeIssue(file="test.py", line=5, message="Incompatible types")
        assert issue.severity == "error"
        assert issue.error_code is None

    def test_with_error_code(self):
        issue = TypeIssue(
            file="test.py",
            line=10,
            message="Incompatible types",
            error_code="assignment",
            severity="warning",
        )
        assert issue.error_code == "assignment"
        assert issue.severity == "warning"


class TestSecurityIssue:
    def test_basic(self):
        issue = SecurityIssue(code="B101", message="Assert used", file="test.py", line=5)
        assert issue.severity == "medium"
        assert issue.confidence == "medium"
        assert issue.owasp is None

    def test_with_owasp(self):
        issue = SecurityIssue(
            code="B602",
            message="subprocess with shell",
            file="app.py",
            line=10,
            severity="high",
            confidence="high",
            owasp="A03:2021-Injection",
        )
        assert issue.owasp == "A03:2021-Injection"


class TestScoreResult:
    def test_minimal(self):
        result = ScoreResult(
            file_path="test.py",
            categories={},
            overall_score=75.0,
        )
        assert result.file_path == "test.py"
        assert result.lint_issues == []
        assert result.type_issues == []
        assert result.security_issues == []
        assert result.degraded is False
        assert result.missing_tools == []

    def test_with_categories(self):
        cats = {
            "security": CategoryScore(name="security", score=9.0, weight=0.2),
        }
        result = ScoreResult(
            file_path="test.py",
            categories=cats,
            overall_score=90.0,
        )
        assert "security" in result.categories
        assert result.categories["security"].score == 9.0

    def test_overall_score_bounds(self):
        with pytest.raises(ValidationError):
            ScoreResult(
                file_path="test.py",
                categories={},
                overall_score=-1.0,
            )
        with pytest.raises(ValidationError):
            ScoreResult(
                file_path="test.py",
                categories={},
                overall_score=100.1,
            )

    def test_degraded_with_missing_tools(self):
        result = ScoreResult(
            file_path="test.py",
            categories={},
            overall_score=50.0,
            degraded=True,
            missing_tools=["bandit", "radon"],
        )
        assert result.degraded is True
        assert "bandit" in result.missing_tools

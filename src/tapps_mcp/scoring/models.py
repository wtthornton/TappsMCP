"""Pydantic models for the scoring engine."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CategoryScore(BaseModel):
    """Score for a single quality category (0-10 scale)."""

    name: str = Field(description="Category name.")
    score: float = Field(ge=0.0, le=10.0, description="Score on 0-10 scale.")
    weight: float = Field(ge=0.0, le=1.0, description="Weight used for overall calculation.")
    details: dict[str, object] = Field(
        default_factory=dict, description="Category-specific detail."
    )


class LintIssue(BaseModel):
    """A single linting diagnostic from ruff."""

    code: str = Field(description="Rule code, e.g. 'E501'.")
    message: str = Field(description="Human-readable message.")
    file: str = Field(description="File path.")
    line: int = Field(description="Line number.")
    column: int = Field(default=0, description="Column number.")
    severity: str = Field(default="warning", description="error | warning | info.")


class TypeIssue(BaseModel):
    """A single type-checking diagnostic from mypy."""

    file: str = Field(description="File path.")
    line: int = Field(description="Line number.")
    message: str = Field(description="Error message.")
    error_code: str | None = Field(default=None, description="mypy error code.")
    severity: str = Field(default="error", description="error | warning | note.")


class SecurityIssue(BaseModel):
    """A single security finding from bandit or heuristic scan."""

    code: str = Field(description="Rule code, e.g. 'B101'.")
    message: str = Field(description="Description of the issue.")
    file: str = Field(description="File path.")
    line: int = Field(description="Line number.")
    severity: str = Field(default="medium", description="critical | high | medium | low | info.")
    confidence: str = Field(default="medium", description="high | medium | low.")
    owasp: str | None = Field(default=None, description="OWASP category if mapped.")


class ScoreResult(BaseModel):
    """Complete scoring result for a single file."""

    file_path: str = Field(description="Path to the scored file.")
    categories: dict[str, CategoryScore] = Field(
        description="Per-category scores (complexity, security, etc.)."
    )
    overall_score: float = Field(ge=0.0, le=100.0, description="Weighted overall score (0-100).")
    lint_issues: list[LintIssue] = Field(default_factory=list, description="Ruff diagnostics.")
    type_issues: list[TypeIssue] = Field(default_factory=list, description="mypy diagnostics.")
    security_issues: list[SecurityIssue] = Field(
        default_factory=list, description="Bandit / heuristic findings."
    )
    degraded: bool = Field(default=False, description="True if some tools were unavailable.")
    missing_tools: list[str] = Field(
        default_factory=list, description="Names of unavailable external tools."
    )

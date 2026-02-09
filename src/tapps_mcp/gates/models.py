"""Pydantic models for quality gate evaluation."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GateThresholds(BaseModel):
    """Configurable thresholds for quality gate pass/fail."""

    overall_min: float = Field(
        default=70.0,
        ge=0.0,
        le=100.0,
        description="Minimum overall (0-100).",
    )
    security_min: float = Field(
        default=0.0,
        ge=0.0,
        le=10.0,
        description="Minimum security (0-10).",
    )
    maintainability_min: float = Field(
        default=0.0,
        ge=0.0,
        le=10.0,
        description="Minimum maintainability (0-10).",
    )
    complexity_max: float = Field(
        default=10.0,
        ge=0.0,
        le=10.0,
        description="Maximum complexity (0-10).",
    )
    test_coverage_min: float = Field(
        default=0.0,
        ge=0.0,
        le=10.0,
        description="Minimum test-coverage (0-10).",
    )
    performance_min: float = Field(
        default=0.0,
        ge=0.0,
        le=10.0,
        description="Minimum performance (0-10).",
    )


class GateFailure(BaseModel):
    """A single quality gate failure."""

    category: str = Field(description="Category that failed.")
    actual: float = Field(description="Actual score.")
    threshold: float = Field(description="Required threshold.")
    message: str = Field(description="Human-readable failure description.")


class GateResult(BaseModel):
    """Result of quality gate evaluation."""

    passed: bool = Field(description="True if all gates passed.")
    failures: list[GateFailure] = Field(
        default_factory=list,
        description="List of gate failures.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-blocking warnings.",
    )
    scores: dict[str, float] = Field(
        default_factory=dict,
        description="All category scores used.",
    )
    thresholds: GateThresholds = Field(
        default_factory=GateThresholds,
        description="Thresholds applied.",
    )
    preset: str = Field(default="standard", description="Preset name.")

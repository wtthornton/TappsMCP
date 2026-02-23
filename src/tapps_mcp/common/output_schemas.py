"""Structured output schemas for MCP tool responses.

Each model defines the machine-parseable JSON that tools return alongside
human-readable text via the MCP ``structuredContent`` mechanism.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StructuredOutput(BaseModel):
    """Base for all structured outputs."""

    @classmethod
    def to_output_schema(cls) -> dict[str, Any]:
        """Return JSON schema dict for MCP tool registration."""
        return cls.model_json_schema()

    def to_structured_content(self) -> dict[str, Any]:
        """Serialize for MCP structuredContent response."""
        return self.model_dump(mode="json")


class CategoryScoreOutput(BaseModel):
    """Single category score in structured output."""

    name: str
    score: float = Field(ge=0.0, le=10.0)
    weight: float = Field(ge=0.0, le=1.0)
    suggestions: list[str] = Field(default_factory=list)


class ScoreFileOutput(StructuredOutput):
    """Structured output for tapps_score_file."""

    file_path: str
    overall_score: float = Field(ge=0.0, le=100.0)
    categories: dict[str, CategoryScoreOutput] = Field(default_factory=dict)
    lint_issue_count: int = 0
    type_issue_count: int = 0
    security_issue_count: int = 0
    degraded: bool = False
    tool_errors: dict[str, str] = Field(default_factory=dict)
    suggestions: list[str] = Field(default_factory=list)


class GateFailure(BaseModel):
    """A single quality gate failure."""

    category: str
    actual: float
    threshold: float
    message: str = ""


class QualityGateOutput(StructuredOutput):
    """Structured output for tapps_quality_gate."""

    file_path: str
    passed: bool
    preset: str
    overall_score: float = Field(ge=0.0, le=100.0)
    threshold: float = Field(ge=0.0, le=100.0)
    scores: dict[str, float] = Field(default_factory=dict)
    failures: list[GateFailure] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class QuickCheckOutput(StructuredOutput):
    """Structured output for tapps_quick_check."""

    file_path: str
    overall_score: float = Field(ge=0.0, le=100.0)
    gate_passed: bool
    gate_preset: str
    security_passed: bool
    lint_issue_count: int = 0
    security_issue_count: int = 0
    suggestions: list[str] = Field(default_factory=list)


class SecurityFindingOutput(BaseModel):
    """A single security finding in structured output."""

    code: str
    message: str
    file: str
    line: int
    severity: str = "medium"
    confidence: str = "medium"


class SecurityScanOutput(StructuredOutput):
    """Structured output for tapps_security_scan."""

    file_path: str
    passed: bool
    total_issues: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    bandit_available: bool = True
    findings: list[SecurityFindingOutput] = Field(default_factory=list)


class FileValidationResult(BaseModel):
    """Per-file result in validate_changed."""

    file_path: str
    score: float = 0.0
    gate_passed: bool = False
    security_passed: bool = True


class ValidateChangedOutput(StructuredOutput):
    """Structured output for tapps_validate_changed."""

    files: list[FileValidationResult] = Field(default_factory=list)
    overall_passed: bool = False
    total_files: int = 0
    passed_count: int = 0
    failed_count: int = 0


class ImpactOutput(StructuredOutput):
    """Structured output for tapps_impact_analysis."""

    changed_file: str
    change_type: str
    severity: str
    total_affected: int = 0
    direct_dependents: list[str] = Field(default_factory=list)
    test_files: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class ExpertOutput(StructuredOutput):
    """Structured output for tapps_consult_expert."""

    domain: str
    expert_name: str
    answer: str
    confidence: float = Field(ge=0.0, le=1.0)
    sources: list[str] = Field(default_factory=list)


class ChecklistOutput(StructuredOutput):
    """Structured output for tapps_checklist."""

    task_type: str
    complete: bool
    called: list[str] = Field(default_factory=list)
    missing_required: list[str] = Field(default_factory=list)
    missing_recommended: list[str] = Field(default_factory=list)
    total_calls: int = 0


# Registry for looking up output schema by tool name
OUTPUT_SCHEMA_REGISTRY: dict[str, type[StructuredOutput]] = {
    "tapps_score_file": ScoreFileOutput,
    "tapps_quality_gate": QualityGateOutput,
    "tapps_quick_check": QuickCheckOutput,
    "tapps_security_scan": SecurityScanOutput,
    "tapps_validate_changed": ValidateChangedOutput,
    "tapps_impact_analysis": ImpactOutput,
    "tapps_consult_expert": ExpertOutput,
    "tapps_checklist": ChecklistOutput,
}


def get_output_schema(tool_name: str) -> dict[str, Any] | None:
    """Get the JSON output schema for a tool, or None if not registered."""
    cls = OUTPUT_SCHEMA_REGISTRY.get(tool_name)
    if cls is not None:
        return cls.to_output_schema()
    return None

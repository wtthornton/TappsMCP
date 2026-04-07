"""Tests for structured output schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tapps_mcp.common.output_schemas import (
    OUTPUT_SCHEMA_REGISTRY,
    CategoryScoreOutput,
    ChecklistOutput,
    ConfigFindingOutput,
    FileValidationResult,
    GateFailure,
    ImpactOutput,
    ProfileOutput,
    QualityGateOutput,
    QuickCheckOutput,
    ScoreFileOutput,
    SecurityFindingOutput,
    SecurityScanOutput,
    SessionStartOutput,
    StructuredOutput,
    ValidateChangedOutput,
    ValidateConfigOutput,
    get_output_schema,
)

# ---------------------------------------------------------------------------
# StructuredOutput base
# ---------------------------------------------------------------------------


class TestStructuredOutputBase:
    """Tests for the StructuredOutput base class."""

    def test_to_output_schema_returns_dict(self) -> None:
        """to_output_schema returns a dict with 'properties' key."""
        schema = ScoreFileOutput.to_output_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema

    def test_to_structured_content_roundtrip(self) -> None:
        """Create instance, serialize, verify fields present."""
        output = ScoreFileOutput(
            file_path="test.py",
            overall_score=85.0,
        )
        content = output.to_structured_content()
        assert isinstance(content, dict)
        assert content["file_path"] == "test.py"
        assert content["overall_score"] == 85.0
        assert content["categories"] == {}
        assert content["lint_issue_count"] == 0
        assert content["degraded"] is False

    def test_base_class_instantiable(self) -> None:
        """StructuredOutput itself can be instantiated (no required fields)."""
        obj = StructuredOutput()
        schema = obj.to_output_schema()
        assert isinstance(schema, dict)
        content = obj.to_structured_content()
        assert isinstance(content, dict)


# ---------------------------------------------------------------------------
# ScoreFileOutput
# ---------------------------------------------------------------------------


class TestScoreFileOutput:
    """Tests for ScoreFileOutput model."""

    def test_score_file_output_schema(self) -> None:
        """JSON schema has required fields."""
        schema = ScoreFileOutput.to_output_schema()
        props = schema["properties"]
        assert "file_path" in props
        assert "overall_score" in props
        assert "categories" in props
        assert "lint_issue_count" in props
        assert "type_issue_count" in props
        assert "security_issue_count" in props
        assert "degraded" in props
        assert "tool_errors" in props
        assert "suggestions" in props

    def test_score_file_output_serialize(self) -> None:
        """Create with sample data, verify serialization."""
        cat = CategoryScoreOutput(
            name="complexity",
            score=8.5,
            weight=0.2,
            suggestions=["Reduce nesting depth"],
        )
        output = ScoreFileOutput(
            file_path="src/main.py",
            overall_score=72.5,
            categories={"complexity": cat},
            lint_issue_count=3,
            type_issue_count=1,
            security_issue_count=0,
            degraded=False,
            tool_errors={"mypy": "timeout"},
            suggestions=["Add type annotations"],
        )
        content = output.to_structured_content()
        assert content["file_path"] == "src/main.py"
        assert content["overall_score"] == 72.5
        assert content["categories"]["complexity"]["name"] == "complexity"
        assert content["categories"]["complexity"]["score"] == 8.5
        assert content["categories"]["complexity"]["weight"] == 0.2
        assert content["categories"]["complexity"]["suggestions"] == ["Reduce nesting depth"]
        assert content["lint_issue_count"] == 3
        assert content["type_issue_count"] == 1
        assert content["tool_errors"]["mypy"] == "timeout"
        assert content["suggestions"] == ["Add type annotations"]

    def test_score_file_output_validation_score_too_high(self) -> None:
        """Score above 100 raises ValidationError."""
        with pytest.raises(ValidationError):
            ScoreFileOutput(file_path="test.py", overall_score=101.0)

    def test_score_file_output_validation_score_too_low(self) -> None:
        """Score below 0 raises ValidationError."""
        with pytest.raises(ValidationError):
            ScoreFileOutput(file_path="test.py", overall_score=-1.0)

    def test_score_file_output_defaults(self) -> None:
        """Default values are correct."""
        output = ScoreFileOutput(file_path="test.py", overall_score=50.0)
        assert output.categories == {}
        assert output.lint_issue_count == 0
        assert output.type_issue_count == 0
        assert output.security_issue_count == 0
        assert output.degraded is False
        assert output.tool_errors == {}
        assert output.suggestions == []


# ---------------------------------------------------------------------------
# QualityGateOutput
# ---------------------------------------------------------------------------


class TestQualityGateOutput:
    """Tests for QualityGateOutput model."""

    def test_quality_gate_output_schema(self) -> None:
        """Verify schema has expected properties."""
        schema = QualityGateOutput.to_output_schema()
        props = schema["properties"]
        assert "file_path" in props
        assert "passed" in props
        assert "preset" in props
        assert "overall_score" in props
        assert "threshold" in props
        assert "scores" in props
        assert "failures" in props
        assert "warnings" in props
        assert "suggestions" in props

    def test_quality_gate_output_passed(self) -> None:
        """Passed scenario with no failures."""
        output = QualityGateOutput(
            file_path="clean.py",
            passed=True,
            preset="standard",
            overall_score=85.0,
            threshold=70.0,
            scores={"complexity": 9.0, "security": 8.5},
        )
        content = output.to_structured_content()
        assert content["passed"] is True
        assert content["failures"] == []
        assert content["overall_score"] == 85.0
        assert content["threshold"] == 70.0
        assert content["scores"]["complexity"] == 9.0

    def test_quality_gate_output_failed(self) -> None:
        """Failed scenario with failures populated."""
        failure = GateFailure(
            category="security",
            actual=4.0,
            threshold=7.0,
            message="Security score below threshold",
        )
        output = QualityGateOutput(
            file_path="risky.py",
            passed=False,
            preset="strict",
            overall_score=55.0,
            threshold=80.0,
            failures=[failure],
            warnings=["Consider adding tests"],
        )
        content = output.to_structured_content()
        assert content["passed"] is False
        assert len(content["failures"]) == 1
        assert content["failures"][0]["category"] == "security"
        assert content["failures"][0]["actual"] == 4.0
        assert content["failures"][0]["threshold"] == 7.0
        assert content["failures"][0]["message"] == "Security score below threshold"
        assert content["warnings"] == ["Consider adding tests"]

    def test_quality_gate_score_validation(self) -> None:
        """Score out of range raises ValidationError."""
        with pytest.raises(ValidationError):
            QualityGateOutput(
                file_path="x.py",
                passed=False,
                preset="standard",
                overall_score=150.0,
                threshold=70.0,
            )


# ---------------------------------------------------------------------------
# QuickCheckOutput
# ---------------------------------------------------------------------------


class TestQuickCheckOutput:
    """Tests for QuickCheckOutput model."""

    def test_quick_check_output_schema(self) -> None:
        """Verify schema has expected properties."""
        schema = QuickCheckOutput.to_output_schema()
        props = schema["properties"]
        assert "file_path" in props
        assert "overall_score" in props
        assert "gate_passed" in props
        assert "gate_preset" in props
        assert "security_passed" in props
        assert "lint_issue_count" in props
        assert "security_issue_count" in props
        assert "suggestions" in props
        assert "recurring_quality_memory_events" in props

    def test_quick_check_output_serialize(self) -> None:
        """Verify all fields serialize correctly."""
        output = QuickCheckOutput(
            file_path="app.py",
            overall_score=78.0,
            gate_passed=True,
            gate_preset="standard",
            security_passed=True,
            lint_issue_count=2,
            security_issue_count=0,
            suggestions=["Fix whitespace"],
        )
        content = output.to_structured_content()
        assert content["file_path"] == "app.py"
        assert content["overall_score"] == 78.0
        assert content["gate_passed"] is True
        assert content["gate_preset"] == "standard"
        assert content["security_passed"] is True
        assert content["lint_issue_count"] == 2
        assert content["security_issue_count"] == 0
        assert content["suggestions"] == ["Fix whitespace"]

    def test_quick_check_score_validation(self) -> None:
        """Score out of range raises ValidationError."""
        with pytest.raises(ValidationError):
            QuickCheckOutput(
                file_path="x.py",
                overall_score=-5.0,
                gate_passed=False,
                gate_preset="standard",
                security_passed=True,
            )


# ---------------------------------------------------------------------------
# SecurityScanOutput
# ---------------------------------------------------------------------------


class TestSecurityScanOutput:
    """Tests for SecurityScanOutput model."""

    def test_security_scan_output_schema(self) -> None:
        """Verify schema has expected properties."""
        schema = SecurityScanOutput.to_output_schema()
        props = schema["properties"]
        assert "file_path" in props
        assert "passed" in props
        assert "total_issues" in props
        assert "critical_count" in props
        assert "high_count" in props
        assert "medium_count" in props
        assert "low_count" in props
        assert "bandit_available" in props
        assert "findings" in props

    def test_security_scan_output_with_findings(self) -> None:
        """Findings list properly serialized."""
        finding = SecurityFindingOutput(
            code="B101",
            message="Use of assert detected",
            file="test.py",
            line=42,
            severity="low",
            confidence="high",
        )
        output = SecurityScanOutput(
            file_path="test.py",
            passed=False,
            total_issues=1,
            low_count=1,
            findings=[finding],
        )
        content = output.to_structured_content()
        assert content["passed"] is False
        assert content["total_issues"] == 1
        assert content["low_count"] == 1
        assert len(content["findings"]) == 1
        assert content["findings"][0]["code"] == "B101"
        assert content["findings"][0]["line"] == 42
        assert content["findings"][0]["severity"] == "low"
        assert content["findings"][0]["confidence"] == "high"

    def test_security_scan_output_clean(self) -> None:
        """Clean scan with no findings."""
        output = SecurityScanOutput(
            file_path="safe.py",
            passed=True,
            total_issues=0,
        )
        content = output.to_structured_content()
        assert content["passed"] is True
        assert content["findings"] == []
        assert content["bandit_available"] is True


# ---------------------------------------------------------------------------
# ValidateChangedOutput
# ---------------------------------------------------------------------------


class TestValidateChangedOutput:
    """Tests for ValidateChangedOutput model."""

    def test_validate_changed_output_schema(self) -> None:
        """Verify schema has expected properties."""
        schema = ValidateChangedOutput.to_output_schema()
        props = schema["properties"]
        assert "files" in props
        assert "overall_passed" in props
        assert "total_files" in props
        assert "passed_count" in props
        assert "failed_count" in props

    def test_validate_changed_output_summary(self) -> None:
        """total_files, passed_count, failed_count are correct."""
        results = [
            FileValidationResult(file_path="a.py", score=85.0, gate_passed=True),
            FileValidationResult(file_path="b.py", score=55.0, gate_passed=False),
            FileValidationResult(
                file_path="c.py",
                score=90.0,
                gate_passed=True,
                security_passed=False,
            ),
        ]
        output = ValidateChangedOutput(
            files=results,
            overall_passed=False,
            total_files=3,
            passed_count=2,
            failed_count=1,
        )
        content = output.to_structured_content()
        assert content["total_files"] == 3
        assert content["passed_count"] == 2
        assert content["failed_count"] == 1
        assert len(content["files"]) == 3
        assert content["files"][0]["file_path"] == "a.py"
        assert content["files"][1]["gate_passed"] is False
        assert content["files"][2]["security_passed"] is False

    def test_validate_changed_output_empty(self) -> None:
        """Empty file list defaults."""
        output = ValidateChangedOutput()
        content = output.to_structured_content()
        assert content["files"] == []
        assert content["overall_passed"] is False
        assert content["total_files"] == 0


# ---------------------------------------------------------------------------
# ValidateConfigOutput
# ---------------------------------------------------------------------------


class TestValidateConfigOutput:
    """Tests for ValidateConfigOutput model."""

    def test_validate_config_output_schema(self) -> None:
        """Verify schema has expected properties."""
        schema = ValidateConfigOutput.to_output_schema()
        props = schema["properties"]
        assert "file_path" in props
        assert "config_type" in props
        assert "valid" in props
        assert "finding_count" in props
        assert "findings" in props
        assert "suggestions" in props

    def test_validate_config_output_serialize(self) -> None:
        """Full serialization with findings."""
        output = ValidateConfigOutput(
            file_path="Dockerfile",
            config_type="dockerfile",
            valid=True,
            finding_count=1,
            critical_count=0,
            warning_count=1,
            findings=[
                ConfigFindingOutput(
                    severity="warning",
                    message="Avoid latest tag",
                    line=1,
                    category="best_practice",
                ),
            ],
            suggestions=["Pin a specific version"],
        )
        content = output.to_structured_content()
        assert content["file_path"] == "Dockerfile"
        assert content["config_type"] == "dockerfile"
        assert content["valid"] is True
        assert content["finding_count"] == 1
        assert len(content["findings"]) == 1
        assert content["findings"][0]["severity"] == "warning"
        assert content["suggestions"] == ["Pin a specific version"]


# ---------------------------------------------------------------------------
# ImpactOutput
# ---------------------------------------------------------------------------


class TestImpactOutput:
    """Tests for ImpactOutput model."""

    def test_impact_output_schema(self) -> None:
        """Verify schema has expected properties."""
        schema = ImpactOutput.to_output_schema()
        props = schema["properties"]
        assert "changed_file" in props
        assert "change_type" in props
        assert "severity" in props
        assert "total_affected" in props
        assert "direct_dependents" in props
        assert "test_files" in props
        assert "recommendations" in props

    def test_impact_output_serialize(self) -> None:
        """Full serialization with populated fields."""
        output = ImpactOutput(
            changed_file="core/engine.py",
            change_type="modified",
            severity="high",
            total_affected=5,
            direct_dependents=["api/handler.py", "cli/main.py"],
            test_files=["tests/test_engine.py"],
            recommendations=["Run full test suite"],
        )
        content = output.to_structured_content()
        assert content["changed_file"] == "core/engine.py"
        assert content["change_type"] == "modified"
        assert content["severity"] == "high"
        assert content["total_affected"] == 5
        assert len(content["direct_dependents"]) == 2
        assert len(content["test_files"]) == 1
        assert content["recommendations"] == ["Run full test suite"]


# ---------------------------------------------------------------------------
# ExpertOutput
# ---------------------------------------------------------------------------


class _TestExpertOutput_REMOVED:
    """Tests for ExpertOutput model."""

    def test_expert_output_schema(self) -> None:
        """Verify schema has expected properties."""
        schema = ExpertOutput.to_output_schema()
        props = schema["properties"]
        assert "domain" in props
        assert "expert_name" in props
        assert "answer" in props
        assert "confidence" in props
        assert "sources" in props

    def test_expert_output_serialize(self) -> None:
        """Full serialization with sources."""
        output = ExpertOutput(
            domain="security",
            expert_name="Security Expert",
            answer="Use parameterized queries to prevent SQL injection.",
            confidence=0.92,
            sources=["owasp-top10.md", "sql-injection.md"],
        )
        content = output.to_structured_content()
        assert content["domain"] == "security"
        assert content["expert_name"] == "Security Expert"
        assert content["confidence"] == 0.92
        assert len(content["sources"]) == 2

    def test_expert_output_confidence_validation(self) -> None:
        """Confidence out of [0, 1] range raises ValidationError."""
        with pytest.raises(ValidationError):
            ExpertOutput(
                domain="testing",
                expert_name="Test Expert",
                answer="Write more tests.",
                confidence=1.5,
            )
        with pytest.raises(ValidationError):
            ExpertOutput(
                domain="testing",
                expert_name="Test Expert",
                answer="Write more tests.",
                confidence=-0.1,
            )


# ---------------------------------------------------------------------------
# ChecklistOutput
# ---------------------------------------------------------------------------


class TestChecklistOutput:
    """Tests for ChecklistOutput model."""

    def test_checklist_output_schema(self) -> None:
        """Verify schema has expected properties."""
        schema = ChecklistOutput.to_output_schema()
        props = schema["properties"]
        assert "task_type" in props
        assert "complete" in props
        assert "called" in props
        assert "missing_required" in props
        assert "missing_recommended" in props
        assert "total_calls" in props

    def test_checklist_output_complete(self) -> None:
        """Complete checklist scenario."""
        output = ChecklistOutput(
            task_type="feature",
            complete=True,
            called=["tapps_score_file", "tapps_quality_gate"],
            missing_required=[],
            missing_recommended=[],
            total_calls=5,
        )
        content = output.to_structured_content()
        assert content["complete"] is True
        assert content["task_type"] == "feature"
        assert len(content["called"]) == 2
        assert content["missing_required"] == []
        assert content["total_calls"] == 5

    def test_checklist_output_incomplete(self) -> None:
        """Incomplete checklist with missing tools."""
        output = ChecklistOutput(
            task_type="bugfix",
            complete=False,
            called=["tapps_score_file"],
            missing_required=["tapps_quality_gate"],
            missing_recommended=["tapps_security_scan"],
            total_calls=1,
        )
        content = output.to_structured_content()
        assert content["complete"] is False
        assert content["missing_required"] == ["tapps_quality_gate"]
        assert content["missing_recommended"] == ["tapps_security_scan"]


# ---------------------------------------------------------------------------
# CategoryScoreOutput
# ---------------------------------------------------------------------------


class TestCategoryScoreOutput:
    """Tests for CategoryScoreOutput model."""

    def test_category_score_output(self) -> None:
        """Validate score bounds."""
        cat = CategoryScoreOutput(name="complexity", score=7.5, weight=0.15)
        assert cat.name == "complexity"
        assert cat.score == 7.5
        assert cat.weight == 0.15

    def test_category_score_output_score_too_high(self) -> None:
        """Score above 10 raises ValidationError."""
        with pytest.raises(ValidationError):
            CategoryScoreOutput(name="x", score=11.0, weight=0.1)

    def test_category_score_output_score_too_low(self) -> None:
        """Score below 0 raises ValidationError."""
        with pytest.raises(ValidationError):
            CategoryScoreOutput(name="x", score=-0.1, weight=0.1)

    def test_category_score_output_weight_too_high(self) -> None:
        """Weight above 1.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            CategoryScoreOutput(name="x", score=5.0, weight=1.1)

    def test_category_score_output_weight_too_low(self) -> None:
        """Weight below 0.0 raises ValidationError."""
        with pytest.raises(ValidationError):
            CategoryScoreOutput(name="x", score=5.0, weight=-0.1)

    def test_category_score_output_suggestions(self) -> None:
        """Suggestions list works."""
        cat = CategoryScoreOutput(
            name="test",
            score=5.0,
            weight=0.1,
            suggestions=["Add unit tests", "Improve coverage"],
        )
        assert len(cat.suggestions) == 2
        assert cat.suggestions[0] == "Add unit tests"

    def test_category_score_output_boundary_values(self) -> None:
        """Boundary values (0 and max) are accepted."""
        cat_low = CategoryScoreOutput(name="min", score=0.0, weight=0.0)
        assert cat_low.score == 0.0
        assert cat_low.weight == 0.0
        cat_high = CategoryScoreOutput(name="max", score=10.0, weight=1.0)
        assert cat_high.score == 10.0
        assert cat_high.weight == 1.0


# ---------------------------------------------------------------------------
# GateFailure
# ---------------------------------------------------------------------------


class TestGateFailure:
    """Tests for GateFailure model."""

    def test_gate_failure_model(self) -> None:
        """All fields serialize correctly."""
        failure = GateFailure(
            category="maintainability",
            actual=5.5,
            threshold=7.0,
            message="Below minimum threshold",
        )
        data = failure.model_dump(mode="json")
        assert data["category"] == "maintainability"
        assert data["actual"] == 5.5
        assert data["threshold"] == 7.0
        assert data["message"] == "Below minimum threshold"

    def test_gate_failure_default_message(self) -> None:
        """Default message is empty string."""
        failure = GateFailure(category="security", actual=3.0, threshold=6.0)
        assert failure.message == ""

    def test_gate_failure_in_schema(self) -> None:
        """GateFailure appears in QualityGateOutput schema."""
        schema = QualityGateOutput.to_output_schema()
        # GateFailure should be referenced via $defs or definitions
        defs = schema.get("$defs", schema.get("definitions", {}))
        assert "GateFailure" in defs


# ---------------------------------------------------------------------------
# SecurityFindingOutput
# ---------------------------------------------------------------------------


class TestSecurityFindingOutput:
    """Tests for SecurityFindingOutput model."""

    def test_security_finding_serialize(self) -> None:
        """All fields serialize correctly."""
        finding = SecurityFindingOutput(
            code="B102",
            message="exec used",
            file="danger.py",
            line=10,
            severity="high",
            confidence="medium",
        )
        data = finding.model_dump(mode="json")
        assert data["code"] == "B102"
        assert data["message"] == "exec used"
        assert data["file"] == "danger.py"
        assert data["line"] == 10
        assert data["severity"] == "high"
        assert data["confidence"] == "medium"

    def test_security_finding_defaults(self) -> None:
        """Default severity and confidence are medium."""
        finding = SecurityFindingOutput(code="B001", message="test", file="f.py", line=1)
        assert finding.severity == "medium"
        assert finding.confidence == "medium"


# ---------------------------------------------------------------------------
# FileValidationResult
# ---------------------------------------------------------------------------


class TestFileValidationResult:
    """Tests for FileValidationResult model."""

    def test_file_validation_result_defaults(self) -> None:
        """Default values are correct."""
        result = FileValidationResult(file_path="x.py")
        assert result.score == 0.0
        assert result.gate_passed is False
        assert result.security_passed is True

    def test_file_validation_result_serialize(self) -> None:
        """All fields serialize correctly."""
        result = FileValidationResult(
            file_path="module.py",
            score=88.5,
            gate_passed=True,
            security_passed=True,
        )
        data = result.model_dump(mode="json")
        assert data["file_path"] == "module.py"
        assert data["score"] == 88.5
        assert data["gate_passed"] is True


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestRegistry:
    """Tests for the output schema registry.

    The registry is intentionally empty (v0.4.1) because the MCP SDK
    validates the full return dict against the declared outputSchema,
    but our tools return an envelope that doesn't match the inner schemas.
    Schema wiring is disabled until handlers migrate to CallToolResult.
    """

    def test_get_output_schema_known_tool(self) -> None:
        """Returns None for all tools while registry is disabled."""
        schema = get_output_schema("tapps_score_file")
        assert schema is None

    def test_get_output_schema_unknown_tool(self) -> None:
        """Returns None for unknown tool name."""
        result = get_output_schema("tapps_nonexistent_tool")
        assert result is None

    def test_registry_is_empty(self) -> None:
        """Registry is intentionally empty to prevent MCP output validation errors."""
        assert len(OUTPUT_SCHEMA_REGISTRY) == 0

    def test_schema_models_still_importable(self) -> None:
        """Schema model classes are preserved for structuredContent key usage."""
        from tapps_mcp.common.output_schemas import (
            ChecklistOutput,
            ImpactOutput,
            ProfileOutput,
            QualityGateOutput,
            QuickCheckOutput,
            ScoreFileOutput,
            SecurityScanOutput,
            SessionStartOutput,
            ValidateChangedOutput,
            ValidateConfigOutput,
        )

        models = [
            ScoreFileOutput,
            QualityGateOutput,
            QuickCheckOutput,
            SecurityScanOutput,
            ValidateChangedOutput,
            ValidateConfigOutput,
            ImpactOutput,
            ChecklistOutput,
            ProfileOutput,
            SessionStartOutput,
        ]
        for cls in models:
            schema = cls.to_output_schema()
            assert isinstance(schema, dict), f"{cls.__name__} schema is not a dict"
            assert "properties" in schema, f"{cls.__name__} lacks 'properties'"


# ---------------------------------------------------------------------------
# ResearchOutput
# ---------------------------------------------------------------------------


class _TestResearchOutput_REMOVED:
    """Tests for ResearchOutput model."""

    def test_research_output_schema(self) -> None:
        """Verify schema has expected properties."""
        schema = ResearchOutput.to_output_schema()
        props = schema["properties"]
        assert "domain" in props
        assert "expert_name" in props
        assert "answer" in props
        assert "confidence" in props
        assert "sources" in props
        assert "docs_supplemented" in props
        assert "docs_library" in props
        assert "docs_topic" in props

    def test_research_output_serialize(self) -> None:
        """Full serialization with docs supplemented."""
        output = ResearchOutput(
            domain="security",
            expert_name="Security Expert",
            answer="Use parameterized queries.",
            confidence=0.85,
            sources=["sql-injection.md"],
            docs_supplemented=True,
            docs_library="sqlalchemy",
            docs_topic="queries",
        )
        content = output.to_structured_content()
        assert content["domain"] == "security"
        assert content["expert_name"] == "Security Expert"
        assert content["confidence"] == 0.85
        assert content["docs_supplemented"] is True
        assert content["docs_library"] == "sqlalchemy"
        assert content["docs_topic"] == "queries"

    def test_research_output_defaults(self) -> None:
        """Default values are correct."""
        output = ResearchOutput(
            domain="testing",
            expert_name="Test Expert",
            answer="Write more tests.",
            confidence=0.7,
        )
        assert output.docs_supplemented is False
        assert output.docs_library is None
        assert output.docs_topic is None
        assert output.sources == []

    def test_research_output_confidence_validation(self) -> None:
        """Confidence out of range raises ValidationError."""
        with pytest.raises(ValidationError):
            ResearchOutput(
                domain="x",
                expert_name="X",
                answer="y",
                confidence=1.5,
            )


# ---------------------------------------------------------------------------
# ProfileOutput
# ---------------------------------------------------------------------------


class TestProfileOutput:
    """Tests for ProfileOutput model."""

    def test_profile_output_schema(self) -> None:
        """Verify schema has expected properties."""
        schema = ProfileOutput.to_output_schema()
        props = schema["properties"]
        assert "project_root" in props
        assert "project_type" in props
        assert "project_type_confidence" in props
        assert "has_ci" in props
        assert "has_docker" in props
        assert "has_tests" in props
        assert "test_frameworks" in props
        assert "package_managers" in props
        assert "quality_recommendations" in props

    def test_profile_output_serialize(self) -> None:
        """Full serialization with populated fields."""
        output = ProfileOutput(
            project_root="/home/user/project",
            project_type="library",
            project_type_confidence=0.92,
            has_ci=True,
            has_docker=True,
            has_tests=True,
            test_frameworks=["pytest"],
            package_managers=["uv"],
            quality_recommendations=["Add type hints"],
        )
        content = output.to_structured_content()
        assert content["project_root"] == "/home/user/project"
        assert content["project_type"] == "library"
        assert content["project_type_confidence"] == 0.92
        assert content["has_ci"] is True
        assert content["has_docker"] is True
        assert content["has_tests"] is True
        assert content["test_frameworks"] == ["pytest"]
        assert content["package_managers"] == ["uv"]
        assert content["quality_recommendations"] == ["Add type hints"]

    def test_profile_output_defaults(self) -> None:
        """Default values are correct."""
        output = ProfileOutput(
            project_root="/tmp",
            project_type="unknown",
            project_type_confidence=0.5,
        )
        assert output.has_ci is False
        assert output.has_docker is False
        assert output.has_tests is False
        assert output.test_frameworks == []
        assert output.package_managers == []
        assert output.quality_recommendations == []


# ---------------------------------------------------------------------------
# SessionStartOutput
# ---------------------------------------------------------------------------


class TestSessionStartOutput:
    """Tests for SessionStartOutput model."""

    def test_session_start_output_schema(self) -> None:
        """Verify schema has expected properties."""
        schema = SessionStartOutput.to_output_schema()
        props = schema["properties"]
        assert "server_version" in props
        assert "project_root" in props
        assert "project_type" in props
        assert "quality_preset" in props
        assert "installed_checkers" in props
        assert "checker_environment" in props
        assert "has_ci" in props
        assert "has_docker" in props
        assert "has_tests" in props

    def test_session_start_output_serialize(self) -> None:
        """Full serialization with populated fields."""
        output = SessionStartOutput(
            server_version="0.10.0",
            project_root="/home/user/project",
            project_type="mcp-server",
            quality_preset="strict",
            installed_checkers=["ruff", "mypy", "bandit"],
            has_ci=True,
            has_docker=False,
            has_tests=True,
        )
        content = output.to_structured_content()
        assert content["server_version"] == "0.10.0"
        assert content["project_root"] == "/home/user/project"
        assert content["project_type"] == "mcp-server"
        assert content["quality_preset"] == "strict"
        assert content["installed_checkers"] == ["ruff", "mypy", "bandit"]
        assert content["checker_environment"] == "mcp_server"
        assert content["has_ci"] is True
        assert content["has_docker"] is False
        assert content["has_tests"] is True

    def test_session_start_output_defaults(self) -> None:
        """Default values are correct."""
        output = SessionStartOutput(
            server_version="1.0.0",
            project_root="/tmp",
        )
        assert output.project_type is None
        assert output.quality_preset == "standard"
        assert output.installed_checkers == []
        assert output.checker_environment == "mcp_server"
        assert output.has_ci is False
        assert output.has_docker is False
        assert output.has_tests is False

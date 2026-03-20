"""Integration tests for tapps-core cross-module wiring.

Tests that core infrastructure modules integrate correctly without mocking.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]


class TestExpertConsultationPipeline:
    """Verify the full expert consultation pipeline works end-to-end."""

    def test_consult_expert_returns_result_with_default_detection(self, tmp_path: Path) -> None:
        """consult_expert auto-detects domain and returns a valid result."""
        from tapps_core.experts.engine import consult_expert

        result = consult_expert("What testing strategy should I use for a REST API?")

        assert result is not None
        assert result.domain  # Non-empty domain
        assert result.expert_id  # Non-empty expert ID
        assert result.expert_name  # Non-empty expert name
        assert result.answer  # Non-empty answer
        assert 0.0 <= result.confidence <= 1.0

    def test_consult_expert_with_explicit_domain(self) -> None:
        """consult_expert works when given an explicit domain."""
        from tapps_core.experts.engine import consult_expert

        result = consult_expert(
            "How should I handle SQL injection prevention?",
            domain="security",
        )

        assert result is not None
        assert result.domain == "security"
        assert result.answer

    def test_consult_expert_returns_sources(self) -> None:
        """consult_expert populates sources from the knowledge base."""
        from tapps_core.experts.engine import consult_expert

        result = consult_expert(
            "What are best practices for unit testing?",
            domain="testing-strategies",
        )

        assert result is not None
        # Sources list may be empty if no knowledge files match, but field exists
        assert isinstance(result.sources, list)
        assert isinstance(result.chunks_used, int)


class TestDomainDetectionPipeline:
    """Verify domain detection feeds into expert consultation."""

    def test_domain_detector_finds_security_domain(self) -> None:
        """DomainDetector correctly identifies security-related questions."""
        from tapps_core.experts.domain_detector import DomainDetector

        mappings = DomainDetector.detect_from_question(
            "How should I handle SQL injection prevention?"
        )

        assert len(mappings) > 0
        # Security should be among the top detected domains
        domain_names = [m.domain for m in mappings]
        assert "security" in domain_names

    def test_domain_detector_finds_testing_domain(self) -> None:
        """DomainDetector correctly identifies testing-related questions."""
        from tapps_core.experts.domain_detector import DomainDetector

        mappings = DomainDetector.detect_from_question(
            "How do I write pytest fixtures for integration tests?"
        )

        assert len(mappings) > 0
        domain_names = [m.domain for m in mappings]
        assert "testing-strategies" in domain_names

    def test_detected_domains_flow_into_consult(self) -> None:
        """Domains from detection can be passed to consult_expert."""
        from tapps_core.experts.domain_detector import DomainDetector
        from tapps_core.experts.engine import consult_expert

        mappings = DomainDetector.detect_from_question_merged(
            "How should I handle SQL injection prevention?"
        )
        assert len(mappings) > 0

        # Use the top detected domain for consultation
        result = consult_expert(
            "SQL injection prevention",
            domain=mappings[0].domain,
        )
        assert result is not None
        assert result.answer


class TestPathValidatorIntegration:
    """Verify path validator works with real filesystem operations."""

    def test_validates_real_file_within_root(self, tmp_path: Path) -> None:
        """Path validator accepts files within project root."""
        from tapps_core.security.path_validator import PathValidator

        validator = PathValidator(project_root=tmp_path)

        # Create a file within project root
        test_file = tmp_path / "src" / "main.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("print('hello')\n", encoding="utf-8")

        # Validation should pass for files within root
        validated = validator.validate_path(test_file)
        assert validated == test_file.resolve()

    def test_validates_nested_directory_structure(self, tmp_path: Path) -> None:
        """Path validator works with deeply nested paths."""
        from tapps_core.security.path_validator import PathValidator

        validator = PathValidator(project_root=tmp_path)

        deep_file = tmp_path / "a" / "b" / "c" / "d" / "test.py"
        deep_file.parent.mkdir(parents=True, exist_ok=True)
        deep_file.write_text("x = 1\n", encoding="utf-8")

        validated = validator.validate_path(deep_file)
        assert validated == deep_file.resolve()

    def test_rejects_path_traversal(self, tmp_path: Path) -> None:
        """Path validator rejects traversal attempts."""
        from tapps_core.common.exceptions import PathValidationError
        from tapps_core.security.path_validator import PathValidator

        validator = PathValidator(project_root=tmp_path)

        with pytest.raises(PathValidationError, match="traversal"):
            validator.validate_path(tmp_path / ".." / ".." / "etc" / "passwd")

    def test_validates_relative_path_against_root(self, tmp_path: Path) -> None:
        """Relative paths are resolved against project root."""
        from tapps_core.security.path_validator import PathValidator

        validator = PathValidator(project_root=tmp_path)

        test_file = tmp_path / "src" / "app.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("app = True\n", encoding="utf-8")

        # Relative path should resolve correctly
        validated = validator.validate_path(Path("src/app.py"))
        assert validated == test_file.resolve()

    def test_rejects_nonexistent_file_when_must_exist(self, tmp_path: Path) -> None:
        """Path validator raises FileNotFoundError for missing files."""
        from tapps_core.security.path_validator import PathValidator

        validator = PathValidator(project_root=tmp_path)

        with pytest.raises(FileNotFoundError):
            validator.validate_path(tmp_path / "does_not_exist.py", must_exist=True)

    def test_accepts_nonexistent_file_for_write(self, tmp_path: Path) -> None:
        """Path validator accepts nonexistent paths for write operations."""
        from tapps_core.security.path_validator import PathValidator

        validator = PathValidator(project_root=tmp_path)

        # write_path does not need to exist
        validated = validator.validate_write_path(tmp_path / "new_file.py")
        assert validated == (tmp_path / "new_file.py").resolve()


class TestSettingsIntegration:
    """Verify settings load correctly with real filesystem."""

    def test_load_settings_with_minimal_project(self, tmp_path: Path) -> None:
        """Settings load successfully for a minimal project directory."""
        from tapps_core.config.settings import load_settings

        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\n', encoding="utf-8"
        )

        settings = load_settings(project_root=tmp_path)
        assert settings is not None
        assert settings.project_root == tmp_path

    def test_settings_scoring_weights_are_valid(self, tmp_path: Path) -> None:
        """Scoring weights from default settings sum to approximately 1.0."""
        from tapps_core.config.settings import load_settings

        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\n', encoding="utf-8"
        )

        settings = load_settings(project_root=tmp_path)
        weights = settings.scoring_weights
        total = (
            weights.complexity
            + weights.security
            + weights.maintainability
            + weights.test_coverage
            + weights.performance
            + weights.structure
            + weights.devex
        )
        # Weights should sum to ~1.0 (allow small float tolerance)
        assert 0.95 <= total <= 1.05

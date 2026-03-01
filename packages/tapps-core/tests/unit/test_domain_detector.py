"""Unit tests for tapps_core.experts.domain_detector."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tapps_core.experts.domain_detector import DomainDetector

if TYPE_CHECKING:
    from pathlib import Path


class TestDetectFromQuestion:
    """Tests for DomainDetector.detect_from_question."""

    def test_security_question(self) -> None:
        results = DomainDetector.detect_from_question("How do I prevent SQL injection in my API?")
        assert results
        assert results[0].domain == "security"

    def test_performance_question(self) -> None:
        results = DomainDetector.detect_from_question(
            "My application has high latency and low throughput"
        )
        assert results
        domains = [r.domain for r in results]
        assert "performance-optimization" in domains

    def test_testing_question(self) -> None:
        results = DomainDetector.detect_from_question(
            "How should I structure my pytest unit tests for better coverage?"
        )
        assert results
        domains = [r.domain for r in results]
        assert "testing-strategies" in domains

    def test_database_question(self) -> None:
        results = DomainDetector.detect_from_question(
            "What is the best way to design a PostgreSQL schema?"
        )
        assert results
        domains = [r.domain for r in results]
        assert "database-data-management" in domains

    def test_empty_question_returns_empty(self) -> None:
        results = DomainDetector.detect_from_question("")
        assert results == []

    def test_unrelated_question_may_return_empty(self) -> None:
        results = DomainDetector.detect_from_question("What is the meaning of life?")
        # May or may not match — just ensure no crash.
        assert isinstance(results, list)

    def test_results_sorted_by_confidence(self) -> None:
        results = DomainDetector.detect_from_question(
            "How to set up Kubernetes deployment with monitoring and logging?"
        )
        if len(results) > 1:
            for i in range(len(results) - 1):
                assert results[i].confidence >= results[i + 1].confidence

    def test_multi_domain_question(self) -> None:
        results = DomainDetector.detect_from_question("Security testing for my REST API endpoints")
        domains = {r.domain for r in results}
        # Should match multiple domains.
        assert len(domains) >= 2

    def test_signals_contain_keywords(self) -> None:
        results = DomainDetector.detect_from_question("How to fix xss vulnerability?")
        assert results
        assert any("keyword:" in s for s in results[0].signals)

    def test_ruff_rules_routes_to_code_quality(self) -> None:
        results = DomainDetector.detect_from_question("How do I configure ruff rules?")
        assert results
        assert results[0].domain == "code-quality-analysis"

    def test_memory_persistence_routes_to_agent_learning(self) -> None:
        results = DomainDetector.detect_from_question(
            "What is the best memory persistence pattern?"
        )
        assert results
        domains = [r.domain for r in results]
        assert "agent-learning" in domains

    def test_bandit_routes_to_code_quality(self) -> None:
        results = DomainDetector.detect_from_question(
            "How do I run bandit for security scanning?"
        )
        assert results
        domains = [r.domain for r in results]
        assert "code-quality-analysis" in domains

    def test_quality_gate_routes_to_code_quality(self) -> None:
        results = DomainDetector.detect_from_question(
            "How do I set up a quality gate for my project?"
        )
        assert results
        assert results[0].domain == "code-quality-analysis"

    def test_memory_decay_routes_to_agent_learning(self) -> None:
        results = DomainDetector.detect_from_question(
            "How does memory decay work in agent systems?"
        )
        assert results
        domains = [r.domain for r in results]
        assert "agent-learning" in domains

    def test_shared_memory_routes_to_agent_learning(self) -> None:
        results = DomainDetector.detect_from_question(
            "How to implement shared memory for multi-agent teams?"
        )
        assert results
        domains = [r.domain for r in results]
        assert "agent-learning" in domains

    def test_no_false_positive_on_existing_questions(self) -> None:
        """Verify that adding new keywords doesn't cause false positives on
        existing well-established questions."""
        # SQL injection should still route to security, not code-quality
        results = DomainDetector.detect_from_question("How do I prevent SQL injection?")
        assert results
        assert results[0].domain == "security"

        # Kubernetes should still include cloud-infrastructure as a top match
        results = DomainDetector.detect_from_question("How to deploy on Kubernetes?")
        assert results
        domains = [r.domain for r in results]
        assert "cloud-infrastructure" in domains


class TestDetectFromProject:
    """Tests for DomainDetector.detect_from_project."""

    def test_empty_directory(self, tmp_path: Path) -> None:
        results = DomainDetector.detect_from_project(tmp_path)
        assert results == []

    def test_dockerfile_detected(self, tmp_path: Path) -> None:
        (tmp_path / "Dockerfile").write_text("FROM python:3.12")
        results = DomainDetector.detect_from_project(tmp_path)
        domains = [r.domain for r in results]
        assert "cloud-infrastructure" in domains

    def test_github_actions_detected(self, tmp_path: Path) -> None:
        workflows = tmp_path / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text("name: CI")
        results = DomainDetector.detect_from_project(tmp_path)
        domains = [r.domain for r in results]
        assert "development-workflow" in domains

    def test_pyproject_detected(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        results = DomainDetector.detect_from_project(tmp_path)
        domains = [r.domain for r in results]
        assert "code-quality-analysis" in domains

    def test_conftest_detected(self, tmp_path: Path) -> None:
        (tmp_path / "conftest.py").write_text("import pytest")
        results = DomainDetector.detect_from_project(tmp_path)
        domains = [r.domain for r in results]
        assert "testing-strategies" in domains

    def test_multiple_signals(self, tmp_path: Path) -> None:
        (tmp_path / "Dockerfile").write_text("FROM python:3.12")
        (tmp_path / "Makefile").write_text("all:\n\techo hi")
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
        results = DomainDetector.detect_from_project(tmp_path)
        # Should detect at least 2 different domains.
        domains = {r.domain for r in results}
        assert len(domains) >= 2

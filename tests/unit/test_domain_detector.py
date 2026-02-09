"""Unit tests for tapps_mcp.experts.domain_detector."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tapps_mcp.experts.domain_detector import DomainDetector

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

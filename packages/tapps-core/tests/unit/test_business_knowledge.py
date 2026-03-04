"""Tests for business expert knowledge directory utilities."""
from __future__ import annotations

from pathlib import Path

import pytest

from tapps_core.experts.business_knowledge import (
    KnowledgeValidationResult,
    get_business_knowledge_path,
    scaffold_knowledge_directory,
    validate_business_knowledge,
)
from tapps_core.experts.models import ExpertConfig


def _make_expert(
    domain: str = "home-automation",
    *,
    name: str = "Home Automation Expert",
    expert_id: str = "expert-home-automation",
    knowledge_dir: str | None = None,
    is_builtin: bool = False,
) -> ExpertConfig:
    """Helper to build an ExpertConfig for testing."""
    return ExpertConfig(
        expert_id=expert_id,
        expert_name=name,
        primary_domain=domain,
        knowledge_dir=knowledge_dir,
        is_builtin=is_builtin,
    )


class TestGetBusinessKnowledgePath:
    """Tests for get_business_knowledge_path."""

    def test_default_domain(self, tmp_path: Path) -> None:
        expert = _make_expert(domain="home-automation")
        result = get_business_knowledge_path(tmp_path, expert)
        assert result == tmp_path / ".tapps-mcp" / "knowledge" / "home-automation"

    def test_knowledge_dir_override(self, tmp_path: Path) -> None:
        expert = _make_expert(domain="home-automation", knowledge_dir="custom-ha")
        result = get_business_knowledge_path(tmp_path, expert)
        assert result == tmp_path / ".tapps-mcp" / "knowledge" / "custom-ha"

    def test_domain_slug_sanitization(self, tmp_path: Path) -> None:
        """Domains with special chars are sanitized via sanitize_domain_for_path."""
        expert = _make_expert(domain="My Custom Domain")
        result = get_business_knowledge_path(tmp_path, expert)
        # sanitize_domain_for_path lowercases and replaces spaces with hyphens
        assert result == tmp_path / ".tapps-mcp" / "knowledge" / "my-custom-domain"


class TestValidateBusinessKnowledge:
    """Tests for validate_business_knowledge."""

    def test_valid_directory_with_md_files(self, tmp_path: Path) -> None:
        expert = _make_expert()
        knowledge_dir = tmp_path / ".tapps-mcp" / "knowledge" / "home-automation"
        knowledge_dir.mkdir(parents=True)
        (knowledge_dir / "guide.md").write_text("# Guide\nContent here.")

        result = validate_business_knowledge(tmp_path, [expert])

        assert result.valid == ["home-automation"]
        assert result.missing == []
        assert result.empty == []
        assert result.warnings == []

    def test_missing_directory(self, tmp_path: Path) -> None:
        expert = _make_expert()
        result = validate_business_knowledge(tmp_path, [expert])

        assert result.valid == []
        assert result.missing == ["home-automation"]
        assert result.empty == []
        assert len(result.warnings) == 1
        assert "missing" in result.warnings[0].lower()

    def test_empty_directory(self, tmp_path: Path) -> None:
        expert = _make_expert()
        knowledge_dir = tmp_path / ".tapps-mcp" / "knowledge" / "home-automation"
        knowledge_dir.mkdir(parents=True)
        # Directory exists but has no .md files
        (knowledge_dir / "notes.txt").write_text("Not a markdown file.")

        result = validate_business_knowledge(tmp_path, [expert])

        assert result.valid == []
        assert result.missing == []
        assert result.empty == ["home-automation"]
        assert len(result.warnings) == 1
        assert "empty" in result.warnings[0].lower()

    def test_multiple_experts_mixed(self, tmp_path: Path) -> None:
        expert_valid = _make_expert(domain="valid-domain", expert_id="e1", name="Valid")
        expert_missing = _make_expert(domain="missing-domain", expert_id="e2", name="Missing")
        expert_empty = _make_expert(domain="empty-domain", expert_id="e3", name="Empty")

        # Set up valid directory
        valid_dir = tmp_path / ".tapps-mcp" / "knowledge" / "valid-domain"
        valid_dir.mkdir(parents=True)
        (valid_dir / "doc.md").write_text("# Doc")

        # Set up empty directory
        empty_dir = tmp_path / ".tapps-mcp" / "knowledge" / "empty-domain"
        empty_dir.mkdir(parents=True)

        result = validate_business_knowledge(
            tmp_path, [expert_valid, expert_missing, expert_empty]
        )

        assert result.valid == ["valid-domain"]
        assert result.missing == ["missing-domain"]
        assert result.empty == ["empty-domain"]
        assert len(result.warnings) == 2

    def test_empty_experts_list(self, tmp_path: Path) -> None:
        result = validate_business_knowledge(tmp_path, [])

        assert result == KnowledgeValidationResult()
        assert result.valid == []
        assert result.missing == []
        assert result.empty == []
        assert result.warnings == []


class TestScaffoldKnowledgeDirectory:
    """Tests for scaffold_knowledge_directory."""

    def test_scaffold_creates_directory_and_readme(self, tmp_path: Path) -> None:
        expert = _make_expert()
        result_path = scaffold_knowledge_directory(tmp_path, expert)

        assert result_path.exists()
        assert result_path.is_dir()
        readme = result_path / "README.md"
        assert readme.exists()
        content = readme.read_text(encoding="utf-8")
        assert expert.expert_name in content
        assert expert.primary_domain in content
        assert "one topic per file" in content.lower()
        assert "50 KB" in content

    def test_scaffold_idempotent(self, tmp_path: Path) -> None:
        expert = _make_expert()
        scaffold_knowledge_directory(tmp_path, expert)

        readme = get_business_knowledge_path(tmp_path, expert) / "README.md"
        original_content = readme.read_text(encoding="utf-8")

        # Write custom content
        readme.write_text("Custom content that should not be overwritten.")

        # Re-scaffold
        scaffold_knowledge_directory(tmp_path, expert)

        # README should NOT be overwritten
        assert readme.read_text(encoding="utf-8") == "Custom content that should not be overwritten."
        assert readme.read_text(encoding="utf-8") != original_content

    def test_scaffold_with_knowledge_dir_override(self, tmp_path: Path) -> None:
        expert = _make_expert(knowledge_dir="my-custom-dir")
        result_path = scaffold_knowledge_directory(tmp_path, expert)

        assert result_path == tmp_path / ".tapps-mcp" / "knowledge" / "my-custom-dir"
        assert (result_path / "README.md").exists()

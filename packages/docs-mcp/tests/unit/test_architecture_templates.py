"""Tests for architecture templates, doc index, and cross-ref validation (Epic 85)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from docs_mcp.generators.doc_index import DocIndexGenerator
from docs_mcp.generators.purpose import PurposeGenerator
from docs_mcp.validators.cross_ref import CrossRefValidator
from tests.helpers import make_settings


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_pyproject(root: Path, **kwargs: Any) -> None:
    deps = kwargs.get("dependencies", [])
    deps_str = ", ".join(f'"{d}"' for d in deps)
    content = f"""
[project]
name = "{kwargs.get("name", "my-project")}"
version = "1.0.0"
description = "{kwargs.get("description", "A test project")}"
dependencies = [{deps_str}]
"""
    if "python_version" in kwargs:
        content += f'\nrequires-python = ">={kwargs["python_version"]}"\n'
    _write(root / "pyproject.toml", content)


# ---------------------------------------------------------------------------
# PurposeGenerator (Epic 85.1)
# ---------------------------------------------------------------------------


class TestPurposeGenerator:
    def test_basic_generation(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path, description="A quality tool")
        gen = PurposeGenerator()
        result = gen.generate(tmp_path)

        assert result.content
        assert not result.degraded
        assert "purpose" in result.sections
        assert "principles" in result.sections
        assert "decisions" in result.sections
        assert "audience" in result.sections
        assert "quality_attributes" in result.sections
        assert "my-project" in result.content
        assert "A quality tool" in result.content

    def test_infers_principles_from_deps(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path, dependencies=["fastapi", "pydantic", "structlog"])
        gen = PurposeGenerator()
        result = gen.generate(tmp_path)

        assert "API-first" in result.content
        assert "Data validation" in result.content
        assert "Structured logging" in result.content

    def test_detects_monorepo(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path)
        _make_pyproject(tmp_path / "packages" / "core", name="core")
        _make_pyproject(tmp_path / "packages" / "api", name="api")

        gen = PurposeGenerator()
        result = gen.generate(tmp_path)

        assert "Monorepo" in result.content

    def test_detects_docker(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path)
        _write(tmp_path / "Dockerfile", "FROM python:3.12")

        gen = PurposeGenerator()
        result = gen.generate(tmp_path)

        assert "Docker" in result.content

    def test_detects_quality_attributes(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path)
        (tmp_path / "tests").mkdir()
        (tmp_path / "docs").mkdir()

        gen = PurposeGenerator()
        result = gen.generate(tmp_path)

        assert "Testability" in result.content
        assert "Maintainability" in result.content

    def test_invalid_root_degraded(self, tmp_path: Path) -> None:
        gen = PurposeGenerator()
        result = gen.generate(tmp_path / "nonexistent_xyz")

        assert result.degraded
        assert result.content == ""

    def test_custom_project_name(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path)
        gen = PurposeGenerator()
        result = gen.generate(tmp_path, project_name="CustomName")

        assert "CustomName" in result.content

    def test_audience_table(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path)
        gen = PurposeGenerator()
        result = gen.generate(tmp_path)

        assert "Developers" in result.content
        assert "Operators" in result.content
        assert "Users" in result.content


# ---------------------------------------------------------------------------
# DocIndexGenerator (Epic 85.2)
# ---------------------------------------------------------------------------


class TestDocIndexGenerator:
    def test_basic_scan(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# My Project\n\nWelcome to the project.")
        _write(tmp_path / "docs" / "guide.md", "# Getting Started\n\nSetup instructions.")

        gen = DocIndexGenerator()
        result = gen.generate(tmp_path)

        assert result.total_files == 2
        assert result.content
        assert "My Project" in result.content
        assert "Getting Started" in result.content

    def test_categorization(self, tmp_path: Path) -> None:
        _write(tmp_path / "docs" / "api-reference.md", "# API Reference\n\nEndpoints.")
        _write(tmp_path / "docs" / "deployment.md", "# Deployment\n\nHow to deploy.")
        _write(tmp_path / "CHANGELOG.md", "# Changelog\n\n## 1.0.0")

        gen = DocIndexGenerator()
        result = gen.generate(tmp_path)

        assert "API Reference" in result.categories
        assert "Operations" in result.categories
        assert "Release" in result.categories

    def test_specific_doc_dirs(self, tmp_path: Path) -> None:
        _write(tmp_path / "docs" / "guide.md", "# Guide")
        _write(tmp_path / "other" / "notes.md", "# Notes")

        gen = DocIndexGenerator()
        result = gen.generate(tmp_path, doc_dirs=["docs"])

        assert result.total_files == 1

    def test_empty_project(self, tmp_path: Path) -> None:
        gen = DocIndexGenerator()
        result = gen.generate(tmp_path)

        assert result.total_files == 0

    def test_invalid_root(self, tmp_path: Path) -> None:
        gen = DocIndexGenerator()
        result = gen.generate(tmp_path / "nonexistent_xyz")

        assert result.total_files == 0

    def test_skips_hidden_dirs(self, tmp_path: Path) -> None:
        _write(tmp_path / ".git" / "config.md", "# Git Config")
        _write(tmp_path / "docs" / "real.md", "# Real Doc")

        gen = DocIndexGenerator()
        result = gen.generate(tmp_path)

        assert result.total_files == 1

    def test_word_count(self, tmp_path: Path) -> None:
        _write(tmp_path / "doc.md", "one two three four five")

        gen = DocIndexGenerator()
        result = gen.generate(tmp_path)

        assert result.entries[0].word_count == 5

    def test_title_extraction_fallback(self, tmp_path: Path) -> None:
        _write(tmp_path / "my-cool-doc.md", "No heading here, just content.")

        gen = DocIndexGenerator()
        result = gen.generate(tmp_path)

        assert result.entries[0].title == "My Cool Doc"

    def test_links_relative_to_output_path_in_subdir(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# Root\n\nRoot doc.")
        _write(tmp_path / "docs" / "guides" / "foo.md", "# Foo\n\nGuide.")

        gen = DocIndexGenerator()
        result = gen.generate(tmp_path, output_path="docs/INDEX.md")

        # Index lives at docs/INDEX.md; link to README.md should use "..".
        assert "(../README.md)" in result.content
        # Link to docs/guides/foo.md should be just guides/foo.md.
        assert "(guides/foo.md)" in result.content
        # The broken "doubled" form must NOT appear.
        assert "(docs/guides/foo.md)" not in result.content
        assert "(docs/README.md)" not in result.content

    def test_links_unchanged_when_output_path_at_project_root(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# Root\n\nRoot doc.")
        _write(tmp_path / "docs" / "guide.md", "# Guide\n\nGuide.")

        gen = DocIndexGenerator()
        result = gen.generate(tmp_path, output_path="INDEX.md")

        # Project-root index: links stay project-root-relative.
        assert "(README.md)" in result.content
        assert "(docs/guide.md)" in result.content

    def test_links_legacy_when_output_path_omitted(self, tmp_path: Path) -> None:
        _write(tmp_path / "docs" / "guide.md", "# Guide\n\nGuide.")

        gen = DocIndexGenerator()
        result = gen.generate(tmp_path)

        # Back-compat: no output_path => project-root-relative targets.
        assert "(docs/guide.md)" in result.content


# ---------------------------------------------------------------------------
# CrossRefValidator (Epic 85.4)
# ---------------------------------------------------------------------------


class TestCrossRefValidator:
    def test_no_issues(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# README\n\nSee [guide](docs/guide.md).")
        _write(tmp_path / "docs" / "guide.md", "# Guide\n\nBack to [README](../README.md).")

        validator = CrossRefValidator()
        report = validator.validate(tmp_path)

        broken = [i for i in report.issues if i.issue_type == "broken_ref"]
        assert len(broken) == 0
        assert report.score >= 80

    def test_broken_ref(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# README\n\nSee [guide](docs/nonexistent.md).")

        validator = CrossRefValidator()
        report = validator.validate(tmp_path)

        assert report.broken_count == 1
        assert any(i.issue_type == "broken_ref" for i in report.issues)

    def test_orphan_detection(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# README\n\nMain page.")
        _write(tmp_path / "docs" / "orphan.md", "# Orphan\n\nNobody links here.")

        validator = CrossRefValidator()
        report = validator.validate(tmp_path)

        assert report.orphan_count >= 1
        orphans = [i for i in report.issues if i.issue_type == "orphan"]
        assert any("orphan.md" in i.source_file for i in orphans)

    def test_entry_points_not_orphans(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# README\n\nMain page.")
        _write(tmp_path / "CHANGELOG.md", "# Changelog\n\n## 1.0.0")

        validator = CrossRefValidator()
        report = validator.validate(tmp_path)

        orphans = [i for i in report.issues if i.issue_type == "orphan"]
        assert not any("README" in i.source_file for i in orphans)
        assert not any("CHANGELOG" in i.source_file for i in orphans)

    def test_missing_backlink(self, tmp_path: Path) -> None:
        _write(tmp_path / "docs" / "a.md", "# A\n\nSee [B](b.md).")
        _write(tmp_path / "docs" / "b.md", "# B\n\nNo link back to A.")

        validator = CrossRefValidator()
        report = validator.validate(tmp_path)

        assert report.missing_backlink_count >= 1

    def test_backlink_check_disabled(self, tmp_path: Path) -> None:
        _write(tmp_path / "docs" / "a.md", "# A\n\nSee [B](b.md).")
        _write(tmp_path / "docs" / "b.md", "# B\n\nNo link back.")

        validator = CrossRefValidator()
        report = validator.validate(tmp_path, check_backlinks=False)

        assert report.missing_backlink_count == 0

    def test_empty_project(self, tmp_path: Path) -> None:
        validator = CrossRefValidator()
        report = validator.validate(tmp_path)

        assert report.total_files == 0
        assert report.score == 100

    def test_invalid_root(self, tmp_path: Path) -> None:
        validator = CrossRefValidator()
        report = validator.validate(tmp_path / "nonexistent_xyz")

        assert report.score == 100

    def test_skips_external_urls(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "doc.md",
            "# Doc\n\n[Google](https://google.com) and [local](other.md).",
        )

        validator = CrossRefValidator()
        report = validator.validate(tmp_path)

        # Only the local ref should be counted, not the external URL
        broken = [i for i in report.issues if i.issue_type == "broken_ref"]
        assert all("google.com" not in i.target for i in broken)

    def test_skips_code_blocks(self, tmp_path: Path) -> None:
        content = "# Doc\n\n```\n[not a link](fake.md)\n```\n\nReal content."
        _write(tmp_path / "doc.md", content)

        validator = CrossRefValidator()
        report = validator.validate(tmp_path)

        broken = [i for i in report.issues if i.issue_type == "broken_ref"]
        assert not any("fake.md" in i.target for i in broken)

    def test_per_file_mean_not_dominated_by_one_bad_file(self, tmp_path: Path) -> None:
        # One file with 100 broken refs (all pointing at nonexistent targets).
        broken_links = "\n".join(f"[x{i}](missing/file_{i}.md)" for i in range(100))
        _write(tmp_path / "docs" / "bad.md", f"# Bad\n\n{broken_links}\n")
        # One clean file that links back to bad.md so bad.md isn't an orphan.
        _write(tmp_path / "docs" / "clean.md", "# Clean\n\nSee [bad](bad.md).")
        # Entry point so we don't pile up orphan penalties.
        _write(tmp_path / "README.md", "# README\n\nSee [clean](docs/clean.md).")

        validator = CrossRefValidator()
        report = validator.validate(tmp_path)

        assert report.broken_count == 100
        # Legacy score is tanked (-60 cap on broken refs + orphan/backlink).
        assert report.legacy_score <= 40
        # New score: one bad file out of ~3 files-with-refs, contributes
        # ~1/N to mean broken ratio, so score should be well above legacy.
        assert report.score > report.legacy_score + 20
        assert report.scoring_method == "per_file_mean"

    def test_group_by_source_omits_issues_list(self, tmp_path: Path) -> None:
        broken_links = "\n".join(f"[x{i}](missing/file_{i}.md)" for i in range(10))
        _write(tmp_path / "docs" / "index.md", f"# Index\n\n{broken_links}\n")
        _write(tmp_path / "README.md", "# README\n\nSee [index](docs/index.md).")

        validator = CrossRefValidator()
        report = validator.validate(tmp_path, group_by_source=True)

        assert report.issues == []
        assert len(report.groups) >= 1
        top = next(g for g in report.groups if g.source_file.endswith("index.md"))
        assert top.broken_count == 10
        assert len(top.sample_targets) <= 5
        # Counts still correct even with flat issues suppressed.
        assert report.broken_count == 10

    def test_pattern_detection_surfaces_shared_prefix(self, tmp_path: Path) -> None:
        # 6 broken refs all sharing the 'wrongbase/' prefix.
        broken_links = "\n".join(f"[x{i}](wrongbase/page_{i}.md)" for i in range(6))
        _write(tmp_path / "docs" / "index.md", f"# Index\n\n{broken_links}\n")
        _write(tmp_path / "README.md", "# README\n\nSee [index](docs/index.md).")

        validator = CrossRefValidator()
        report = validator.validate(tmp_path)

        assert len(report.patterns) >= 1
        # Prefix is resolved relative to source file (docs/index.md), so the
        # shared prefix should start with 'docs/wrongbase'.
        top_prefix = report.patterns[0].prefix
        assert "wrongbase" in top_prefix
        assert report.patterns[0].count >= 5
        assert len(report.patterns[0].example_targets) <= 5

    def test_backward_compat_fields_present(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# README\n\nSee [missing](does_not_exist.md).")

        validator = CrossRefValidator()
        report = validator.validate(tmp_path)

        assert hasattr(report, "broken_count")
        assert hasattr(report, "score")
        assert hasattr(report, "legacy_score")
        assert report.scoring_method == "per_file_mean"

    def test_single_file_all_broken_scores_zero(self, tmp_path: Path) -> None:
        # One file, every ref broken. Score must be 0 (not misleadingly high).
        broken_links = "\n".join(f"[x{i}](missing_{i}.md)" for i in range(5))
        _write(tmp_path / "doc.md", f"# Doc\n\n{broken_links}\n")

        validator = CrossRefValidator()
        report = validator.validate(tmp_path)

        assert report.score == 0


# ---------------------------------------------------------------------------
# MCP tool handler tests
# ---------------------------------------------------------------------------


class TestDocsGeneratePurposeTool:
    async def test_success(self, tmp_path: Path) -> None:
        _make_pyproject(tmp_path, dependencies=["fastapi"])
        from docs_mcp.server_gen_tools import docs_generate_purpose

        with patch("docs_mcp.server_gen_tools._get_settings") as mock_settings:
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_generate_purpose(project_root=str(tmp_path))

        assert result["success"] is True
        assert "purpose" in result["data"]["sections"]
        assert result["data"]["content_length"] > 0

    async def test_invalid_root(self, tmp_path: Path) -> None:
        from docs_mcp.server_gen_tools import docs_generate_purpose

        bad_path = str(tmp_path / "nonexistent_xyz")
        result = await docs_generate_purpose(project_root=bad_path)
        assert result["success"] is False


class TestDocsGenerateDocIndexTool:
    async def test_success(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# Test Project")
        from docs_mcp.server_gen_tools import docs_generate_doc_index

        with patch("docs_mcp.server_gen_tools._get_settings") as mock_settings:
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_generate_doc_index(project_root=str(tmp_path))

        assert result["success"] is True
        assert result["data"]["total_files"] >= 1

    async def test_invalid_root(self, tmp_path: Path) -> None:
        from docs_mcp.server_gen_tools import docs_generate_doc_index

        bad_path = str(tmp_path / "nonexistent_xyz")
        result = await docs_generate_doc_index(project_root=bad_path)
        assert result["success"] is False


class TestDocsCheckCrossRefsTool:
    async def test_success(self, tmp_path: Path) -> None:
        _write(tmp_path / "README.md", "# README\n\nSee [guide](guide.md).")
        _write(tmp_path / "guide.md", "# Guide\n\nContent.")
        from docs_mcp.server_val_tools import docs_check_cross_refs

        with patch("docs_mcp.server_val_tools._get_settings") as mock_settings:
            mock_settings.return_value = make_settings(tmp_path)
            result = await docs_check_cross_refs(project_root=str(tmp_path))

        assert result["success"] is True
        assert "score" in result["data"]

    async def test_invalid_root(self, tmp_path: Path) -> None:
        from docs_mcp.server_val_tools import docs_check_cross_refs

        bad_path = str(tmp_path / "nonexistent_xyz")
        result = await docs_check_cross_refs(project_root=bad_path)
        assert result["success"] is False

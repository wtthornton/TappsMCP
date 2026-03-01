"""Tests for docs_project_scan tool."""

from __future__ import annotations

from pathlib import Path

import pytest


class TestDocsProjectScan:
    @pytest.mark.asyncio
    async def test_project_scan_returns_success(self, sample_project: Path) -> None:
        from docs_mcp.server import docs_project_scan

        result = await docs_project_scan(project_root=str(sample_project))
        assert result["success"] is True
        assert result["tool"] == "docs_project_scan"

    @pytest.mark.asyncio
    async def test_project_scan_counts_docs(self, docs_project: Path) -> None:
        from docs_mcp.server import docs_project_scan

        result = await docs_project_scan(project_root=str(docs_project))
        data = result["data"]

        # docs_project has: README.md, CHANGELOG.md, CONTRIBUTING.md,
        # LICENSE (no .md ext so won't be found by _DOC_EXTENSIONS),
        # docs/api.md, docs/guide.md
        assert data["total_docs"] >= 5

    @pytest.mark.asyncio
    async def test_project_scan_categorizes_readme(
        self, sample_project: Path
    ) -> None:
        from docs_mcp.server import docs_project_scan

        result = await docs_project_scan(project_root=str(sample_project))
        categories = result["data"]["categories"]

        assert len(categories["readme"]) >= 1
        assert categories["readme"][0]["path"] == "README.md"

    @pytest.mark.asyncio
    async def test_project_scan_categorizes_changelog(
        self, docs_project: Path
    ) -> None:
        from docs_mcp.server import docs_project_scan

        result = await docs_project_scan(project_root=str(docs_project))
        categories = result["data"]["categories"]

        assert len(categories["changelog"]) >= 1

    @pytest.mark.asyncio
    async def test_project_scan_completeness_score(
        self, docs_project: Path
    ) -> None:
        from docs_mcp.server import docs_project_scan

        result = await docs_project_scan(project_root=str(docs_project))
        score = result["data"]["completeness_score"]

        # docs_project has README, CHANGELOG, CONTRIBUTING, guide, api docs, docs dir
        # Should have a reasonable score
        assert isinstance(score, int)
        assert score > 0

    @pytest.mark.asyncio
    async def test_project_scan_completeness_score_minimal(
        self, sample_project: Path
    ) -> None:
        from docs_mcp.server import docs_project_scan

        result = await docs_project_scan(project_root=str(sample_project))
        score_minimal = result["data"]["completeness_score"]

        # Minimal project (only README) should score lower
        result_full = await docs_project_scan(project_root=str(sample_project))
        assert score_minimal == result_full["data"]["completeness_score"]
        # At least README gives 15 points
        assert score_minimal >= 15

    @pytest.mark.asyncio
    async def test_project_scan_critical_docs(self, docs_project: Path) -> None:
        from docs_mcp.server import docs_project_scan

        result = await docs_project_scan(project_root=str(docs_project))
        critical = result["data"]["critical_docs"]

        assert "README.md" in critical
        assert "LICENSE" in critical
        assert "CHANGELOG.md" in critical
        assert "CONTRIBUTING.md" in critical

        assert critical["README.md"]["exists"] is True
        assert critical["CHANGELOG.md"]["exists"] is True
        assert critical["CONTRIBUTING.md"]["exists"] is True

    @pytest.mark.asyncio
    async def test_project_scan_empty_project(self, tmp_path: Path) -> None:
        from docs_mcp.server import docs_project_scan

        (tmp_path / ".git").mkdir()
        (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")

        result = await docs_project_scan(project_root=str(tmp_path))
        data = result["data"]

        assert data["total_docs"] == 0
        assert data["completeness_score"] == 0
        assert len(data["recommendations"]) > 0

    @pytest.mark.asyncio
    async def test_project_scan_data_shape(self, sample_project: Path) -> None:
        from docs_mcp.server import docs_project_scan

        result = await docs_project_scan(project_root=str(sample_project))
        data = result["data"]

        assert "total_docs" in data
        assert "total_size_bytes" in data
        assert "categories" in data
        assert "completeness_score" in data
        assert "critical_docs" in data
        assert "recommendations" in data

    @pytest.mark.asyncio
    async def test_project_scan_records_call(self, sample_project: Path) -> None:
        from docs_mcp.server import _tool_calls, docs_project_scan

        await docs_project_scan(project_root=str(sample_project))
        assert _tool_calls.get("docs_project_scan", 0) >= 1

    @pytest.mark.asyncio
    async def test_project_scan_total_size(self, docs_project: Path) -> None:
        from docs_mcp.server import docs_project_scan

        result = await docs_project_scan(project_root=str(docs_project))
        assert result["data"]["total_size_bytes"] > 0


class TestCategorizeDoc:
    def test_categorize_readme(self, tmp_path: Path) -> None:
        from docs_mcp.server import _categorize_doc

        p = tmp_path / "README.md"
        assert _categorize_doc(p, tmp_path) == "readme"

    def test_categorize_changelog(self, tmp_path: Path) -> None:
        from docs_mcp.server import _categorize_doc

        p = tmp_path / "CHANGELOG.md"
        assert _categorize_doc(p, tmp_path) == "changelog"

    def test_categorize_contributing(self, tmp_path: Path) -> None:
        from docs_mcp.server import _categorize_doc

        p = tmp_path / "CONTRIBUTING.md"
        assert _categorize_doc(p, tmp_path) == "contributing"

    def test_categorize_license(self, tmp_path: Path) -> None:
        from docs_mcp.server import _categorize_doc

        p = tmp_path / "LICENSE"
        assert _categorize_doc(p, tmp_path) == "license"

    def test_categorize_security(self, tmp_path: Path) -> None:
        from docs_mcp.server import _categorize_doc

        p = tmp_path / "SECURITY.md"
        assert _categorize_doc(p, tmp_path) == "security"

    def test_categorize_api_docs(self, tmp_path: Path) -> None:
        from docs_mcp.server import _categorize_doc

        docs = tmp_path / "docs"
        docs.mkdir()
        p = docs / "api.md"
        assert _categorize_doc(p, tmp_path) == "api_docs"

    def test_categorize_guide(self, tmp_path: Path) -> None:
        from docs_mcp.server import _categorize_doc

        docs = tmp_path / "docs"
        docs.mkdir()
        p = docs / "guide.md"
        assert _categorize_doc(p, tmp_path) == "guides"

    def test_categorize_other(self, tmp_path: Path) -> None:
        from docs_mcp.server import _categorize_doc

        p = tmp_path / "notes.md"
        assert _categorize_doc(p, tmp_path) == "other"

    def test_categorize_adr(self, tmp_path: Path) -> None:
        from docs_mcp.server import _categorize_doc

        adr_dir = tmp_path / "adr"
        adr_dir.mkdir()
        p = adr_dir / "001-use-postgres.md"
        assert _categorize_doc(p, tmp_path) == "adr"


class TestDetectDocFormat:
    def test_markdown(self) -> None:
        from docs_mcp.server import _detect_doc_format

        assert _detect_doc_format(Path("test.md")) == "markdown"

    def test_rst(self) -> None:
        from docs_mcp.server import _detect_doc_format

        assert _detect_doc_format(Path("test.rst")) == "restructuredtext"

    def test_plain(self) -> None:
        from docs_mcp.server import _detect_doc_format

        assert _detect_doc_format(Path("test.txt")) == "plain"

    def test_unknown(self) -> None:
        from docs_mcp.server import _detect_doc_format

        assert _detect_doc_format(Path("test.html")) == "unknown"


class TestDetectProjectName:
    def test_from_pyproject(self, sample_project: Path) -> None:
        from docs_mcp.server import _detect_project_name

        assert _detect_project_name(sample_project) == "test-project"

    def test_fallback_to_dirname(self, tmp_path: Path) -> None:
        from docs_mcp.server import _detect_project_name

        # No pyproject.toml, falls back to directory name
        assert _detect_project_name(tmp_path) == tmp_path.name


class TestScanDocFiles:
    def test_scan_finds_readme(self, sample_project: Path) -> None:
        from docs_mcp.server import _scan_doc_files

        docs = _scan_doc_files(sample_project)
        paths = [d["path"] for d in docs]
        assert "README.md" in paths

    def test_scan_skips_git_dir(self, tmp_path: Path) -> None:
        from docs_mcp.server import _scan_doc_files

        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config.md").write_text("git config", encoding="utf-8")
        (tmp_path / "README.md").write_text("# Hello", encoding="utf-8")

        docs = _scan_doc_files(tmp_path)
        paths = [d["path"] for d in docs]
        assert "README.md" in paths
        assert not any(".git" in p for p in paths)

    def test_scan_nonexistent_dir(self) -> None:
        from docs_mcp.server import _scan_doc_files

        docs = _scan_doc_files(Path("/nonexistent/path/abc123"))
        assert docs == []

    def test_scan_returns_doc_metadata(self, sample_project: Path) -> None:
        from docs_mcp.server import _scan_doc_files

        docs = _scan_doc_files(sample_project)
        assert len(docs) > 0

        doc = docs[0]
        assert "path" in doc
        assert "size_bytes" in doc
        assert "last_modified" in doc
        assert "format" in doc
        assert "category" in doc

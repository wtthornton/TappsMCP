"""Tests for documentation validators and their MCP tool wrappers.

Covers DriftDetector, CompletenessChecker, LinkChecker, FreshnessChecker,
and the four MCP tools: docs_check_drift, docs_check_completeness,
docs_check_links, docs_check_freshness.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# DriftDetector tests
# ---------------------------------------------------------------------------


class TestDriftDetectorEmpty:
    """DriftDetector on empty or nonexistent projects."""

    def test_empty_project_returns_zero_drift(self, tmp_path: Path) -> None:
        from docs_mcp.validators.drift import DriftDetector

        report = DriftDetector().check(tmp_path)
        assert report.total_items == 0
        assert report.checked_files == 0
        assert report.drift_score == 0.0

    def test_nonexistent_root_returns_empty_report(self) -> None:
        from docs_mcp.validators.drift import DriftDetector

        report = DriftDetector().check(Path("/nonexistent/xyz"))
        assert report.total_items == 0
        assert report.items == []


class TestDriftDetectorCodeOnly:
    """DriftDetector when there is code but no documentation."""

    def test_code_without_docs_produces_drift(self, tmp_path: Path) -> None:
        (tmp_path / "app.py").write_text(
            '"""App module."""\n\ndef process() -> None:\n    pass\n',
            encoding="utf-8",
        )
        from docs_mcp.validators.drift import DriftDetector

        report = DriftDetector().check(tmp_path)
        assert report.total_items > 0
        assert report.drift_score > 0.0

    def test_drift_items_have_file_path(self, tmp_path: Path) -> None:
        (tmp_path / "service.py").write_text(
            '"""Service."""\n\nclass Handler:\n    """Handle."""\n    pass\n',
            encoding="utf-8",
        )
        from docs_mcp.validators.drift import DriftDetector

        report = DriftDetector().check(tmp_path)
        assert report.total_items > 0
        assert all(item.file_path for item in report.items)


class TestDriftDetectorFullDocs:
    """DriftDetector when docs reference all public names."""

    def test_no_drift_when_docs_cover_names(self, tmp_path: Path) -> None:
        (tmp_path / "calc.py").write_text(
            '"""Calc."""\n\ndef add() -> int:\n    """Add."""\n    return 0\n',
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text(
            "# Calc\n\nThe `add` function adds numbers.\n",
            encoding="utf-8",
        )
        from docs_mcp.validators.drift import DriftDetector

        report = DriftDetector().check(tmp_path)
        assert report.total_items == 0

    def test_partial_coverage_produces_partial_drift(self, tmp_path: Path) -> None:
        (tmp_path / "utils.py").write_text(
            '"""Utils."""\n\n'
            "def alpha() -> None:\n    pass\n\n"
            "def beta() -> None:\n    pass\n",
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text(
            "# Utils\n\nUse `alpha` for processing.\n",
            encoding="utf-8",
        )
        from docs_mcp.validators.drift import DriftDetector

        report = DriftDetector().check(tmp_path)
        # beta is undocumented
        assert report.total_items > 0
        descriptions = " ".join(item.description for item in report.items)
        assert "beta" in descriptions


class TestDriftDetectorMixed:
    """DriftDetector with mixed scenarios."""

    def test_doc_dirs_restricts_search(self, tmp_path: Path) -> None:
        (tmp_path / "api.py").write_text(
            '"""API."""\n\ndef endpoint() -> None:\n    pass\n',
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text(
            "# Project\n\nUse `endpoint` for requests.\n",
            encoding="utf-8",
        )
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "guide.md").write_text("# Guide\n\nGeneral info.\n", encoding="utf-8")

        from docs_mcp.validators.drift import DriftDetector

        # Without restriction: README covers endpoint -> no drift
        report_all = DriftDetector().check(tmp_path)
        # With restriction to docs/ only: endpoint not mentioned -> drift
        report_docs = DriftDetector().check(tmp_path, doc_dirs=["docs"])
        assert report_docs.total_items > 0

    def test_severity_error_when_code_newer_than_docs(self, tmp_path: Path) -> None:
        readme = tmp_path / "README.md"
        readme.write_text("# Project\n", encoding="utf-8")
        old_time = time.time() - 86400 * 60
        os.utime(readme, (old_time, old_time))

        (tmp_path / "main.py").write_text(
            '"""Main."""\n\ndef new_feature() -> None:\n    pass\n',
            encoding="utf-8",
        )
        from docs_mcp.validators.drift import DriftDetector

        report = DriftDetector().check(tmp_path)
        if report.items:
            severities = {item.severity for item in report.items}
            assert "error" in severities

    def test_empty_python_files_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "empty.py").write_text("", encoding="utf-8")
        from docs_mcp.validators.drift import DriftDetector

        report = DriftDetector().check(tmp_path)
        assert report.checked_files == 0

    def test_drift_score_capped_at_one(self, tmp_path: Path) -> None:
        for i in range(10):
            (tmp_path / f"mod{i}.py").write_text(
                f'"""Mod {i}."""\n\ndef func_{i}() -> None:\n    pass\n',
                encoding="utf-8",
            )
        from docs_mcp.validators.drift import DriftDetector

        report = DriftDetector().check(tmp_path)
        assert report.drift_score <= 1.0


# ---------------------------------------------------------------------------
# CompletenessChecker tests
# ---------------------------------------------------------------------------


class TestCompletenessCheckerEmpty:
    """CompletenessChecker on empty or nonexistent projects."""

    def test_empty_project_low_score(self, tmp_path: Path) -> None:
        from docs_mcp.validators.completeness import CompletenessChecker

        report = CompletenessChecker().check(tmp_path)
        assert report.overall_score == 0.0
        assert len(report.recommendations) > 0

    def test_nonexistent_root(self) -> None:
        from docs_mcp.validators.completeness import CompletenessChecker

        report = CompletenessChecker().check(Path("/nonexistent/xyz"))
        assert report.overall_score == 0.0
        assert len(report.recommendations) > 0


class TestCompletenessCheckerFullDocs:
    """CompletenessChecker with all docs present."""

    def test_all_essential_docs_high_score(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        (tmp_path / "LICENSE").write_text("MIT License\n", encoding="utf-8")
        (tmp_path / "CONTRIBUTING.md").write_text("# Contributing\n", encoding="utf-8")
        (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "guide.md").write_text("# Guide\n", encoding="utf-8")

        from docs_mcp.validators.completeness import CompletenessChecker

        report = CompletenessChecker().check(tmp_path)
        assert report.overall_score > 50.0

    def test_all_categories_returned(self, tmp_path: Path) -> None:
        from docs_mcp.validators.completeness import CompletenessChecker

        report = CompletenessChecker().check(tmp_path)
        names = {c.name for c in report.categories}
        assert "essential_docs" in names
        assert "development_docs" in names
        assert "api_documentation" in names
        assert "inline_docs" in names
        assert "project_docs" in names


class TestCompletenessCheckerMissing:
    """CompletenessChecker with partial documentation."""

    def test_missing_readme_generates_recommendation(self, tmp_path: Path) -> None:
        (tmp_path / "LICENSE").write_text("MIT\n", encoding="utf-8")
        from docs_mcp.validators.completeness import CompletenessChecker

        report = CompletenessChecker().check(tmp_path)
        has_rec = any("README" in r for r in report.recommendations)
        assert has_rec

    def test_missing_changelog_generates_recommendation(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        from docs_mcp.validators.completeness import CompletenessChecker

        report = CompletenessChecker().check(tmp_path)
        has_rec = any("CHANGELOG" in r for r in report.recommendations)
        assert has_rec

    def test_weight_affects_score(self, tmp_path: Path) -> None:
        """Essential docs (weight=3) should affect score more than project docs (weight=1)."""
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        (tmp_path / "LICENSE").write_text("MIT\n", encoding="utf-8")
        from docs_mcp.validators.completeness import CompletenessChecker

        report = CompletenessChecker().check(tmp_path)
        # Essential docs score 1.0*3 out of total weight 9 -> ~33%
        assert report.overall_score > 25.0

    def test_undocumented_module_recommendation(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "bad.py").write_text(
            "def func() -> None:\n    pass\n",
            encoding="utf-8",
        )
        from docs_mcp.validators.completeness import CompletenessChecker

        report = CompletenessChecker().check(tmp_path)
        has_inline_rec = any("docstring" in r.lower() for r in report.recommendations)
        assert has_inline_rec

    def test_docs_directory_recommendation(self, tmp_path: Path) -> None:
        from docs_mcp.validators.completeness import CompletenessChecker

        report = CompletenessChecker().check(tmp_path)
        has_docs_rec = any("docs/" in r for r in report.recommendations)
        assert has_docs_rec


# ---------------------------------------------------------------------------
# LinkChecker tests
# ---------------------------------------------------------------------------


class TestLinkCheckerEmpty:
    """LinkChecker on empty or nonexistent projects."""

    def test_empty_project_no_links(self, tmp_path: Path) -> None:
        from docs_mcp.validators.link_checker import LinkChecker

        report = LinkChecker().check(tmp_path)
        assert report.total_links == 0
        assert report.valid_links == 0
        assert report.broken_links == []

    def test_nonexistent_root(self) -> None:
        from docs_mcp.validators.link_checker import LinkChecker

        report = LinkChecker().check(Path("/nonexistent/xyz"))
        assert report.total_links == 0


class TestLinkCheckerValidLinks:
    """LinkChecker with valid links."""

    def test_valid_file_link(self, tmp_path: Path) -> None:
        (tmp_path / "guide.md").write_text("# Guide\n", encoding="utf-8")
        (tmp_path / "README.md").write_text(
            "# Project\n\nSee [guide](guide.md).\n",
            encoding="utf-8",
        )
        from docs_mcp.validators.link_checker import LinkChecker

        report = LinkChecker().check(tmp_path)
        assert report.total_links == 1
        assert report.valid_links == 1
        assert report.broken_links == []

    def test_valid_anchor_link(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text(
            "# Project\n\n[Setup](#setup)\n\n## Setup\n\nInstructions.\n",
            encoding="utf-8",
        )
        from docs_mcp.validators.link_checker import LinkChecker

        report = LinkChecker().check(tmp_path)
        assert report.total_links == 1
        assert report.valid_links == 1

    def test_valid_cross_file_anchor(self, tmp_path: Path) -> None:
        (tmp_path / "guide.md").write_text(
            "# Guide\n\n## Installation\n",
            encoding="utf-8",
        )
        (tmp_path / "README.md").write_text(
            "# Project\n\n[Install](guide.md#installation).\n",
            encoding="utf-8",
        )
        from docs_mcp.validators.link_checker import LinkChecker

        report = LinkChecker().check(tmp_path)
        assert report.valid_links == 1

    def test_external_links_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text(
            "# Project\n\n[Google](https://google.com)\n",
            encoding="utf-8",
        )
        from docs_mcp.validators.link_checker import LinkChecker

        report = LinkChecker().check(tmp_path)
        assert report.total_links == 0

    def test_subdirectory_link(self, tmp_path: Path) -> None:
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "api.md").write_text("# API\n", encoding="utf-8")
        (tmp_path / "README.md").write_text(
            "[API](docs/api.md)\n",
            encoding="utf-8",
        )
        from docs_mcp.validators.link_checker import LinkChecker

        report = LinkChecker().check(tmp_path)
        assert report.valid_links == 1


class TestLinkCheckerBrokenFileLinks:
    """LinkChecker with broken file references."""

    def test_broken_file_reference(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text(
            "# Project\n\n[Missing](missing.md)\n",
            encoding="utf-8",
        )
        from docs_mcp.validators.link_checker import LinkChecker

        report = LinkChecker().check(tmp_path)
        assert len(report.broken_links) == 1
        assert report.broken_links[0].reason == "file_not_found"

    def test_broken_link_has_line_number(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text(
            "# Project\n\nSome text.\n\n[Missing](gone.md)\n",
            encoding="utf-8",
        )
        from docs_mcp.validators.link_checker import LinkChecker

        report = LinkChecker().check(tmp_path)
        assert len(report.broken_links) == 1
        assert report.broken_links[0].line == 5

    def test_multiple_broken_links(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text(
            "[A](a.md) and [B](b.md)\n",
            encoding="utf-8",
        )
        from docs_mcp.validators.link_checker import LinkChecker

        report = LinkChecker().check(tmp_path)
        assert len(report.broken_links) == 2


class TestLinkCheckerBrokenAnchors:
    """LinkChecker with broken anchor references."""

    def test_broken_same_file_anchor(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text(
            "# Project\n\n[Jump](#nonexistent)\n",
            encoding="utf-8",
        )
        from docs_mcp.validators.link_checker import LinkChecker

        report = LinkChecker().check(tmp_path)
        assert len(report.broken_links) == 1
        assert report.broken_links[0].reason == "anchor_not_found"

    def test_broken_cross_file_anchor(self, tmp_path: Path) -> None:
        (tmp_path / "guide.md").write_text("# Guide\n\n## Setup\n", encoding="utf-8")
        (tmp_path / "README.md").write_text(
            "[Usage](guide.md#usage)\n",
            encoding="utf-8",
        )
        from docs_mcp.validators.link_checker import LinkChecker

        report = LinkChecker().check(tmp_path)
        assert len(report.broken_links) == 1
        assert report.broken_links[0].reason == "anchor_not_found"


class TestLinkCheckerFilesFilter:
    """LinkChecker with files parameter filtering."""

    def test_files_restricts_scanning(self, tmp_path: Path) -> None:
        (tmp_path / "good.md").write_text("# Good\n", encoding="utf-8")
        (tmp_path / "a.md").write_text("[link](good.md)\n", encoding="utf-8")
        (tmp_path / "b.md").write_text("[broken](missing.md)\n", encoding="utf-8")

        from docs_mcp.validators.link_checker import LinkChecker

        report = LinkChecker().check(tmp_path, files=["a.md"])
        assert report.total_links == 1
        assert report.valid_links == 1
        assert report.broken_links == []


# ---------------------------------------------------------------------------
# FreshnessChecker tests
# ---------------------------------------------------------------------------


class TestFreshnessCheckerEmpty:
    """FreshnessChecker on empty or nonexistent projects."""

    def test_empty_project_zero_score(self, tmp_path: Path) -> None:
        from docs_mcp.validators.freshness import FreshnessChecker

        report = FreshnessChecker().check(tmp_path)
        assert report.items == []
        assert report.freshness_score == 0.0
        assert report.average_age_days == 0.0

    def test_nonexistent_root(self) -> None:
        from docs_mcp.validators.freshness import FreshnessChecker

        report = FreshnessChecker().check(Path("/nonexistent/xyz"))
        assert report.freshness_score == 0.0


class TestFreshnessCheckerFreshDocs:
    """FreshnessChecker with recently modified docs."""

    def test_fresh_files_high_score(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")

        from docs_mcp.validators.freshness import FreshnessChecker

        report = FreshnessChecker().check(tmp_path)
        assert len(report.items) == 2
        assert report.freshness_score > 90.0
        for item in report.items:
            assert item.freshness == "fresh"

    def test_fresh_file_age_near_zero(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        from docs_mcp.validators.freshness import FreshnessChecker

        report = FreshnessChecker().check(tmp_path)
        assert report.average_age_days < 1.0

    def test_iso_date_format(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        from docs_mcp.validators.freshness import FreshnessChecker

        report = FreshnessChecker().check(tmp_path)
        iso = report.items[0].last_modified
        assert "T" in iso
        assert len(iso) == 20  # YYYY-MM-DDTHH:MM:SSZ
        assert iso.endswith("Z")


class TestFreshnessCheckerStaleDocs:
    """FreshnessChecker with old modification times."""

    def test_stale_files_low_score(self, tmp_path: Path) -> None:
        readme = tmp_path / "README.md"
        readme.write_text("# Project\n", encoding="utf-8")
        old_time = time.time() - 86400 * 200
        os.utime(readme, (old_time, old_time))

        from docs_mcp.validators.freshness import FreshnessChecker

        report = FreshnessChecker().check(tmp_path)
        assert report.items[0].freshness == "stale"
        assert report.freshness_score < 50.0

    def test_ancient_files(self, tmp_path: Path) -> None:
        readme = tmp_path / "README.md"
        readme.write_text("# Old\n", encoding="utf-8")
        old_time = time.time() - 86400 * 730
        os.utime(readme, (old_time, old_time))

        from docs_mcp.validators.freshness import FreshnessChecker

        report = FreshnessChecker().check(tmp_path)
        assert report.items[0].freshness == "ancient"
        assert report.items[0].age_days >= 365

    def test_mixed_freshness_intermediate_score(self, tmp_path: Path) -> None:
        (tmp_path / "fresh.md").write_text("# Fresh\n", encoding="utf-8")
        old_doc = tmp_path / "old.md"
        old_doc.write_text("# Old\n", encoding="utf-8")
        old_time = time.time() - 86400 * 200
        os.utime(old_doc, (old_time, old_time))

        from docs_mcp.validators.freshness import FreshnessChecker

        report = FreshnessChecker().check(tmp_path)
        labels = {item.freshness for item in report.items}
        assert "fresh" in labels

    def test_score_between_zero_and_hundred(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        from docs_mcp.validators.freshness import FreshnessChecker

        report = FreshnessChecker().check(tmp_path)
        assert 0.0 <= report.freshness_score <= 100.0

    def test_skip_dirs_honored(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        venv = tmp_path / ".venv"
        venv.mkdir()
        (venv / "hidden.md").write_text("# Hidden\n", encoding="utf-8")

        from docs_mcp.validators.freshness import FreshnessChecker

        report = FreshnessChecker().check(tmp_path)
        paths = {item.file_path for item in report.items}
        assert not any(".venv" in p for p in paths)


# ---------------------------------------------------------------------------
# MCP tool tests: docs_check_drift
# ---------------------------------------------------------------------------


class TestDocsCheckDriftTool:
    """Test docs_check_drift MCP tool wrapper."""

    @pytest.mark.asyncio
    async def test_success_response_envelope(self, tmp_path: Path) -> None:
        from docs_mcp.server_val_tools import docs_check_drift

        result = await docs_check_drift(project_root=str(tmp_path))
        assert result["success"] is True
        assert result["tool"] == "docs_check_drift"
        assert "elapsed_ms" in result
        assert "data" in result

    @pytest.mark.asyncio
    async def test_data_contains_report_fields(self, tmp_path: Path) -> None:
        from docs_mcp.server_val_tools import docs_check_drift

        result = await docs_check_drift(project_root=str(tmp_path))
        data = result["data"]
        assert "total_items" in data
        assert "drift_score" in data
        assert "checked_files" in data
        assert "items" in data

    @pytest.mark.asyncio
    async def test_invalid_root_returns_error(self) -> None:
        from docs_mcp.server_val_tools import docs_check_drift

        result = await docs_check_drift(project_root="/nonexistent/xyz")
        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_ROOT"

    @pytest.mark.asyncio
    async def test_doc_dirs_parameter_parsed(self, tmp_path: Path) -> None:
        """Verify doc_dirs comma-separated string is parsed correctly."""
        (tmp_path / "app.py").write_text(
            '"""App."""\n\ndef func() -> None:\n    pass\n',
            encoding="utf-8",
        )
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "api.md").write_text("# API\n\nThe `func` function.\n", encoding="utf-8")

        from docs_mcp.server_val_tools import docs_check_drift

        result = await docs_check_drift(
            doc_dirs="docs", project_root=str(tmp_path),
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_records_tool_call(self, tmp_path: Path) -> None:
        from docs_mcp.server import _tool_calls
        from docs_mcp.server_val_tools import docs_check_drift

        await docs_check_drift(project_root=str(tmp_path))
        assert _tool_calls.get("docs_check_drift", 0) >= 1

    @pytest.mark.asyncio
    async def test_with_patched_detector(self, tmp_path: Path) -> None:
        """Verify tool delegates to DriftDetector correctly."""
        from docs_mcp.validators.drift import DriftReport

        mock_report = DriftReport(
            total_items=3,
            drift_score=0.5,
            checked_files=6,
        )
        with patch(
            "docs_mcp.validators.drift.DriftDetector"
        ) as mock_cls:
            mock_cls.return_value.check.return_value = mock_report
            from docs_mcp.server_val_tools import docs_check_drift

            result = await docs_check_drift(project_root=str(tmp_path))

        assert result["success"] is True
        assert result["data"]["total_items"] == 3
        assert result["data"]["drift_score"] == 0.5


# ---------------------------------------------------------------------------
# MCP tool tests: docs_check_completeness
# ---------------------------------------------------------------------------


class TestDocsCheckCompletenessTool:
    """Test docs_check_completeness MCP tool wrapper."""

    @pytest.mark.asyncio
    async def test_success_response_envelope(self, tmp_path: Path) -> None:
        from docs_mcp.server_val_tools import docs_check_completeness

        result = await docs_check_completeness(project_root=str(tmp_path))
        assert result["success"] is True
        assert result["tool"] == "docs_check_completeness"
        assert "elapsed_ms" in result

    @pytest.mark.asyncio
    async def test_data_contains_report_fields(self, tmp_path: Path) -> None:
        from docs_mcp.server_val_tools import docs_check_completeness

        result = await docs_check_completeness(project_root=str(tmp_path))
        data = result["data"]
        assert "overall_score" in data
        assert "categories" in data
        assert "recommendations" in data

    @pytest.mark.asyncio
    async def test_invalid_root_returns_error(self) -> None:
        from docs_mcp.server_val_tools import docs_check_completeness

        result = await docs_check_completeness(project_root="/nonexistent/xyz")
        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_ROOT"

    @pytest.mark.asyncio
    async def test_records_tool_call(self, tmp_path: Path) -> None:
        from docs_mcp.server import _tool_calls
        from docs_mcp.server_val_tools import docs_check_completeness

        await docs_check_completeness(project_root=str(tmp_path))
        assert _tool_calls.get("docs_check_completeness", 0) >= 1

    @pytest.mark.asyncio
    async def test_categories_are_list_of_dicts(self, tmp_path: Path) -> None:
        from docs_mcp.server_val_tools import docs_check_completeness

        result = await docs_check_completeness(project_root=str(tmp_path))
        categories = result["data"]["categories"]
        assert isinstance(categories, list)
        for cat in categories:
            assert isinstance(cat, dict)
            assert "name" in cat
            assert "score" in cat

    @pytest.mark.asyncio
    async def test_with_patched_checker(self, tmp_path: Path) -> None:
        from docs_mcp.validators.completeness import CompletenessReport

        mock_report = CompletenessReport(
            overall_score=75.0,
            recommendations=["Add CHANGELOG.md"],
        )
        with patch(
            "docs_mcp.validators.completeness.CompletenessChecker"
        ) as mock_cls:
            mock_cls.return_value.check.return_value = mock_report
            from docs_mcp.server_val_tools import docs_check_completeness

            result = await docs_check_completeness(project_root=str(tmp_path))

        assert result["data"]["overall_score"] == 75.0
        assert "Add CHANGELOG.md" in result["data"]["recommendations"]


# ---------------------------------------------------------------------------
# MCP tool tests: docs_check_links
# ---------------------------------------------------------------------------


class TestDocsCheckLinksTool:
    """Test docs_check_links MCP tool wrapper."""

    @pytest.mark.asyncio
    async def test_success_response_envelope(self, tmp_path: Path) -> None:
        from docs_mcp.server_val_tools import docs_check_links

        result = await docs_check_links(project_root=str(tmp_path))
        assert result["success"] is True
        assert result["tool"] == "docs_check_links"

    @pytest.mark.asyncio
    async def test_data_contains_report_fields(self, tmp_path: Path) -> None:
        from docs_mcp.server_val_tools import docs_check_links

        result = await docs_check_links(project_root=str(tmp_path))
        data = result["data"]
        assert "total_links" in data
        assert "valid_links" in data
        assert "broken_links" in data

    @pytest.mark.asyncio
    async def test_invalid_root_returns_error(self) -> None:
        from docs_mcp.server_val_tools import docs_check_links

        result = await docs_check_links(project_root="/nonexistent/xyz")
        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_ROOT"

    @pytest.mark.asyncio
    async def test_files_parameter_comma_separated(self, tmp_path: Path) -> None:
        """Verify files comma-separated string is parsed correctly."""
        (tmp_path / "a.md").write_text("# A\n", encoding="utf-8")
        (tmp_path / "b.md").write_text("[link](a.md)\n", encoding="utf-8")
        (tmp_path / "c.md").write_text("[broken](missing.md)\n", encoding="utf-8")

        from docs_mcp.server_val_tools import docs_check_links

        # Only check b.md (has valid link) and skip c.md (has broken)
        result = await docs_check_links(
            files="b.md", project_root=str(tmp_path),
        )
        assert result["success"] is True
        assert result["data"]["valid_links"] == 1
        assert len(result["data"]["broken_links"]) == 0

    @pytest.mark.asyncio
    async def test_records_tool_call(self, tmp_path: Path) -> None:
        from docs_mcp.server import _tool_calls
        from docs_mcp.server_val_tools import docs_check_links

        await docs_check_links(project_root=str(tmp_path))
        assert _tool_calls.get("docs_check_links", 0) >= 1

    @pytest.mark.asyncio
    async def test_multiple_files_parameter(self, tmp_path: Path) -> None:
        (tmp_path / "target.md").write_text("# Target\n", encoding="utf-8")
        (tmp_path / "a.md").write_text("[T](target.md)\n", encoding="utf-8")
        (tmp_path / "b.md").write_text("[T](target.md)\n", encoding="utf-8")

        from docs_mcp.server_val_tools import docs_check_links

        result = await docs_check_links(
            files="a.md, b.md", project_root=str(tmp_path),
        )
        assert result["data"]["total_links"] == 2
        assert result["data"]["valid_links"] == 2

    @pytest.mark.asyncio
    async def test_with_patched_checker(self, tmp_path: Path) -> None:
        from docs_mcp.validators.link_checker import LinkReport

        mock_report = LinkReport(
            total_links=10,
            valid_links=8,
        )
        with patch(
            "docs_mcp.validators.link_checker.LinkChecker"
        ) as mock_cls:
            mock_cls.return_value.check.return_value = mock_report
            from docs_mcp.server_val_tools import docs_check_links

            result = await docs_check_links(project_root=str(tmp_path))

        assert result["data"]["total_links"] == 10
        assert result["data"]["valid_links"] == 8


# ---------------------------------------------------------------------------
# MCP tool tests: docs_check_freshness
# ---------------------------------------------------------------------------


class TestDocsCheckFreshnessTool:
    """Test docs_check_freshness MCP tool wrapper."""

    @pytest.mark.asyncio
    async def test_success_response_envelope(self, tmp_path: Path) -> None:
        from docs_mcp.server_val_tools import docs_check_freshness

        result = await docs_check_freshness(project_root=str(tmp_path))
        assert result["success"] is True
        assert result["tool"] == "docs_check_freshness"

    @pytest.mark.asyncio
    async def test_data_contains_report_fields(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# Readme\n", encoding="utf-8")
        from docs_mcp.server_val_tools import docs_check_freshness

        result = await docs_check_freshness(project_root=str(tmp_path))
        data = result["data"]
        assert "freshness_score" in data
        assert "average_age_days" in data
        assert "items" in data

    @pytest.mark.asyncio
    async def test_invalid_root_returns_error(self) -> None:
        from docs_mcp.server_val_tools import docs_check_freshness

        result = await docs_check_freshness(project_root="/nonexistent/xyz")
        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_ROOT"

    @pytest.mark.asyncio
    async def test_records_tool_call(self, tmp_path: Path) -> None:
        from docs_mcp.server import _tool_calls
        from docs_mcp.server_val_tools import docs_check_freshness

        await docs_check_freshness(project_root=str(tmp_path))
        assert _tool_calls.get("docs_check_freshness", 0) >= 1

    @pytest.mark.asyncio
    async def test_fresh_file_high_score(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        from docs_mcp.server_val_tools import docs_check_freshness

        result = await docs_check_freshness(project_root=str(tmp_path))
        assert result["data"]["freshness_score"] > 90.0

    @pytest.mark.asyncio
    async def test_items_serialized_as_dicts(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        from docs_mcp.server_val_tools import docs_check_freshness

        result = await docs_check_freshness(project_root=str(tmp_path))
        items = result["data"]["items"]
        assert isinstance(items, list)
        assert len(items) == 1
        assert isinstance(items[0], dict)
        assert "file_path" in items[0]
        assert "freshness" in items[0]

    @pytest.mark.asyncio
    async def test_with_patched_checker(self, tmp_path: Path) -> None:
        from docs_mcp.validators.freshness import FreshnessReport

        mock_report = FreshnessReport(
            freshness_score=42.0,
            average_age_days=120.5,
        )
        with patch(
            "docs_mcp.validators.freshness.FreshnessChecker"
        ) as mock_cls:
            mock_cls.return_value.check.return_value = mock_report
            from docs_mcp.server_val_tools import docs_check_freshness

            result = await docs_check_freshness(project_root=str(tmp_path))

        assert result["data"]["freshness_score"] == 42.0
        assert result["data"]["average_age_days"] == 120.5

"""Tests for MCP tool wrappers around documentation validators.

Behavioral tests for individual validators (DriftDetector, CompletenessChecker,
LinkChecker, FreshnessChecker) live in their dedicated test files:
  - test_drift.py
  - test_completeness.py
  - test_link_checker.py
  - test_freshness.py

This file tests:
  1. The server tool integration layer (docs_check_drift, docs_check_completeness,
     docs_check_links, docs_check_freshness) -- response envelopes, parameter
     parsing, error handling, patched delegation, filtering, and pagination.
  2. A small number of validator behavioral tests that are not covered by
     the individual files (partial coverage, specific recommendations,
     line numbers on broken links).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Unique validator behavioral tests (not covered in individual test files)
# ---------------------------------------------------------------------------


class TestDriftDetectorPartialCoverage:
    """Drift detector partial coverage scenario not in test_drift.py."""

    def test_partial_coverage_produces_partial_drift(self, tmp_path: Path) -> None:
        (tmp_path / "utils.py").write_text(
            '"""Utils."""\n\ndef alpha() -> None:\n    pass\n\ndef beta() -> None:\n    pass\n',
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


class TestCompletenessCheckerRecommendations:
    """Completeness recommendation tests not covered in test_completeness.py."""

    def test_missing_changelog_generates_recommendation(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
        from docs_mcp.validators.completeness import CompletenessChecker

        report = CompletenessChecker().check(tmp_path)
        has_rec = any("CHANGELOG" in r for r in report.recommendations)
        assert has_rec

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


class TestLinkCheckerLineNumbers:
    """Link checker line number test not covered in test_link_checker.py."""

    def test_broken_link_has_line_number(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text(
            "# Project\n\nSome text.\n\n[Missing](gone.md)\n",
            encoding="utf-8",
        )
        from docs_mcp.validators.link_checker import LinkChecker

        report = LinkChecker().check(tmp_path)
        assert len(report.broken_links) == 1
        assert report.broken_links[0].line == 5


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
            doc_dirs="docs",
            project_root=str(tmp_path),
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
        from docs_mcp.validators.drift import DriftItem, DriftReport

        mock_report = DriftReport(
            total_items=3,
            items=[
                DriftItem(
                    file_path=f"src/mod{i}.py",
                    drift_type="added_undocumented",
                    description=f"Public names not found in docs: func_{i}",
                )
                for i in range(3)
            ],
            drift_score=0.5,
            checked_files=6,
        )
        with patch("docs_mcp.validators.drift.DriftDetector") as mock_cls:
            mock_cls.return_value.check.return_value = mock_report
            from docs_mcp.server_val_tools import docs_check_drift

            result = await docs_check_drift(project_root=str(tmp_path))

        assert result["success"] is True
        assert result["data"]["total_items"] == 3
        assert result["data"]["drift_score"] == 0.5

    @pytest.mark.asyncio
    async def test_source_files_filter(self, tmp_path: Path) -> None:
        """source_files limits results to matching file paths."""
        from unittest.mock import patch

        from docs_mcp.validators.drift import DriftItem, DriftReport

        mock_report = DriftReport(
            total_items=3,
            items=[
                DriftItem(
                    file_path="src/server.py",
                    drift_type="added_undocumented",
                    description="Public names not found in docs: handle_request",
                ),
                DriftItem(
                    file_path="src/upgrade.py",
                    drift_type="added_undocumented",
                    description="Public names not found in docs: run_upgrade",
                ),
                DriftItem(
                    file_path="src/utils.py",
                    drift_type="added_undocumented",
                    description="Public names not found in docs: parse_config",
                ),
            ],
            drift_score=0.5,
            checked_files=6,
        )

        with patch("docs_mcp.validators.drift.DriftDetector") as mock_cls:
            mock_cls.return_value.check.return_value = mock_report
            from docs_mcp.server_val_tools import docs_check_drift

            result = await docs_check_drift(
                source_files="server.py,upgrade.py",
                project_root=str(tmp_path),
            )

        data = result["data"]
        assert data["total_unfiltered"] == 3
        assert data["total_items"] == 2
        assert data["showing"] == 2
        paths = {it["file_path"] for it in data["items"]}
        assert paths == {"src/server.py", "src/upgrade.py"}

    @pytest.mark.asyncio
    async def test_search_names_filter(self, tmp_path: Path) -> None:
        """search_names limits results to items mentioning the given names."""
        from unittest.mock import patch

        from docs_mcp.validators.drift import DriftItem, DriftReport

        mock_report = DriftReport(
            total_items=2,
            items=[
                DriftItem(
                    file_path="src/server.py",
                    drift_type="added_undocumented",
                    description="Public names not found in docs: handle_request, init_app",
                ),
                DriftItem(
                    file_path="src/utils.py",
                    drift_type="added_undocumented",
                    description="Public names not found in docs: parse_config",
                ),
            ],
            drift_score=0.3,
            checked_files=4,
        )

        with patch("docs_mcp.validators.drift.DriftDetector") as mock_cls:
            mock_cls.return_value.check.return_value = mock_report
            from docs_mcp.server_val_tools import docs_check_drift

            result = await docs_check_drift(
                search_names="handle_request",
                project_root=str(tmp_path),
            )

        data = result["data"]
        assert data["total_unfiltered"] == 2
        assert data["total_items"] == 1
        assert data["items"][0]["file_path"] == "src/server.py"

    @pytest.mark.asyncio
    async def test_max_items_limit(self, tmp_path: Path) -> None:
        """max_items caps the number of returned items."""
        from unittest.mock import patch

        from docs_mcp.validators.drift import DriftItem, DriftReport

        items = [
            DriftItem(
                file_path=f"src/mod{i}.py",
                drift_type="added_undocumented",
                description=f"Public names not found in docs: func_{i}",
            )
            for i in range(10)
        ]
        mock_report = DriftReport(
            total_items=10,
            items=items,
            drift_score=0.8,
            checked_files=10,
        )

        with patch("docs_mcp.validators.drift.DriftDetector") as mock_cls:
            mock_cls.return_value.check.return_value = mock_report
            from docs_mcp.server_val_tools import docs_check_drift

            result = await docs_check_drift(
                max_items=3,
                project_root=str(tmp_path),
            )

        data = result["data"]
        assert data["total_unfiltered"] == 10
        assert data["total_items"] == 10
        assert data["showing"] == 3
        assert len(data["items"]) == 3

    @pytest.mark.asyncio
    async def test_combined_filters(self, tmp_path: Path) -> None:
        """source_files + search_names + max_items combine correctly."""
        from unittest.mock import patch

        from docs_mcp.validators.drift import DriftItem, DriftReport

        mock_report = DriftReport(
            total_items=3,
            items=[
                DriftItem(
                    file_path="src/server.py",
                    drift_type="added_undocumented",
                    description="Public names not found in docs: handle_request",
                ),
                DriftItem(
                    file_path="src/server.py",
                    drift_type="added_undocumented",
                    description="Public names not found in docs: shutdown",
                ),
                DriftItem(
                    file_path="src/utils.py",
                    drift_type="added_undocumented",
                    description="Public names not found in docs: parse_config",
                ),
            ],
            drift_score=0.5,
            checked_files=6,
        )

        with patch("docs_mcp.validators.drift.DriftDetector") as mock_cls:
            mock_cls.return_value.check.return_value = mock_report
            from docs_mcp.server_val_tools import docs_check_drift

            result = await docs_check_drift(
                source_files="server.py",
                search_names="handle_request",
                max_items=1,
                project_root=str(tmp_path),
            )

        data = result["data"]
        assert data["total_unfiltered"] == 3
        assert data["total_items"] == 1
        assert data["showing"] == 1

    @pytest.mark.asyncio
    async def test_no_filters_backward_compat(self, tmp_path: Path) -> None:
        """Without filters, response includes summary counts and all items."""
        from unittest.mock import patch

        from docs_mcp.validators.drift import DriftItem, DriftReport

        mock_report = DriftReport(
            total_items=2,
            items=[
                DriftItem(
                    file_path="src/a.py",
                    drift_type="added_undocumented",
                    description="Public names not found in docs: foo",
                ),
                DriftItem(
                    file_path="src/b.py",
                    drift_type="added_undocumented",
                    description="Public names not found in docs: bar",
                ),
            ],
            drift_score=0.3,
            checked_files=4,
        )

        with patch("docs_mcp.validators.drift.DriftDetector") as mock_cls:
            mock_cls.return_value.check.return_value = mock_report
            from docs_mcp.server_val_tools import docs_check_drift

            result = await docs_check_drift(project_root=str(tmp_path))

        data = result["data"]
        assert data["total_unfiltered"] == 2
        assert data["total_items"] == 2
        assert data["showing"] == 2
        assert len(data["items"]) == 2


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
        with patch("docs_mcp.validators.completeness.CompletenessChecker") as mock_cls:
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
            files="b.md",
            project_root=str(tmp_path),
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
            files="a.md, b.md",
            project_root=str(tmp_path),
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
        with patch("docs_mcp.validators.link_checker.LinkChecker") as mock_cls:
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
        with patch("docs_mcp.validators.freshness.FreshnessChecker") as mock_cls:
            mock_cls.return_value.check.return_value = mock_report
            from docs_mcp.server_val_tools import docs_check_freshness

            result = await docs_check_freshness(project_root=str(tmp_path))

        assert result["data"]["freshness_score"] == 42.0
        assert result["data"]["average_age_days"] == 120.5

    # -------------------------------------------------------------------
    # Epic 88: Response size management tests
    # -------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_category_counts_in_response(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("# R\n", encoding="utf-8")
        from docs_mcp.server_val_tools import docs_check_freshness

        result = await docs_check_freshness(project_root=str(tmp_path))
        cc = result["data"]["category_counts"]
        assert cc["fresh"] == 1
        assert cc["aging"] == 0

    @pytest.mark.asyncio
    async def test_items_sorted_stalest_first(self, tmp_path: Path) -> None:
        import os as _os
        import time as _time

        (tmp_path / "new.md").write_text("n\n", encoding="utf-8")
        old = tmp_path / "old.md"
        old.write_text("o\n", encoding="utf-8")
        _os.utime(old, (_time.time() - 86400 * 200, _time.time() - 86400 * 200))

        from docs_mcp.server_val_tools import docs_check_freshness

        result = await docs_check_freshness(project_root=str(tmp_path))
        items = result["data"]["items"]
        assert len(items) == 2
        assert items[0]["age_days"] >= items[1]["age_days"]

    @pytest.mark.asyncio
    async def test_summary_string_present(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("a\n", encoding="utf-8")
        from docs_mcp.server_val_tools import docs_check_freshness

        result = await docs_check_freshness(project_root=str(tmp_path))
        summary = result["data"]["summary"]
        assert "docs scanned" in summary
        assert "fresh" in summary

    @pytest.mark.asyncio
    async def test_total_items_and_showing_metadata(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("a\n", encoding="utf-8")
        from docs_mcp.server_val_tools import docs_check_freshness

        result = await docs_check_freshness(project_root=str(tmp_path))
        data = result["data"]
        assert data["total_unfiltered"] == 1
        assert data["total_items"] == 1
        assert data["showing"] == 1

    @pytest.mark.asyncio
    async def test_max_items_truncation(self, tmp_path: Path) -> None:
        for i in range(10):
            (tmp_path / f"doc{i}.md").write_text(f"d{i}\n", encoding="utf-8")
        from docs_mcp.server_val_tools import docs_check_freshness

        result = await docs_check_freshness(
            project_root=str(tmp_path),
            max_items=3,
        )
        data = result["data"]
        assert data["showing"] == 3
        assert data["total_items"] == 10
        assert data["total_unfiltered"] == 10
        assert len(data["items"]) == 3

    @pytest.mark.asyncio
    async def test_max_items_zero_uses_default(self, tmp_path: Path) -> None:
        for i in range(60):
            (tmp_path / f"doc{i}.md").write_text(f"d{i}\n", encoding="utf-8")
        from docs_mcp.server_val_tools import docs_check_freshness

        result = await docs_check_freshness(
            project_root=str(tmp_path),
            max_items=0,
        )
        data = result["data"]
        assert data["showing"] == 50  # default
        assert data["total_items"] == 60

    @pytest.mark.asyncio
    async def test_path_scoping(self, tmp_path: Path) -> None:
        sub = tmp_path / "docs"
        sub.mkdir()
        (sub / "guide.md").write_text("g\n", encoding="utf-8")
        (tmp_path / "README.md").write_text("r\n", encoding="utf-8")
        from docs_mcp.server_val_tools import docs_check_freshness

        result = await docs_check_freshness(
            project_root=str(tmp_path),
            path="docs",
        )
        data = result["data"]
        assert data["total_unfiltered"] == 1
        items = data["items"]
        assert len(items) == 1
        assert items[0]["file_path"] == "docs/guide.md"

    @pytest.mark.asyncio
    async def test_path_scoping_invalid_returns_error(self, tmp_path: Path) -> None:
        from docs_mcp.server_val_tools import docs_check_freshness

        result = await docs_check_freshness(
            project_root=str(tmp_path),
            path="nonexistent",
        )
        assert result["success"] is False
        assert result["error"]["code"] == "INVALID_PATH"

    @pytest.mark.asyncio
    async def test_summary_only_mode(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("a\n", encoding="utf-8")
        (tmp_path / "b.md").write_text("b\n", encoding="utf-8")
        from docs_mcp.server_val_tools import docs_check_freshness

        result = await docs_check_freshness(
            project_root=str(tmp_path),
            summary_only=True,
        )
        data = result["data"]
        assert data["items"] == []
        assert data["showing"] == 0
        assert data["total_items"] == 2
        assert data["freshness_score"] > 0
        assert data["category_counts"]["fresh"] == 2

    @pytest.mark.asyncio
    async def test_freshness_filter_single_category(self, tmp_path: Path) -> None:
        import os as _os
        import time as _time

        (tmp_path / "new.md").write_text("n\n", encoding="utf-8")
        old = tmp_path / "old.md"
        old.write_text("o\n", encoding="utf-8")
        _os.utime(old, (_time.time() - 86400 * 200, _time.time() - 86400 * 200))

        from docs_mcp.server_val_tools import docs_check_freshness

        result = await docs_check_freshness(
            project_root=str(tmp_path),
            freshness="stale",
        )
        data = result["data"]
        assert data["total_unfiltered"] == 2
        assert data["total_items"] == 1
        assert data["items"][0]["freshness"] == "stale"

    @pytest.mark.asyncio
    async def test_freshness_filter_multiple_categories(self, tmp_path: Path) -> None:
        import os as _os
        import time as _time

        (tmp_path / "new.md").write_text("n\n", encoding="utf-8")
        stale = tmp_path / "stale.md"
        stale.write_text("s\n", encoding="utf-8")
        _os.utime(stale, (_time.time() - 86400 * 200, _time.time() - 86400 * 200))
        ancient = tmp_path / "ancient.md"
        ancient.write_text("a\n", encoding="utf-8")
        _os.utime(ancient, (_time.time() - 86400 * 400, _time.time() - 86400 * 400))

        from docs_mcp.server_val_tools import docs_check_freshness

        result = await docs_check_freshness(
            project_root=str(tmp_path),
            freshness="stale,ancient",
        )
        data = result["data"]
        assert data["total_unfiltered"] == 3
        assert data["total_items"] == 2
        for item in data["items"]:
            assert item["freshness"] in {"stale", "ancient"}

    @pytest.mark.asyncio
    async def test_freshness_filter_invalid_category_ignored(
        self,
        tmp_path: Path,
    ) -> None:
        (tmp_path / "a.md").write_text("a\n", encoding="utf-8")
        from docs_mcp.server_val_tools import docs_check_freshness

        result = await docs_check_freshness(
            project_root=str(tmp_path),
            freshness="invalid,fresh",
        )
        data = result["data"]
        assert data["total_items"] == 1

    @pytest.mark.asyncio
    async def test_combined_filter_and_max_items(self, tmp_path: Path) -> None:
        """freshness filter + max_items should filter first, then truncate."""
        for i in range(10):
            (tmp_path / f"doc{i}.md").write_text(f"d{i}\n", encoding="utf-8")

        from docs_mcp.server_val_tools import docs_check_freshness

        result = await docs_check_freshness(
            project_root=str(tmp_path),
            freshness="fresh",
            max_items=3,
        )
        data = result["data"]
        assert data["total_items"] == 10  # all fresh
        assert data["showing"] == 3

"""Tests for tools.parallel — concurrent tool execution."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from tapps_mcp.scoring.models import LintIssue, SecurityIssue, TypeIssue
from tapps_mcp.tools.parallel import ParallelResults, run_all_tools


class TestParallelResults:
    def test_defaults(self):
        r = ParallelResults()
        assert r.lint_issues == []
        assert r.type_issues == []
        assert r.security_issues == []
        assert r.radon_cc == []
        assert r.radon_mi == 50.0
        assert r.missing_tools == []
        assert r.degraded is False


class TestRunAllTools:
    @pytest.fixture
    def mock_which(self):
        """Mock shutil.which so all tools are 'found'."""
        with patch("tapps_mcp.tools.parallel.shutil.which", return_value="/usr/bin/tool") as m:
            yield m

    @pytest.fixture
    def mock_which_none(self):
        """Mock shutil.which so no tools are found."""
        with patch("tapps_mcp.tools.parallel.shutil.which", return_value=None) as m:
            yield m

    @pytest.mark.asyncio
    async def test_all_tools_missing(self, mock_which_none):
        result = await run_all_tools("test.py")
        assert result.degraded is True
        assert "ruff" in result.missing_tools
        assert "mypy" in result.missing_tools
        assert "bandit" in result.missing_tools
        assert "radon" in result.missing_tools

    @pytest.mark.asyncio
    async def test_selectively_disabled(self, mock_which):
        with (
            patch("tapps_mcp.tools.parallel.run_ruff_check_async", new_callable=AsyncMock) as ruff,
        ):
            ruff.return_value = []
            result = await run_all_tools(
                "test.py",
                run_ruff=True,
                run_mypy=False,
                run_bandit=False,
                run_radon=False,
            )
            assert result.lint_issues == []
            ruff.assert_called_once()
            # mypy, bandit, radon not called but also not "missing"
            assert "mypy" not in result.missing_tools

    @pytest.mark.asyncio
    async def test_tool_exception_handled(self, mock_which):
        with (
            patch(
                "tapps_mcp.tools.parallel.run_ruff_check_async",
                new_callable=AsyncMock,
                side_effect=RuntimeError("ruff crashed"),
            ),
            patch(
                "tapps_mcp.tools.parallel.run_mypy_check_async",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "tapps_mcp.tools.parallel.run_bandit_check_async",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "tapps_mcp.tools.parallel.run_radon_cc_async",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "tapps_mcp.tools.parallel.run_radon_mi_async",
                new_callable=AsyncMock,
                return_value=65.0,
            ),
        ):
            result = await run_all_tools("test.py")
            assert result.degraded is True
            # Other tools should still have results
            assert result.type_issues == []

    @pytest.mark.asyncio
    async def test_successful_run(self, mock_which):
        lint_issues = [LintIssue(code="E501", message="long", file="t.py", line=1)]
        type_issues = [TypeIssue(file="t.py", line=1, message="err")]
        sec_issues = [SecurityIssue(code="B101", message="assert", file="t.py", line=1)]
        radon_cc = [{"name": "foo", "complexity": 3}]
        radon_mi = 75.0

        with (
            patch(
                "tapps_mcp.tools.parallel.run_ruff_check_async",
                new_callable=AsyncMock,
                return_value=lint_issues,
            ),
            patch(
                "tapps_mcp.tools.parallel.run_mypy_check_async",
                new_callable=AsyncMock,
                return_value=type_issues,
            ),
            patch(
                "tapps_mcp.tools.parallel.run_bandit_check_async",
                new_callable=AsyncMock,
                return_value=sec_issues,
            ),
            patch(
                "tapps_mcp.tools.parallel.run_radon_cc_async",
                new_callable=AsyncMock,
                return_value=radon_cc,
            ),
            patch(
                "tapps_mcp.tools.parallel.run_radon_mi_async",
                new_callable=AsyncMock,
                return_value=radon_mi,
            ),
        ):
            result = await run_all_tools("test.py")
            assert result.lint_issues == lint_issues
            assert result.type_issues == type_issues
            assert result.security_issues == sec_issues
            assert result.radon_cc == radon_cc
            assert result.radon_mi == radon_mi
            assert result.degraded is False
            assert result.missing_tools == []

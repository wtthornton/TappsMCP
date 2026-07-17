"""Regression tests for the v4 functional bugfix batch."""

from __future__ import annotations

import ast
from pathlib import Path

from tapps_mcp.project.impact_analyzer import _is_test_file
from tapps_mcp.project.report import _build_summary, _render_markdown
from tapps_mcp.server_scoring_tools import _function_cc
from tapps_mcp.tools.parallel import ParallelResults, _mark_tool_failure
from tapps_mcp.tools.perflint import parse_perflint_json


class TestEmptyReportSummary:
    def test_empty_summary_has_avg_score(self) -> None:
        summary = _build_summary([], None)
        assert summary["files_scored"] == 0
        assert summary["avg_score"] == 0.0
        # Must not KeyError when rendering markdown with zero files.
        md = _render_markdown("Empty", [], None, summary)
        assert "Avg score" in md


class TestParallelToolFailureMarking:
    def test_bandit_failure_triggers_fallback_signals(self) -> None:
        results = ParallelResults()
        _mark_tool_failure("bandit", results)
        assert "bandit" in results.missing_tools
        assert "bandit" in results.tool_parse_failures

    def test_radon_mi_failure_marks_radon_missing(self) -> None:
        results = ParallelResults()
        _mark_tool_failure("radon_mi", results)
        assert "radon" in results.missing_tools
        assert results.radon_mi == 50.0  # default unchanged; scorer must fall back


class TestNestedFunctionCc:
    def test_nested_def_does_not_inflate_outer_cc(self) -> None:
        src = """
def outer(x):
    if x:
        return 1
    def inner(y):
        if y:
            return 2
        if y > 1:
            return 3
        return 0
    return 0
"""
        tree = ast.parse(src)
        outer = tree.body[0]
        assert isinstance(outer, ast.FunctionDef)
        # Outer has one branch (if x) → CC 2. Nested ifs must not inflate.
        assert _function_cc(outer) == 2


class TestIsTestFileLayout:
    def test_test_dir_layout_recognized(self) -> None:
        assert _is_test_file(Path("test/unit/foo_test.py"))
        assert _is_test_file(Path("tests/unit/test_foo.py"))
        assert not _is_test_file(Path("src/contest.py"))


class TestPerflintNullCoords:
    def test_null_coords_do_not_crash(self) -> None:
        findings = parse_perflint_json(
            '[{"message-id":"W8101","symbol":"x","message":"m","path":"a.py","line":null,"column":null}]'
        )
        assert findings[0].line == 0

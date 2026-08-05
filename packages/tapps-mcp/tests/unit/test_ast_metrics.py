"""Tests for the AST metric functions behind the scoring categories (TAP-5628).

These are the fallbacks the scorer uses when radon is unavailable, so their
behaviour decides scores on any machine without the external checkers.
"""

from __future__ import annotations

import ast

from tapps_mcp.scoring.ast_metrics import (
    AstMetricsMixin,
    _halstead_issues,
    _max_nesting_depth,
    _num,
)

SIMPLE = "def f(x):\n    return x + 1\n"
BRANCHY = """
def f(x):
    if x > 0:
        for i in range(x):
            while i:
                if i % 2:
                    i -= 1
    return x
"""


class TestParseAstSafe:
    def test_valid_code_parses(self) -> None:
        assert AstMetricsMixin._parse_ast_safe(SIMPLE) is not None

    def test_syntax_error_returns_none_rather_than_raising(self) -> None:
        assert AstMetricsMixin._parse_ast_safe("def (:\n") is None


class TestAstComplexity:
    def test_branchy_code_reports_more_than_simple_code(self) -> None:
        """Returns max per-function CC scaled by 5 — higher means more complex."""
        assert AstMetricsMixin._ast_complexity(BRANCHY) > AstMetricsMixin._ast_complexity(SIMPLE)

    def test_a_branchless_function_is_cc_one(self) -> None:
        assert AstMetricsMixin._ast_complexity(SIMPLE) == 1 / 5.0

    def test_module_level_branches_count_when_there_are_no_functions(self) -> None:
        assert AstMetricsMixin._ast_complexity("if x:\n    y = 1\n") == 2 / 5.0

    def test_nested_branches_are_charged_to_the_inner_function_only(self) -> None:
        """`outer` stays CC 1; the `if` belongs to `inner`, and max wins.

        Were the branch charged to the enclosing function too, the maximum
        would be 3 rather than 2.
        """
        nested = "def outer():\n    def inner():\n        if x:\n            return 1\n    return inner\n"
        assert AstMetricsMixin._ast_complexity(nested) == 2 / 5.0

    def test_score_stays_in_range(self) -> None:
        for code in (SIMPLE, BRANCHY, ""):
            assert 0.0 <= AstMetricsMixin._ast_complexity(code) <= 10.0

    def test_unparseable_code_is_neutral(self) -> None:
        assert AstMetricsMixin._ast_complexity("def (:\n") == 5.0


class TestHeuristicSecurity:
    def test_clean_code_scores_full(self) -> None:
        assert AstMetricsMixin._heuristic_security(SIMPLE) == 10.0

    def test_each_insecure_pattern_costs_score(self) -> None:
        one = AstMetricsMixin._heuristic_security("eval(user_input)")
        two = AstMetricsMixin._heuristic_security("eval(user_input)\nexec(other)")
        assert one < 10.0
        assert two < one


class TestAstMaintainability:
    def test_docstrings_help(self) -> None:
        documented = '"""Module."""\n\n\ndef f():\n    """Do a thing."""\n    return 1\n'
        bare = "def f():\n    return 1\n"
        assert AstMetricsMixin._ast_maintainability(documented) >= (
            AstMetricsMixin._ast_maintainability(bare)
        )

    def test_score_stays_in_range(self) -> None:
        assert 0.0 <= AstMetricsMixin._ast_maintainability(BRANCHY) <= 10.0


class TestAstPerformance:
    def test_nested_loops_are_reported(self) -> None:
        code = "def f(rows, cols):\n    for r in rows:\n        for c in cols:\n            print(r, c)\n"
        score, issues = AstMetricsMixin._ast_performance_detailed(code)
        assert issues
        assert score < 10.0

    def test_clean_code_reports_nothing(self) -> None:
        score, issues = AstMetricsMixin._ast_performance_detailed(SIMPLE)
        assert issues == []
        assert score == 10.0

    def test_unparseable_code_scores_zero(self) -> None:
        assert AstMetricsMixin._ast_performance_detailed("def (:\n") == (0.0, [])


class TestMaxNestingDepth:
    def test_flat_code_has_shallow_depth(self) -> None:
        assert _max_nesting_depth(ast.parse(SIMPLE)) < _max_nesting_depth(ast.parse(BRANCHY))

    def test_depth_counts_nested_blocks(self) -> None:
        assert _max_nesting_depth(ast.parse(BRANCHY)) >= 4


class TestNum:
    def test_numeric_values_convert(self) -> None:
        assert _num(3) == 3.0
        assert _num(2.5) == 2.5

    def test_numeric_strings_are_not_coerced(self) -> None:
        """Radon emits numbers; a string here means the shape changed."""
        assert _num("2.5") == 0.0

    def test_non_numeric_falls_back_to_the_default(self) -> None:
        assert _num(object(), default=1.5) == 1.5
        assert _num(None) == 0.0


class TestHalsteadIssues:
    def test_quiet_metrics_report_nothing(self) -> None:
        assert _halstead_issues([{"volume": 10, "difficulty": 1, "effort": 10, "bugs": 0.0}]) == []

    def test_extreme_volume_is_reported(self) -> None:
        entries = [{"volume": 10_000_000, "difficulty": 999, "effort": 10**9, "bugs": 50.0}]
        assert _halstead_issues(entries)

    def test_empty_input_is_safe(self) -> None:
        assert _halstead_issues([]) == []

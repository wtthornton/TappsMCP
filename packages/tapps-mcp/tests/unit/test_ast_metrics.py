"""Tests for the AST metric functions behind the scoring categories (TAP-5628).

These are the fallbacks the scorer uses when radon is unavailable, so their
behaviour decides scores on any machine without the external checkers.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tapps_mcp.scoring.ast_metrics import (
    AstMetricsMixin,
    _halstead_issues,
    _max_nesting_depth,
    _num,
)
from tapps_mcp.scoring.coverage_heuristic import (
    _count_test_files,
    _member_defines_stem,
    _test_roots,
    _tests_import_module,
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


@pytest.fixture(autouse=True)
def _clear_coverage_heuristic_caches() -> None:
    """Both helpers below are ``lru_cache``d on a ``Path`` argument; tmp_path

    reuse across tests would stick otherwise.
    """
    _test_roots.cache_clear()
    _member_defines_stem.cache_clear()


def _workspace(root: Path, member_names: tuple[str, ...] = ("alpha", "beta")) -> None:
    root.joinpath("pyproject.toml").write_text('[tool.uv.workspace]\nmembers = ["packages/*"]\n')
    for member in member_names:
        (root / "packages" / member / "tests" / "unit").mkdir(parents=True)
        (root / "packages" / member / "src").mkdir(parents=True)
    (root / "scripts").mkdir()


class TestCoverageHeuristicImportlibLoad:
    """TAP-5847: a script loaded by path (not a plain ``import`` statement)."""

    def test_importlib_loaded_module_is_credited(self, tmp_path: Path) -> None:
        _workspace(tmp_path)
        test_file = tmp_path / "packages" / "alpha" / "tests" / "unit" / "test_loader.py"
        test_file.write_text(
            "import importlib.util\n"
            "\n"
            "def _load():\n"
            '    return _load_module("compare")\n'
        )
        script = tmp_path / "scripts" / "compare.py"

        assert _tests_import_module(tmp_path, script) is True

    def test_plain_string_mention_without_importlib_is_not_credited(
        self, tmp_path: Path
    ) -> None:
        """The importlib-loaded heuristic is gated on ``importlib`` appearing

        in the file too — a bare string mention of the stem elsewhere must
        not be enough on its own.
        """
        _workspace(tmp_path)
        test_file = tmp_path / "packages" / "alpha" / "tests" / "unit" / "test_unrelated.py"
        test_file.write_text('NAME = "compare"\n')
        script = tmp_path / "scripts" / "compare.py"

        assert _tests_import_module(tmp_path, script) is False


class TestCoverageHeuristicStemCollision:
    """TAP-5847: a workspace member's own file must not lend its test to an

    unrelated top-level file that merely shares the stem.
    """

    def test_member_owned_stem_is_not_credited_to_an_outside_file(
        self, tmp_path: Path
    ) -> None:
        _workspace(tmp_path)
        (tmp_path / "packages" / "alpha" / "src" / "report.py").write_text("X = 1\n")
        (tmp_path / "packages" / "alpha" / "tests" / "unit" / "test_report.py").touch()

        assert _count_test_files(tmp_path, "report") == (0, 0)

    def test_member_without_its_own_source_file_still_credits_a_script(
        self, tmp_path: Path
    ) -> None:
        """The TAP-5619 case must still work: a member's test file with no

        competing same-stem source file in that member is real credit for a
        top-level script.
        """
        _workspace(tmp_path)
        (tmp_path / "packages" / "alpha" / "tests" / "unit" / "test_widget.py").touch()

        assert _count_test_files(tmp_path, "widget") == (1, 0)


class TestHalsteadIssues:
    def test_quiet_metrics_report_nothing(self) -> None:
        assert _halstead_issues([{"volume": 10, "difficulty": 1, "effort": 10, "bugs": 0.0}]) == []

    def test_extreme_volume_is_reported(self) -> None:
        entries = [{"volume": 10_000_000, "difficulty": 999, "effort": 10**9, "bugs": 50.0}]
        assert _halstead_issues(entries)

    def test_empty_input_is_safe(self) -> None:
        assert _halstead_issues([]) == []

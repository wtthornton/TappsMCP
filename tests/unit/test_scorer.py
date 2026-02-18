"""Tests for scoring.scorer — the main scoring engine."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tapps_mcp.scoring.models import LintIssue
from tapps_mcp.scoring.scorer import (
    CodeScorer,
    _find_project_root,
    _max_nesting_depth,
    _suggest_complexity,
    _suggest_devex,
    _suggest_maintainability,
    _suggest_performance,
    _suggest_security,
    _suggest_structure,
    _suggest_test_coverage,
)
from tapps_mcp.tools.parallel import ParallelResults


class TestCodeScorerQuick:
    """Tests for score_file_quick (ruff-only mode)."""

    @patch("tapps_mcp.scoring.scorer.run_ruff_check")
    def test_clean_file(self, mock_ruff, tmp_path):
        mock_ruff.return_value = []
        f = tmp_path / "clean.py"
        f.write_text("x = 1\n", encoding="utf-8")

        scorer = CodeScorer()
        result = scorer.score_file_quick(f)
        assert result.overall_score == 100.0
        assert "linting" in result.categories
        assert result.degraded is False

    @patch("tapps_mcp.scoring.scorer.run_ruff_check")
    def test_with_issues(self, mock_ruff, tmp_path):
        mock_ruff.return_value = [
            LintIssue(code="E501", message="Line too long", file="t.py", line=1),
        ]
        f = tmp_path / "bad.py"
        f.write_text("x = 1\n", encoding="utf-8")

        scorer = CodeScorer()
        result = scorer.score_file_quick(f)
        # 10.0 - 2.0 = 8.0 → 80.0 overall
        assert result.overall_score == 80.0


class TestCodeScorerFull:
    """Tests for score_file (full async mode)."""

    @pytest.mark.asyncio
    async def test_full_score_all_tools(self, tmp_path):
        f = tmp_path / "sample.py"
        f.write_text(
            '"""Module doc."""\n\ndef hello():\n    """Say hello."""\n    return "hi"\n',
            encoding="utf-8",
        )
        # Create project markers so heuristics work
        (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        (tmp_path / ".git").mkdir()
        (tmp_path / "tests").mkdir()

        parallel = ParallelResults(
            lint_issues=[],
            type_issues=[],
            security_issues=[],
            radon_cc=[{"name": "hello", "complexity": 1}],
            radon_mi=85.0,
        )

        with patch("tapps_mcp.scoring.scorer.run_all_tools", new_callable=AsyncMock) as mock_tools:
            mock_tools.return_value = parallel
            scorer = CodeScorer()
            result = await scorer.score_file(f)

        assert 0.0 <= result.overall_score <= 100.0
        assert "complexity" in result.categories
        assert "security" in result.categories
        assert "maintainability" in result.categories
        assert "test_coverage" in result.categories
        assert "performance" in result.categories
        assert "structure" in result.categories
        assert "devex" in result.categories
        assert result.degraded is False

    @pytest.mark.asyncio
    async def test_degraded_when_tools_missing(self, tmp_path):
        f = tmp_path / "sample.py"
        f.write_text("x = 1\n", encoding="utf-8")

        parallel = ParallelResults(
            missing_tools=["bandit", "radon"],
            degraded=True,
        )

        with patch("tapps_mcp.scoring.scorer.run_all_tools", new_callable=AsyncMock) as mock_tools:
            mock_tools.return_value = parallel
            scorer = CodeScorer()
            result = await scorer.score_file(f)

        assert result.degraded is True
        assert "bandit" in result.missing_tools

    @pytest.mark.asyncio
    async def test_unreadable_file(self, tmp_path):
        scorer = CodeScorer()
        # Non-existent file
        result = await scorer.score_file(tmp_path / "nonexistent.py")
        assert result.overall_score == 0.0
        assert result.degraded is True


class TestCodeScorerSync:
    @patch("tapps_mcp.scoring.scorer.run_all_tools", new_callable=AsyncMock)
    def test_sync_wrapper(self, mock_tools, tmp_path):
        f = tmp_path / "sample.py"
        f.write_text("x = 1\n", encoding="utf-8")
        mock_tools.return_value = ParallelResults()

        scorer = CodeScorer()
        result = scorer.score_file_sync(f)
        assert result.file_path == str(f.resolve())


class TestAstComplexity:
    def test_simple_code(self):
        code = "x = 1\ny = 2"
        score = CodeScorer._ast_complexity(code)
        assert 0.0 <= score <= 10.0

    def test_complex_code(self):
        code = """
def f(x):
    if x > 0:
        for i in range(x):
            while i > 0:
                if i % 2 == 0:
                    try:
                        pass
                    except Exception:
                        pass
                i -= 1
"""
        score = CodeScorer._ast_complexity(code)
        assert score > 1.0

    def test_syntax_error(self):
        score = CodeScorer._ast_complexity("def f(:\n")
        assert score == 10.0


class TestHeuristicSecurity:
    def test_clean_code(self):
        score = CodeScorer._heuristic_security("x = 1")
        assert score == 10.0

    def test_eval_usage(self):
        score = CodeScorer._heuristic_security("result = eval(user_input)")
        assert score < 10.0

    def test_multiple_insecure_patterns(self):
        code = "eval(x)\nexec(y)\nos.system(cmd)"
        score = CodeScorer._heuristic_security(code)
        assert score <= 4.0


class TestAstMaintainability:
    def test_short_with_docstring(self):
        code = '"""Module."""\nx = 1'
        score = CodeScorer._ast_maintainability(code)
        assert score >= 7.0

    def test_long_file_penalty(self):
        code = "\n".join(f"x_{i} = {i}" for i in range(350))
        score = CodeScorer._ast_maintainability(code)
        assert score <= 7.0

    def test_no_docstring_penalty(self):
        code = "x = 1\ny = 2"
        score = CodeScorer._ast_maintainability(code)
        assert score <= 8.0


class TestCoverageHeuristic:
    def test_test_file_gets_score(self, tmp_path):
        f = tmp_path / "test_something.py"
        f.write_text("pass", encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        assert CodeScorer._coverage_heuristic(f) == 5.0

    def test_file_with_matching_test(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_app.py").write_text("pass", encoding="utf-8")
        src = tmp_path / "app.py"
        src.write_text("pass", encoding="utf-8")
        assert CodeScorer._coverage_heuristic(src) == 5.0

    def test_file_without_test(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        src = tmp_path / "app.py"
        src.write_text("pass", encoding="utf-8")
        assert CodeScorer._coverage_heuristic(src) == 0.0

    def test_fuzzy_match_scores_3(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        (tmp_path / "tests").mkdir()
        # test_server_tools.py is a fuzzy match for server.py
        (tmp_path / "tests" / "test_server_tools.py").write_text("pass", encoding="utf-8")
        src = tmp_path / "server.py"
        src.write_text("pass", encoding="utf-8")
        assert CodeScorer._coverage_heuristic(src) == 3.0

    def test_multiple_test_files_scores_7(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "unit").mkdir()
        # Exact match + fuzzy match = 2 files
        (tmp_path / "tests" / "test_server.py").write_text("pass", encoding="utf-8")
        (tmp_path / "tests" / "unit" / "test_server_tools.py").write_text("pass", encoding="utf-8")
        src = tmp_path / "server.py"
        src.write_text("pass", encoding="utf-8")
        assert CodeScorer._coverage_heuristic(src) == 7.0

    def test_exact_match_preferred_over_fuzzy(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        (tmp_path / "tests").mkdir()
        # Only exact match, no fuzzy
        (tmp_path / "tests" / "test_app.py").write_text("pass", encoding="utf-8")
        src = tmp_path / "app.py"
        src.write_text("pass", encoding="utf-8")
        assert CodeScorer._coverage_heuristic(src) == 5.0


class TestStructureScore:
    def test_full_project(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        (tmp_path / "README.md").write_text("", encoding="utf-8")
        (tmp_path / "tests").mkdir()
        (tmp_path / ".git").mkdir()
        f = tmp_path / "app.py"
        f.write_text("pass", encoding="utf-8")
        score = CodeScorer._structure_score(f)
        assert score >= 5.0

    def test_minimal_project(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        f = tmp_path / "app.py"
        f.write_text("pass", encoding="utf-8")
        score = CodeScorer._structure_score(f)
        assert score > 0.0


class TestDevexScore:
    def test_with_agents_md(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")
        (tmp_path / "AGENTS.md").write_text("", encoding="utf-8")
        (tmp_path / "docs").mkdir()
        f = tmp_path / "app.py"
        f.write_text("pass", encoding="utf-8")
        score = CodeScorer._devex_score(f)
        assert score >= 5.0

    def test_bare_project(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        f = tmp_path / "app.py"
        f.write_text("pass", encoding="utf-8")
        score = CodeScorer._devex_score(f)
        assert score >= 0.0


class TestAstPerformance:
    def test_clean_code(self):
        code = "def f():\n    return 1"
        score = CodeScorer._ast_performance(code)
        assert score == 10.0

    def test_nested_loops(self):
        code = "for i in range(10):\n    for j in range(10):\n        pass"
        score = CodeScorer._ast_performance(code)
        assert score < 10.0

    def test_syntax_error(self):
        score = CodeScorer._ast_performance("def f(:\n")
        assert score == 0.0


class TestFindProjectRoot:
    def test_with_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
        sub = tmp_path / "src"
        sub.mkdir()
        f = sub / "app.py"
        f.write_text("pass", encoding="utf-8")
        root = _find_project_root(f)
        assert root == tmp_path

    def test_with_git(self, tmp_path):
        (tmp_path / ".git").mkdir()
        f = tmp_path / "app.py"
        f.write_text("pass", encoding="utf-8")
        root = _find_project_root(f)
        assert root == tmp_path

    def test_no_markers(self, tmp_path):
        # Create a deeply nested path with no markers
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        f = deep / "app.py"
        f.write_text("pass", encoding="utf-8")
        root = _find_project_root(f)
        # Could be None or could find a parent — depends on system
        # Just verify it doesn't crash
        assert root is None or isinstance(root, Path)


class TestMaxNestingDepth:
    def test_flat_function(self):
        import ast

        code = "def f():\n    x = 1\n    return x"
        tree = ast.parse(code)
        func = tree.body[0]
        depth = _max_nesting_depth(func)
        assert depth == 0

    def test_nested_if(self):
        import ast

        code = "def f():\n    if True:\n        if True:\n            pass"
        tree = ast.parse(code)
        func = tree.body[0]
        depth = _max_nesting_depth(func)
        assert depth == 2

    def test_mixed_nesting(self):
        import ast

        code = (
            "def f():\n    for i in range(10):\n        while True:\n            "
            "if i:\n                pass"
        )
        tree = ast.parse(code)
        func = tree.body[0]
        depth = _max_nesting_depth(func)
        assert depth == 3


class TestOverallCalculation:
    def test_complexity_inverted(self):
        """Complexity should be inverted: (10 - score) * weight."""
        from tapps_mcp.scoring.models import CategoryScore

        scorer = CodeScorer()
        cats = {
            "complexity": CategoryScore(name="complexity", score=2.0, weight=1.0),
        }
        overall = scorer._calculate_overall(cats)
        # (10 - 2) * 1.0 * 10 = 80.0
        assert abs(overall - 80.0) < 0.01

    def test_non_complexity_direct(self):
        from tapps_mcp.scoring.models import CategoryScore

        scorer = CodeScorer()
        cats = {
            "security": CategoryScore(name="security", score=8.0, weight=1.0),
        }
        overall = scorer._calculate_overall(cats)
        # 8.0 * 1.0 * 10 = 80.0
        assert abs(overall - 80.0) < 0.01

    def test_zero_weight_excluded(self):
        from tapps_mcp.scoring.models import CategoryScore

        scorer = CodeScorer()
        cats = {
            "linting": CategoryScore(name="linting", score=5.0, weight=0.0),
        }
        overall = scorer._calculate_overall(cats)
        assert overall == 0.0


# ------------------------------------------------------------------
# Suggestion generator tests
# ------------------------------------------------------------------


class TestSuggestComplexity:
    def test_high_cc_with_radon(self):
        tips = _suggest_complexity(
            8.0, {"max_cc": 15, "max_cc_function": "parse_data"}, using_radon=True
        )
        assert len(tips) == 1
        assert "parse_data" in tips[0]
        assert "CC=15" in tips[0]
        assert "below 10" in tips[0]

    def test_moderate_cc_with_radon(self):
        tips = _suggest_complexity(
            4.0, {"max_cc": 7, "max_cc_function": "process"}, using_radon=True
        )
        assert len(tips) == 1
        assert "simplifying" in tips[0]

    def test_low_cc_no_suggestions(self):
        tips = _suggest_complexity(
            1.0, {"max_cc": 3, "max_cc_function": "simple"}, using_radon=True
        )
        assert tips == []

    def test_fallback_without_radon(self):
        tips = _suggest_complexity(5.0, {"fallback": True}, using_radon=False)
        assert len(tips) == 1
        assert "radon" in tips[0].lower()


class TestSuggestSecurity:
    def test_issues_found(self):
        tips = _suggest_security(6.0, {"issue_count": 3})
        assert len(tips) == 1
        assert "3 security issue" in tips[0]

    def test_patterns_found(self):
        tips = _suggest_security(
            6.0, {"issue_count": 0, "patterns_found": ["eval(", "exec("]}
        )
        assert len(tips) == 1
        assert "eval(" in tips[0]

    def test_clean_no_suggestions(self):
        tips = _suggest_security(10.0, {"issue_count": 0})
        assert tips == []


class TestSuggestMaintainability:
    def test_very_low_mi(self):
        tips = _suggest_maintainability(
            2.0, {"mi_value": 15, "has_docstring": True, "line_count": 100}
        )
        assert any("MI=15" in t for t in tips)
        assert any("very low" in t for t in tips)

    def test_low_mi(self):
        tips = _suggest_maintainability(
            3.5, {"mi_value": 35, "has_docstring": True, "line_count": 100}
        )
        assert any("MI=35" in t for t in tips)

    def test_no_docstring(self):
        tips = _suggest_maintainability(
            7.0, {"mi_value": 80, "has_docstring": False, "line_count": 50}
        )
        assert any("docstring" in t.lower() for t in tips)

    def test_long_file(self):
        tips = _suggest_maintainability(
            6.0, {"mi_value": 60, "has_docstring": True, "line_count": 400}
        )
        assert any("400 lines" in t for t in tips)

    def test_good_score_no_suggestions(self):
        tips = _suggest_maintainability(
            9.0, {"mi_value": 90, "has_docstring": True, "line_count": 50}
        )
        assert tips == []


class TestSuggestTestCoverage:
    def test_no_test_file(self):
        tips = _suggest_test_coverage(0, {"stem": "mymodule", "is_test_file": False})
        assert len(tips) == 1
        assert "test_mymodule.py" in tips[0]

    def test_is_test_file(self):
        tips = _suggest_test_coverage(5, {"stem": "test_foo", "is_test_file": True})
        assert len(tips) == 1
        assert "test file" in tips[0].lower()

    def test_has_test_no_suggestions(self):
        tips = _suggest_test_coverage(5, {"stem": "app", "is_test_file": False})
        assert tips == []


class TestSuggestPerformance:
    def test_nested_loops(self):
        tips = _suggest_performance(8.5, {"issues_found": ["nested_loops"]})
        assert len(tips) == 1
        assert "Nested for-loops" in tips[0]

    def test_very_large_function(self):
        tips = _suggest_performance(8.5, {"issues_found": ["very_large_function"]})
        assert len(tips) == 1
        assert "100 lines" in tips[0]

    def test_deep_nesting(self):
        tips = _suggest_performance(9.0, {"issues_found": ["deep_nesting"]})
        assert len(tips) == 1
        assert "depth" in tips[0].lower()

    def test_multiple_issues(self):
        tips = _suggest_performance(
            6.0, {"issues_found": ["large_function", "nested_loops", "expensive_comprehension"]}
        )
        assert len(tips) == 3

    def test_clean_no_suggestions(self):
        tips = _suggest_performance(10.0, {"issues_found": []})
        assert tips == []


class TestSuggestStructure:
    def test_low_score(self):
        tips = _suggest_structure(3.0)
        assert len(tips) == 1
        assert "pyproject.toml" in tips[0]

    def test_good_score(self):
        tips = _suggest_structure(8.0)
        assert tips == []


class TestSuggestDevex:
    def test_low_score(self):
        tips = _suggest_devex(3.0)
        assert len(tips) == 1
        assert "CLAUDE.md" in tips[0]

    def test_good_score(self):
        tips = _suggest_devex(8.0)
        assert tips == []


class TestSuggestionsInScoring:
    """Integration: suggestions are populated when scoring a file."""

    @pytest.mark.asyncio
    async def test_suggestions_populated_in_full_score(self, tmp_path):
        f = tmp_path / "sample.py"
        f.write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        (tmp_path / ".git").mkdir()
        (tmp_path / "tests").mkdir()

        parallel = ParallelResults(
            lint_issues=[],
            type_issues=[],
            security_issues=[],
            radon_cc=[{"name": "big_func", "complexity": 12}],
            radon_mi=85.0,
        )

        with patch("tapps_mcp.scoring.scorer.run_all_tools", new_callable=AsyncMock) as mock_tools:
            mock_tools.return_value = parallel
            scorer = CodeScorer()
            result = await scorer.score_file(f)

        # Complexity should have a suggestion about high CC
        cplx = result.categories["complexity"]
        assert len(cplx.suggestions) >= 1
        assert "big_func" in cplx.suggestions[0]

        # Test coverage should suggest creating a test file
        cov = result.categories["test_coverage"]
        assert len(cov.suggestions) >= 1
        assert "test_sample.py" in cov.suggestions[0]

    @pytest.mark.asyncio
    async def test_no_suggestions_for_perfect_file(self, tmp_path):
        f = tmp_path / "sample.py"
        f.write_text(
            '"""Module doc."""\n\ndef hello():\n    """Say hello."""\n    return "hi"\n',
            encoding="utf-8",
        )
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")
        (tmp_path / ".git").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_sample.py").write_text("pass\n", encoding="utf-8")
        (tmp_path / "CLAUDE.md").write_text("x\n", encoding="utf-8")
        (tmp_path / "docs").mkdir()

        parallel = ParallelResults(
            lint_issues=[],
            type_issues=[],
            security_issues=[],
            radon_cc=[{"name": "hello", "complexity": 1}],
            radon_mi=95.0,
        )

        with patch("tapps_mcp.scoring.scorer.run_all_tools", new_callable=AsyncMock) as mock_tools:
            mock_tools.return_value = parallel
            scorer = CodeScorer()
            result = await scorer.score_file(f)

        # Well-structured file with good scores should have minimal suggestions
        total_suggestions = sum(len(c.suggestions) for c in result.categories.values())
        assert total_suggestions == 0

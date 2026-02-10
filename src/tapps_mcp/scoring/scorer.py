"""Main scoring engine — 7-category code quality scoring.

Scores Python files across seven categories:
  complexity, security, maintainability, test_coverage,
  performance, structure, devex

Each category produces a 0-10 score.  The overall score (0-100) is the
weighted sum ``Σ(category_score * weight) * 10``, with ``complexity``
inverted (10 - score) because lower complexity is better.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path  # noqa: TC003 — used at runtime
from typing import ClassVar

import structlog

from tapps_mcp.config.settings import ScoringWeights, TappsMCPSettings, load_settings
from tapps_mcp.scoring.constants import (
    DEEP_NESTING_THRESHOLD,
    INSECURE_PATTERN_PENALTY,
    LARGE_FUNCTION_LINES,
    PERFORMANCE_PENALTY_MAP,
    VERY_DEEP_NESTING_THRESHOLD,
    VERY_LARGE_FUNCTION_LINES,
    clamp_individual,
    clamp_overall,
)
from tapps_mcp.scoring.models import CategoryScore, ScoreResult
from tapps_mcp.tools.bandit import calculate_security_score
from tapps_mcp.tools.mypy import calculate_type_score
from tapps_mcp.tools.parallel import ParallelResults, run_all_tools
from tapps_mcp.tools.radon import calculate_complexity_score, calculate_maintainability_score
from tapps_mcp.tools.ruff import calculate_lint_score, run_ruff_check

logger = structlog.get_logger(__name__)

# Insecure patterns for heuristic security scoring
_INSECURE_PATTERNS: list[str] = [
    "eval(",
    "exec(",
    "__import__",
    "pickle.loads",
    "subprocess.call",
    "os.system",
]


class CodeScorer:
    """Score Python files across 7 quality categories."""

    def __init__(
        self,
        settings: TappsMCPSettings | None = None,
        weights: ScoringWeights | None = None,
    ) -> None:
        self._settings = settings or load_settings()
        self._weights = weights or self._settings.scoring_weights

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score_file_quick(self, file_path: Path) -> ScoreResult:
        """Quick mode: ruff-only scoring (< 500 ms target)."""
        resolved = file_path.resolve()
        issues = run_ruff_check(str(resolved), cwd=str(resolved.parent))
        lint_score = calculate_lint_score(issues)

        categories = {
            "linting": CategoryScore(
                name="linting",
                score=lint_score,
                weight=1.0,
                details={"issue_count": len(issues)},
            ),
        }

        return ScoreResult(
            file_path=str(resolved),
            categories=categories,
            overall_score=clamp_overall(lint_score * 10.0),
            lint_issues=issues,
            degraded=False,
        )

    async def score_file(self, file_path: Path) -> ScoreResult:
        """Full mode: parallel ruff + mypy + bandit + radon → 7-category score."""
        resolved = file_path.resolve()
        str_path = str(resolved)
        cwd = str(resolved.parent)
        timeout = self._settings.tool_timeout

        # Read code for AST-based analysis
        try:
            code = resolved.read_text(encoding="utf-8", errors="replace")
        except (OSError, PermissionError) as exc:
            logger.error("file_read_failed", path=str_path, error=str(exc))
            return self._error_result(str_path, str(exc))

        # Run external tools in parallel
        parallel = await run_all_tools(
            str_path,
            cwd=cwd,
            timeout=timeout,
        )

        # Build category scores
        categories = self._build_categories(code, resolved, parallel)
        overall = self._calculate_overall(categories)

        return ScoreResult(
            file_path=str_path,
            categories=categories,
            overall_score=overall,
            lint_issues=parallel.lint_issues,
            type_issues=parallel.type_issues,
            security_issues=parallel.security_issues,
            degraded=parallel.degraded,
            missing_tools=parallel.missing_tools,
        )

    def score_file_sync(self, file_path: Path) -> ScoreResult:
        """Synchronous wrapper around the async ``score_file``."""
        return asyncio.run(self.score_file(file_path))

    # ------------------------------------------------------------------
    # Internal: category computation
    # ------------------------------------------------------------------

    def _build_categories(
        self,
        code: str,
        file_path: Path,
        parallel: ParallelResults,
    ) -> dict[str, CategoryScore]:
        w = self._weights
        cats: dict[str, CategoryScore] = {}

        # 1) Complexity (radon cc → 0-10, lower complexity = higher quality)
        if parallel.radon_cc:
            complexity_raw = calculate_complexity_score(parallel.radon_cc)
        else:
            complexity_raw = self._ast_complexity(code)
        cats["complexity"] = CategoryScore(
            name="complexity",
            score=complexity_raw,
            weight=w.complexity,
            details={"functions_analysed": len(parallel.radon_cc)},
        )

        # 2) Security (bandit → 0-10)
        if parallel.security_issues or "bandit" not in parallel.missing_tools:
            sec_score = calculate_security_score(parallel.security_issues)
        else:
            sec_score = self._heuristic_security(code)
        cats["security"] = CategoryScore(
            name="security",
            score=sec_score,
            weight=w.security,
            details={"issue_count": len(parallel.security_issues)},
        )

        # 3) Maintainability (radon mi → 0-10)
        if "radon" not in parallel.missing_tools:
            maint_score = calculate_maintainability_score(parallel.radon_mi)
        else:
            maint_score = self._ast_maintainability(code)
        cats["maintainability"] = CategoryScore(
            name="maintainability",
            score=maint_score,
            weight=w.maintainability,
            details={"mi_value": parallel.radon_mi},
        )

        # 4) Test coverage (heuristic)
        coverage = self._coverage_heuristic(file_path)
        cats["test_coverage"] = CategoryScore(
            name="test_coverage",
            score=coverage,
            weight=w.test_coverage,
        )

        # 5) Performance (AST-based)
        perf = self._ast_performance(code)
        cats["performance"] = CategoryScore(
            name="performance",
            score=perf,
            weight=w.performance,
        )

        # 6) Structure (project layout)
        structure = self._structure_score(file_path)
        cats["structure"] = CategoryScore(
            name="structure",
            score=structure,
            weight=w.structure,
        )

        # 7) DevEx (tooling / docs)
        devex = self._devex_score(file_path)
        cats["devex"] = CategoryScore(
            name="devex",
            score=devex,
            weight=w.devex,
        )

        # Bonus: linting & type-checking (informational, not weighted in overall)
        lint_s = calculate_lint_score(parallel.lint_issues)
        cats["linting"] = CategoryScore(
            name="linting",
            score=lint_s,
            weight=0.0,
            details={"issue_count": len(parallel.lint_issues)},
        )
        type_s = calculate_type_score(parallel.type_issues)
        cats["type_checking"] = CategoryScore(
            name="type_checking",
            score=type_s,
            weight=0.0,
            details={"issue_count": len(parallel.type_issues)},
        )

        return cats

    def _calculate_overall(self, categories: dict[str, CategoryScore]) -> float:
        """Weighted overall score (0-100).

        ``complexity`` is inverted: (10 - complexity_score) * weight.
        """
        total = 0.0
        for cat in categories.values():
            if cat.weight <= 0:
                continue
            if cat.name == "complexity":
                total += (10.0 - cat.score) * cat.weight
            else:
                total += cat.score * cat.weight
        return clamp_overall(total * 10.0)

    # ------------------------------------------------------------------
    # Fallback heuristics (when external tools are unavailable)
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_ast_safe(code: str) -> ast.Module | None:
        """Parse code into an AST, returning None on SyntaxError."""
        try:
            return ast.parse(code)
        except SyntaxError:
            return None

    @staticmethod
    def _ast_complexity(code: str) -> float:
        """Fallback complexity from AST cyclomatic complexity."""
        tree = CodeScorer._parse_ast_safe(code)
        if tree is None:
            return 10.0
        max_cc = 1
        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.For, ast.While, ast.ExceptHandler)):
                max_cc += 1
        return clamp_individual(max_cc / 5.0)

    @staticmethod
    def _heuristic_security(code: str) -> float:
        """Fallback security score from pattern matching."""
        issues = sum(1 for p in _INSECURE_PATTERNS if p in code)
        return clamp_individual(10.0 - issues * INSECURE_PATTERN_PENALTY)

    @staticmethod
    def _check_project_signals(
        file_path: Path,
        signals: list[tuple[float, list[str]]],
    ) -> float:
        """Score based on project file existence.

        *signals* is a list of ``(points, file_names)`` tuples.
        Returns a 0-10 clamped score.
        """
        root = _find_project_root(file_path)
        if root is None:
            return 5.0
        pts = sum(
            points
            for points, names in signals
            if any((root / n).exists() for n in names)
        )
        return clamp_individual(min(10.0, pts * 2.0))

    @staticmethod
    def _ast_maintainability(code: str) -> float:
        """Fallback maintainability from line count / docstrings."""
        lines = code.splitlines()
        line_count = len(lines)
        has_docstring = '"""' in code or "'''" in code
        # Start at 8, penalise for length, reward for docstrings
        score = 8.0
        long_file_threshold = 300
        medium_file_threshold = 150
        if line_count > long_file_threshold:
            score -= 2.0
        elif line_count > medium_file_threshold:
            score -= 1.0
        if not has_docstring:
            score -= 1.0
        return clamp_individual(score)

    @staticmethod
    def _coverage_heuristic(file_path: Path) -> float:
        """Heuristic test coverage based on test file existence."""
        root = _find_project_root(file_path)
        if root is None:
            return 0.0
        # If the file itself is a test file
        if file_path.name.startswith("test_") or file_path.name.endswith("_test.py"):
            return 5.0
        # Look for matching test files
        stem = file_path.stem
        test_dirs = ["tests", "test", "tests/unit", "tests/integration"]
        patterns = [f"test_{stem}.py", f"{stem}_test.py"]
        for td in test_dirs:
            td_path = root / td
            if td_path.is_dir():
                for pat in patterns:
                    if (td_path / pat).exists():
                        return 5.0
        return 0.0

    _STRUCTURE_SIGNALS: ClassVar[list[tuple[float, list[str]]]] = [
        (2.5, ["pyproject.toml", "package.json"]),
        (2.0, ["README", "README.md", "README.rst"]),
        (2.0, ["tests", "test"]),
        (1.0, [".git"]),
        (1.5, ["requirements.txt", "setup.py"]),
    ]

    _DEVEX_SIGNALS: ClassVar[list[tuple[float, list[str]]]] = [
        (3.0, ["AGENTS.md", "CLAUDE.md"]),
        (2.0, ["docs"]),
        (2.0, [".tapps-agents", ".cursor"]),
    ]

    @staticmethod
    def _structure_score(file_path: Path) -> float:
        """Score project layout (0-10)."""
        return CodeScorer._check_project_signals(file_path, CodeScorer._STRUCTURE_SIGNALS)

    @staticmethod
    def _devex_score(file_path: Path) -> float:
        """Score developer experience (0-10)."""
        root = _find_project_root(file_path)
        if root is None:
            return 5.0
        pts = sum(
            p for p, names in CodeScorer._DEVEX_SIGNALS
            if any((root / n).exists() for n in names)
        )
        pyproject = root / "pyproject.toml"
        if pyproject.exists():
            try:
                text = pyproject.read_text(encoding="utf-8", errors="replace")
                if any(t in text for t in ("[tool.ruff]", "[tool.mypy]", "pytest")):
                    pts += 1.5
            except OSError:
                pass
        return clamp_individual(min(10.0, pts * 2.0))

    @staticmethod
    def _ast_performance(code: str) -> float:
        """AST-based performance scoring."""
        tree = CodeScorer._parse_ast_safe(code)
        if tree is None:
            return 0.0
        seen: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                _check_function_size(node, seen)
            if isinstance(node, ast.For):
                _check_nested_for(node, seen)
            if isinstance(node, ast.ListComp):
                _check_expensive_comp(node, seen)
        penalty = sum(PERFORMANCE_PENALTY_MAP.get(i, 0.5) for i in seen)
        return clamp_individual(10.0 - penalty)

    def _error_result(self, path: str, message: str) -> ScoreResult:
        return ScoreResult(
            file_path=path,
            categories={},
            overall_score=0.0,
            degraded=True,
            missing_tools=[],
        )


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

_EXPENSIVE_CALL_THRESHOLD = 5


def _check_function_size(node: ast.FunctionDef, seen: set[str]) -> None:
    """Flag oversized functions and deeply nested control flow."""
    if hasattr(node, "end_lineno") and node.end_lineno is not None:
        func_lines = node.end_lineno - node.lineno
    else:
        func_lines = 50  # estimate
    if func_lines > VERY_LARGE_FUNCTION_LINES:
        seen.add("very_large_function")
    elif func_lines > LARGE_FUNCTION_LINES:
        seen.add("large_function")
    depth = _max_nesting_depth(node)
    if depth > VERY_DEEP_NESTING_THRESHOLD:
        seen.add("very_deep_nesting")
    elif depth > DEEP_NESTING_THRESHOLD:
        seen.add("deep_nesting")


def _check_nested_for(node: ast.For, seen: set[str]) -> None:
    """Flag nested for-loops."""
    for child in ast.walk(node):
        if isinstance(child, ast.For) and child is not node:
            seen.add("nested_loops")
            break


def _check_expensive_comp(node: ast.ListComp, seen: set[str]) -> None:
    """Flag list comprehensions with many function calls."""
    calls = sum(1 for n in ast.walk(node) if isinstance(n, ast.Call))
    if calls > _EXPENSIVE_CALL_THRESHOLD:
        seen.add("expensive_comprehension")


def _find_project_root(file_path: Path) -> Path | None:
    """Walk up from *file_path* looking for project markers."""
    current = file_path.resolve().parent
    markers = [".git", "pyproject.toml", "setup.py", "requirements.txt", "package.json"]
    for _ in range(10):
        if any((current / m).exists() for m in markers):
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def _max_nesting_depth(node: ast.AST, depth: int = 0) -> int:
    """Recursively compute max nesting depth of control structures."""
    max_d = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
            max_d = max(max_d, _max_nesting_depth(child, depth + 1))
        else:
            max_d = max(max_d, _max_nesting_depth(child, depth))
    return max_d

"""Pure AST and metric functions behind the scoring categories.

Complexity, security heuristics, maintainability, coverage, structure,
devex, and performance — each computed from source text or a parsed tree,
with no dependency on how the categories are assembled. Split out of
``scorer_categories`` under TAP-5628.

``CategoryScorersMixin`` inherits this, so ``self._ast_complexity(...)``
call sites resolve through the MRO unchanged.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import ClassVar

import structlog

from tapps_mcp.scoring.constants import (
    DEEP_NESTING_THRESHOLD,
    HALSTEAD_HIGH_BUGS,
    HALSTEAD_HIGH_DIFFICULTY,
    HALSTEAD_HIGH_EFFORT,
    HALSTEAD_HIGH_VOLUME,
    HALSTEAD_VERY_HIGH_VOLUME,
    INSECURE_PATTERN_PENALTY,
    LARGE_FUNCTION_LINES,
    PERFORMANCE_PENALTY_MAP,
    VERY_DEEP_NESTING_THRESHOLD,
    VERY_LARGE_FUNCTION_LINES,
    clamp_individual,
)
from tapps_mcp.scoring.coverage_heuristic import (
    _TEST_DIR_NAMES as _TEST_DIR_NAMES,
)
from tapps_mcp.scoring.coverage_heuristic import (
    _count_test_files as _count_test_files,
)
from tapps_mcp.scoring.coverage_heuristic import (
    _find_project_root as _find_project_root,
)
from tapps_mcp.scoring.coverage_heuristic import (
    _import_module_candidates as _import_module_candidates,
)
from tapps_mcp.scoring.coverage_heuristic import (
    _stem_token_in_name as _stem_token_in_name,
)
from tapps_mcp.scoring.coverage_heuristic import (
    _test_count_to_score as _test_count_to_score,
)
from tapps_mcp.scoring.coverage_heuristic import (
    _test_roots as _test_roots,
)
from tapps_mcp.scoring.coverage_heuristic import (
    _tests_import_module as _tests_import_module,
)
from tapps_mcp.scoring.coverage_heuristic import (
    _text_imports_module as _text_imports_module,
)
from tapps_mcp.scoring.coverage_heuristic import (
    _workspace_members as _workspace_members,
)
from tapps_mcp.scoring.scorer_base import ScorerBase

logger = structlog.get_logger(__name__)


_EXPENSIVE_CALL_THRESHOLD = 5


def _max_nesting_depth(node: ast.AST, depth: int = 0) -> int:
    """Recursively compute max nesting depth of control structures."""
    max_d = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
            max_d = max(max_d, _max_nesting_depth(child, depth + 1))
        else:
            max_d = max(max_d, _max_nesting_depth(child, depth))
    return max_d


# Insecure patterns for heuristic security scoring
_INSECURE_PATTERNS: list[str] = [
    "eval(",
    "exec(",
    "__import__",
    "pickle.loads",
    "subprocess.call",
    "os.system",
]


def _num(v: object, default: float = 0.0) -> float:
    """Safely coerce a dict value (from untyped radon output) to float."""
    if isinstance(v, (int, float)):
        return float(v)
    return default


def _halstead_issues(hal_entries: list[dict[str, object]]) -> list[str]:
    """Derive performance issue labels from Halstead metrics."""
    if not hal_entries:
        return []
    seen: set[str] = set()
    for entry in hal_entries:
        volume = _num(entry.get("volume"))
        difficulty = _num(entry.get("difficulty"))
        effort = _num(entry.get("effort"))
        bugs = _num(entry.get("bugs"))

        if volume > HALSTEAD_VERY_HIGH_VOLUME:
            seen.add("halstead_very_high_volume")
        elif volume > HALSTEAD_HIGH_VOLUME:
            seen.add("halstead_high_volume")
        if difficulty > HALSTEAD_HIGH_DIFFICULTY:
            seen.add("halstead_high_difficulty")
        if effort > HALSTEAD_HIGH_EFFORT:
            seen.add("halstead_high_effort")
        if bugs > HALSTEAD_HIGH_BUGS:
            seen.add("halstead_high_bugs")
    return sorted(seen)


def _perflint_issues(findings: Sequence[object]) -> list[str]:
    """Derive performance issue labels from perflint findings."""
    if not findings:
        return []
    seen: set[str] = set()
    for finding in findings:
        label = getattr(finding, "label", "")
        if label:
            seen.add(label)
    return sorted(seen)


def _check_function_size(node: ast.FunctionDef | ast.AsyncFunctionDef, seen: set[str]) -> None:
    """Flag oversized functions and deeply nested control flow."""
    func_lines = (
        node.end_lineno - node.lineno
        if hasattr(node, "end_lineno") and node.end_lineno is not None
        else 50
    )
    _classify_threshold(
        func_lines,
        LARGE_FUNCTION_LINES,
        VERY_LARGE_FUNCTION_LINES,
        "large_function",
        "very_large_function",
        seen,
    )
    _classify_threshold(
        _max_nesting_depth(node),
        DEEP_NESTING_THRESHOLD,
        VERY_DEEP_NESTING_THRESHOLD,
        "deep_nesting",
        "very_deep_nesting",
        seen,
    )


def _classify_threshold(
    value: float,
    moderate_threshold: float,
    severe_threshold: float,
    moderate_label: str,
    severe_label: str,
    seen: set[str],
) -> None:
    """Add a label to *seen* based on threshold comparison."""
    if value > severe_threshold:
        seen.add(severe_label)
    elif value > moderate_threshold:
        seen.add(moderate_label)


def _check_nested_for(node: ast.For | ast.AsyncFor, seen: set[str]) -> None:
    """Flag nested for-loops (sync or async) within the same function scope."""
    for child in _walk_skip_nested_defs(node):
        if isinstance(child, (ast.For, ast.AsyncFor)) and child is not node:
            seen.add("nested_loops")
            break


def _check_expensive_comp(node: ast.ListComp, seen: set[str]) -> None:
    """Flag list comprehensions with many function calls."""
    calls = sum(1 for n in ast.walk(node) if isinstance(n, ast.Call))
    if calls > _EXPENSIVE_CALL_THRESHOLD:
        seen.add("expensive_comprehension")


def _walk_skip_nested_defs(node: ast.AST) -> Iterator[ast.AST]:
    """Yield descendants of *node*, skipping nested function/class defs."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        yield child
        yield from _walk_skip_nested_defs(child)


class AstMetricsMixin(ScorerBase):
    """AST-derived metrics shared by the category scorers."""

    @staticmethod
    def _parse_ast_safe(code: str) -> ast.Module | None:
        """Parse code into an AST, returning None on SyntaxError."""
        try:
            return ast.parse(code)
        except SyntaxError:
            return None

    @staticmethod
    def _ast_complexity(code: str) -> float:
        """Fallback complexity from AST cyclomatic complexity.

        Computes per-function CC and uses the maximum, matching radon's
        approach.  Falls back to module-level CC when no functions exist.
        Returns 5.0 (neutral) when the code cannot be parsed.
        """
        tree = AstMetricsMixin._parse_ast_safe(code)
        if tree is None:
            return 5.0

        # Count CC per function and use the maximum (like radon).
        # Skip nested FunctionDef/AsyncFunctionDef/ClassDef so nested bodies
        # do not inflate the enclosing function's cyclomatic complexity.
        func_ccs: list[int] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                cc = 1
                for child in _walk_skip_nested_defs(node):
                    if isinstance(child, (ast.If, ast.For, ast.While, ast.ExceptHandler)):
                        cc += 1
                func_ccs.append(cc)

        if func_ccs:
            max_cc = max(func_ccs)
        else:
            # No functions: count module-level branches
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
        pts = sum(points for points, names in signals if any((root / n).exists() for n in names))
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
        """Heuristic test coverage based on test file existence / imports.

        Uses a graduated scoring approach:
          - 0: no tests found at all
          - 3: fuzzy match (test file name contains the module stem)
          - 4: a test file imports this module (filename mismatch)
          - 5: exact match (``test_{stem}.py`` or ``{stem}_test.py``)
          - 7: multiple test files reference this module
        """
        root = _find_project_root(file_path)
        if root is None:
            return 0.0
        if file_path.name.startswith("test_") or file_path.name.endswith("_test.py"):
            return 5.0
        exact_count, fuzzy_count = _count_test_files(root, file_path.stem)
        score = _test_count_to_score(exact_count, fuzzy_count)
        if score == 0.0 and _tests_import_module(root, file_path):
            return 4.0
        return score

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
        return AstMetricsMixin._check_project_signals(file_path, AstMetricsMixin._STRUCTURE_SIGNALS)

    @staticmethod
    def _devex_score(file_path: Path) -> float:
        """Score developer experience (0-10)."""
        root = _find_project_root(file_path)
        if root is None:
            return 5.0
        pts = sum(
            p
            for p, names in AstMetricsMixin._DEVEX_SIGNALS
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
        score, _seen = AstMetricsMixin._ast_performance_detailed(code)
        return score

    @staticmethod
    def _ast_performance_detailed(code: str) -> tuple[float, list[str]]:
        """AST-based performance scoring with issue details."""
        tree = AstMetricsMixin._parse_ast_safe(code)
        if tree is None:
            return 0.0, []
        seen: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _check_function_size(node, seen)
            if isinstance(node, (ast.For, ast.AsyncFor)):
                _check_nested_for(node, seen)
            if isinstance(node, ast.ListComp):
                _check_expensive_comp(node, seen)
        penalty = sum(PERFORMANCE_PENALTY_MAP.get(i, 0.5) for i in seen)
        return clamp_individual(10.0 - penalty), sorted(seen)

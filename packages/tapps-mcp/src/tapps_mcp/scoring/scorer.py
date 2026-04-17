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
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

import structlog

from tapps_core.config.settings import ScoringWeights, TappsMCPSettings

if TYPE_CHECKING:
    from tapps_mcp.tools.pip_audit import VulnerabilityFinding
    from tapps_mcp.tools.vulture import DeadCodeFinding
from tapps_mcp.scoring.constants import (
    DEEP_NESTING_THRESHOLD,
    HALSTEAD_HIGH_BUGS,
    HALSTEAD_HIGH_DIFFICULTY,
    HALSTEAD_HIGH_EFFORT,
    HALSTEAD_HIGH_VOLUME,
    HALSTEAD_VERY_HIGH_VOLUME,
    INSECURE_PATTERN_PENALTY,
    LARGE_FUNCTION_LINES,
    PERFLINT_PENALTY_CAP,
    PERFORMANCE_PENALTY_MAP,
    VERY_DEEP_NESTING_THRESHOLD,
    VERY_LARGE_FUNCTION_LINES,
    clamp_individual,
    clamp_overall,
)
from tapps_mcp.scoring.models import CategoryScore, ScoreResult
from tapps_mcp.scoring.scorer_base import STANDARD_CATEGORIES, ScorerBase
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


class CodeScorer(ScorerBase):
    """Score Python files across 7 quality categories.

    This is the concrete implementation of ``ScorerBase`` for Python files.
    It uses ruff for linting, mypy for type checking, bandit for security,
    and radon for complexity/maintainability analysis.
    """

    def __init__(
        self,
        settings: TappsMCPSettings | None = None,
        weights: ScoringWeights | None = None,
    ) -> None:
        super().__init__(settings, weights)

    # ------------------------------------------------------------------
    # ScorerBase abstract property implementations
    # ------------------------------------------------------------------

    @property
    def language(self) -> str:
        """Return 'python' as the language identifier."""
        return "python"

    @property
    def supported_categories(self) -> list[str]:
        """Return all 7 standard scoring categories."""
        return STANDARD_CATEGORIES.copy()

    @property
    def file_extensions(self) -> frozenset[str]:
        """Return Python file extensions."""
        return frozenset({".py", ".pyi"})

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

    def score_file_quick_enriched(self, file_path: Path) -> ScoreResult:
        """Quick-enriched mode: ruff + AST heuristics for all 7 categories.

        Runs ruff for linting, then supplements with AST-based heuristics
        for complexity, security, maintainability, test_coverage, performance,
        structure, and devex. No external tools beyond ruff are invoked.
        """
        resolved = file_path.resolve()
        issues = run_ruff_check(str(resolved), cwd=str(resolved.parent))
        lint_score = calculate_lint_score(issues)

        try:
            code = resolved.read_text(encoding="utf-8", errors="replace")
        except (OSError, PermissionError) as exc:
            logger.error("file_read_failed", path=str(resolved), error=str(exc))
            return self._error_result(str(resolved))

        w = self._weights
        cats: dict[str, CategoryScore] = {}

        # 1) Complexity (AST fallback)
        complexity_raw = self._ast_complexity(code)
        cats["complexity"] = CategoryScore(
            name="complexity",
            score=complexity_raw,
            weight=w.complexity,
            details={"fallback": True},
        )

        # 2) Security (heuristic)
        sec_score = self._heuristic_security(code)
        patterns_found = [p for p in _INSECURE_PATTERNS if p in code]
        cats["security"] = CategoryScore(
            name="security",
            score=sec_score,
            weight=w.security,
            details={"fallback": True, "patterns_found": patterns_found},
        )

        # 3) Maintainability (AST)
        maint_score = self._ast_maintainability(code)
        cats["maintainability"] = CategoryScore(
            name="maintainability",
            score=maint_score,
            weight=w.maintainability,
            details={"fallback": True, "line_count": len(code.splitlines())},
        )

        # 4) Test coverage (heuristic)
        coverage = self._coverage_heuristic(resolved)
        cats["test_coverage"] = CategoryScore(
            name="test_coverage",
            score=coverage,
            weight=w.test_coverage,
            details={"stem": resolved.stem},
        )

        # 5) Performance (AST)
        perf, perf_issues = self._ast_performance_detailed(code)
        cats["performance"] = CategoryScore(
            name="performance",
            score=perf,
            weight=w.performance,
            details={"issues_found": sorted(perf_issues)},
        )

        # 6) Structure
        structure = self._structure_score(resolved)
        cats["structure"] = CategoryScore(
            name="structure",
            score=structure,
            weight=w.structure,
        )

        # 7) DevEx
        devex = self._devex_score(resolved)
        cats["devex"] = CategoryScore(
            name="devex",
            score=devex,
            weight=w.devex,
        )

        # Bonus: linting (informational, weight=0)
        cats["linting"] = CategoryScore(
            name="linting",
            score=lint_score,
            weight=0.0,
            details={"issue_count": len(issues)},
        )

        overall = self._calculate_overall(cats)

        return ScoreResult(
            file_path=str(resolved),
            categories=cats,
            overall_score=overall,
            lint_issues=issues,
            degraded=True,
            missing_tools=["bandit", "radon", "mypy"],
        )

    async def score_file(self, file_path: Path, *, mode: str = "subprocess") -> ScoreResult:
        """Full mode: parallel ruff + mypy + bandit + radon → 7-category score.

        Args:
            file_path: Path to the Python file to score.
            mode: Execution mode for external tools - ``"subprocess"``,
                ``"direct"``, or ``"auto"``.
        """
        resolved = file_path.resolve()
        str_path = str(resolved)
        cwd = str(resolved.parent)
        timeout = self._settings.tool_timeout

        # Read code for AST-based analysis
        try:
            code = await asyncio.to_thread(resolved.read_text, encoding="utf-8", errors="replace")
        except (OSError, PermissionError) as exc:
            logger.error("file_read_failed", path=str_path, error=str(exc))
            return self._error_result(str_path)

        # Run external tools in parallel
        parallel = await run_all_tools(
            str_path,
            cwd=cwd,
            timeout=timeout,
            run_vulture=self._settings.dead_code_enabled,
            vulture_whitelist_patterns=self._settings.dead_code_whitelist_patterns,
            mode=mode,
        )

        # Build category scores
        categories, dep_vuln_count = self._build_categories(code, resolved, parallel)
        overall = self._calculate_overall(categories)

        return ScoreResult(
            file_path=str_path,
            categories=categories,
            overall_score=overall,
            lint_issues=parallel.lint_issues,
            type_issues=parallel.type_issues,
            security_issues=parallel.security_issues,
            dead_code_count=len(parallel.dead_code),
            dependency_vuln_count=dep_vuln_count,
            degraded=parallel.degraded,
            missing_tools=parallel.missing_tools,
            tool_errors=parallel.tool_errors,
        )

    # ------------------------------------------------------------------
    # Internal: category computation
    # ------------------------------------------------------------------

    def _build_categories(
        self,
        code: str,
        file_path: Path,
        parallel: ParallelResults,
    ) -> tuple[dict[str, CategoryScore], int]:
        """Build all category scores, returning (categories, dependency_vuln_count)."""
        cats: dict[str, CategoryScore] = {}

        cats["complexity"] = self._score_complexity_category(code, parallel)
        sec_cat, dep_vuln_count = self._score_security_category(code, parallel)
        cats["security"] = sec_cat
        maint_cat, dc_struct_penalty = self._score_maintainability_category(code, parallel)
        cats["maintainability"] = maint_cat
        cats["test_coverage"] = self._score_test_coverage_category(file_path)
        cats["performance"] = self._score_performance_category(code, parallel)
        cats["structure"] = self._score_structure_category(file_path, dc_struct_penalty)
        cats["devex"] = self._score_devex_category(file_path)
        self._add_informational_categories(cats, parallel)

        return cats, dep_vuln_count

    def _score_complexity_category(self, code: str, parallel: ParallelResults) -> CategoryScore:
        """Complexity category: radon CC or AST fallback (0-10)."""
        w = self._weights
        details: dict[str, object] = {"functions_analysed": len(parallel.radon_cc)}
        using_radon_cc = bool(parallel.radon_cc)
        if using_radon_cc:
            score = calculate_complexity_score(parallel.radon_cc)
            max_entry = max(parallel.radon_cc, key=lambda e: float(str(e.get("complexity", 0))))
            details["max_cc"] = float(str(max_entry.get("complexity", 0)))
            details["max_cc_function"] = str(max_entry.get("name", ""))
        else:
            score = self._ast_complexity(code)
            details["fallback"] = True
        return CategoryScore(
            name="complexity",
            score=score,
            weight=w.complexity,
            details=details,
            suggestions=_suggest_complexity(score, details, using_radon_cc),
        )

    def _score_security_category(
        self, code: str, parallel: ParallelResults
    ) -> tuple[CategoryScore, int]:
        """Security category: bandit + dependency vulnerabilities.

        Returns (CategoryScore, dependency_vuln_count).
        """
        w = self._weights
        details: dict[str, object] = {"issue_count": len(parallel.security_issues)}
        using_bandit = parallel.security_issues or "bandit" not in parallel.missing_tools
        if using_bandit:
            score = calculate_security_score(parallel.security_issues)
        else:
            score = self._heuristic_security(code)
            details["fallback"] = True
            details["patterns_found"] = [p for p in _INSECURE_PATTERNS if p in code]

        score, dep_findings = self._apply_dependency_penalty(score, details)

        suggestions = _suggest_security(score, details)
        if dep_findings:
            from tapps_mcp.scoring.dependency_security import suggest_dependency_fixes

            suggestions = suggest_dependency_fixes(dep_findings)[:5] + suggestions

        return CategoryScore(
            name="security",
            score=score,
            weight=w.security,
            details=details,
            suggestions=suggestions,
        ), len(dep_findings)

    def _apply_dependency_penalty(
        self, score: float, details: dict[str, object]
    ) -> tuple[float, list[VulnerabilityFinding]]:
        """Apply dependency vulnerability penalty if enabled.

        Returns (adjusted_score, findings_list).
        """
        if not self._settings.dependency_scan_enabled:
            return score, []

        from tapps_mcp.scoring.dependency_security import calculate_dependency_penalty
        from tapps_mcp.tools.dependency_scan_cache import get_dependency_findings

        dep_findings = get_dependency_findings(str(self._settings.project_root))
        if not dep_findings:
            return score, []

        penalty = calculate_dependency_penalty(dep_findings)
        score = clamp_individual(score - penalty / 10.0)
        details["dependency_vulnerabilities"] = len(dep_findings)
        sev_breakdown: dict[str, int] = {}
        for f in dep_findings:
            sev_breakdown[f.severity] = sev_breakdown.get(f.severity, 0) + 1
        details["dependency_severity_breakdown"] = sev_breakdown
        return score, dep_findings

    def _score_maintainability_category(
        self, code: str, parallel: ParallelResults
    ) -> tuple[CategoryScore, float]:
        """Maintainability category: radon MI + dead code penalty.

        Returns (CategoryScore, dead_code_struct_penalty).
        """
        w = self._weights
        details: dict[str, object] = {"mi_value": parallel.radon_mi}
        if "radon" not in parallel.missing_tools:
            score = calculate_maintainability_score(parallel.radon_mi)
        else:
            score = self._ast_maintainability(code)
            details["fallback"] = True
        details["has_docstring"] = '"""' in code or "'''" in code
        details["line_count"] = len(code.splitlines())

        dc_struct_penalty = 0.0
        extra_suggestions: list[str] = []
        if parallel.dead_code:
            score, dc_struct_penalty, extra_suggestions = self._apply_dead_code_penalty(
                score, details, parallel.dead_code
            )

        return CategoryScore(
            name="maintainability",
            score=score,
            weight=w.maintainability,
            details=details,
            suggestions=_suggest_maintainability(score, details) + extra_suggestions,
        ), dc_struct_penalty

    @staticmethod
    def _apply_dead_code_penalty(
        score: float,
        details: dict[str, object],
        dead_code: list[DeadCodeFinding],
    ) -> tuple[float, float, list[str]]:
        """Apply dead code penalties, returning (adjusted_score, struct_penalty, suggestions)."""
        from tapps_mcp.scoring.dead_code import (
            calculate_dead_code_penalty,
            suggest_dead_code_fixes,
        )

        dc_maint_penalty, dc_struct_penalty = calculate_dead_code_penalty(dead_code)
        adjusted = clamp_individual(score - dc_maint_penalty / 10.0)
        details["dead_code_count"] = len(dead_code)
        details["dead_code_penalty"] = round(dc_maint_penalty, 2)
        suggestions = suggest_dead_code_fixes(dead_code[:5])
        return adjusted, dc_struct_penalty, suggestions

    def _score_test_coverage_category(self, file_path: Path) -> CategoryScore:
        """Test coverage category: heuristic based on test file existence."""
        w = self._weights
        coverage = self._coverage_heuristic(file_path)
        details: dict[str, object] = {"stem": file_path.stem}
        details["is_test_file"] = file_path.name.startswith("test_") or file_path.name.endswith(
            "_test.py"
        )
        return CategoryScore(
            name="test_coverage",
            score=coverage,
            weight=w.test_coverage,
            details=details,
            suggestions=_suggest_test_coverage(coverage, details),
        )

    def _score_performance_category(
        self,
        code: str,
        parallel: ParallelResults,
    ) -> CategoryScore:
        """Performance category: AST heuristics + Halstead metrics + perflint."""
        w = self._weights

        # 1) AST heuristics (always available)
        ast_score, ast_issues = self._ast_performance_detailed(code)
        ast_penalty = 10.0 - ast_score

        # 2) Halstead metrics (when radon available)
        hal_issues = _halstead_issues(parallel.radon_hal)
        hal_penalty = sum(PERFORMANCE_PENALTY_MAP.get(i, 0.5) for i in hal_issues)

        # 3) Perflint findings (when pylint+perflint available)
        perf_issues = _perflint_issues(parallel.perflint)
        perf_penalty = min(
            sum(PERFORMANCE_PENALTY_MAP.get(i, 0.3) for i in perf_issues),
            PERFLINT_PENALTY_CAP,
        )

        combined_score = clamp_individual(10.0 - ast_penalty - hal_penalty - perf_penalty)
        all_issues = sorted(set(ast_issues) | set(hal_issues) | set(perf_issues))
        details: dict[str, object] = {
            "issues_found": all_issues,
            "ast_issues": sorted(ast_issues),
            "halstead_issues": sorted(hal_issues),
            "perflint_issues": sorted(perf_issues),
        }
        return CategoryScore(
            name="performance",
            score=combined_score,
            weight=w.performance,
            details=details,
            suggestions=_suggest_performance(combined_score, details),
        )

    def _score_structure_category(
        self, file_path: Path, dead_code_struct_penalty: float
    ) -> CategoryScore:
        """Structure category: project layout with optional dead code penalty."""
        w = self._weights
        structure = self._structure_score(file_path)
        if dead_code_struct_penalty > 0:
            structure = clamp_individual(structure - dead_code_struct_penalty / 10.0)
        return CategoryScore(
            name="structure",
            score=structure,
            weight=w.structure,
            suggestions=_suggest_structure(structure),
        )

    def _score_devex_category(self, file_path: Path) -> CategoryScore:
        """DevEx category: tooling and documentation signals."""
        w = self._weights
        devex = self._devex_score(file_path)
        return CategoryScore(
            name="devex",
            score=devex,
            weight=w.devex,
            suggestions=_suggest_devex(devex),
        )

    @staticmethod
    def _add_informational_categories(
        cats: dict[str, CategoryScore], parallel: ParallelResults
    ) -> None:
        """Add linting and type-checking as informational (zero-weight) categories."""
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
        """Fallback complexity from AST cyclomatic complexity.

        Computes per-function CC and uses the maximum, matching radon's
        approach.  Falls back to module-level CC when no functions exist.
        Returns 5.0 (neutral) when the code cannot be parsed.
        """
        tree = CodeScorer._parse_ast_safe(code)
        if tree is None:
            return 5.0

        # Count CC per function and use the maximum (like radon).
        func_ccs: list[int] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                cc = 1
                for child in ast.walk(node):
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
        """Heuristic test coverage based on test file existence.

        Uses a graduated scoring approach:
          - 0: no tests found at all
          - 3: fuzzy match (test file name contains the module stem)
          - 5: exact match (``test_{stem}.py`` or ``{stem}_test.py``)
          - 7: multiple test files reference this module
        """
        root = _find_project_root(file_path)
        if root is None:
            return 0.0
        if file_path.name.startswith("test_") or file_path.name.endswith("_test.py"):
            return 5.0
        exact_count, fuzzy_count = _count_test_files(root, file_path.stem)
        return _test_count_to_score(exact_count, fuzzy_count)

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
            p for p, names in CodeScorer._DEVEX_SIGNALS if any((root / n).exists() for n in names)
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
        score, _seen = CodeScorer._ast_performance_detailed(code)
        return score

    @staticmethod
    def _ast_performance_detailed(code: str) -> tuple[float, list[str]]:
        """AST-based performance scoring with issue details."""
        tree = CodeScorer._parse_ast_safe(code)
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


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

_EXPENSIVE_CALL_THRESHOLD = 5

from tapps_mcp.scoring.suggestions import (
    suggest_complexity as _suggest_complexity,
)
from tapps_mcp.scoring.suggestions import (
    suggest_devex as _suggest_devex,
)
from tapps_mcp.scoring.suggestions import (
    suggest_maintainability as _suggest_maintainability,
)
from tapps_mcp.scoring.suggestions import (
    suggest_performance as _suggest_performance,
)
from tapps_mcp.scoring.suggestions import (
    suggest_security as _suggest_security,
)
from tapps_mcp.scoring.suggestions import (
    suggest_structure as _suggest_structure,
)
from tapps_mcp.scoring.suggestions import (
    suggest_test_coverage as _suggest_test_coverage,
)

_SCORE_LOW = 5


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
    value: int | float,
    moderate_threshold: int | float,
    severe_threshold: int | float,
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
    """Flag nested for-loops (sync or async)."""
    for child in ast.walk(node):
        if isinstance(child, (ast.For, ast.AsyncFor)) and child is not node:
            seen.add("nested_loops")
            break


def _check_expensive_comp(node: ast.ListComp, seen: set[str]) -> None:
    """Flag list comprehensions with many function calls."""
    calls = sum(1 for n in ast.walk(node) if isinstance(n, ast.Call))
    if calls > _EXPENSIVE_CALL_THRESHOLD:
        seen.add("expensive_comprehension")


def _count_test_files(root: Path, stem: str) -> tuple[int, int]:
    """Count exact and fuzzy test file matches for a module stem.

    Returns (exact_count, fuzzy_count).
    """
    test_dirs = ["tests", "test", "tests/unit", "tests/integration"]
    exact_patterns = [f"test_{stem}.py", f"{stem}_test.py"]
    exact_count = 0
    fuzzy_count = 0
    for td in test_dirs:
        td_path = root / td
        if not td_path.is_dir():
            continue
        for pat in exact_patterns:
            if (td_path / pat).exists():
                exact_count += 1
        for match in td_path.glob(f"test_*{stem}*.py"):
            if match.name not in exact_patterns:
                fuzzy_count += 1
    return exact_count, fuzzy_count


def _test_count_to_score(exact_count: int, fuzzy_count: int) -> float:
    """Convert test file counts to a coverage heuristic score."""
    total = exact_count + fuzzy_count
    multi_test_threshold = 2
    if total >= multi_test_threshold:
        return 7.0
    if exact_count >= 1:
        return 5.0
    if fuzzy_count >= 1:
        return 3.0
    return 0.0


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

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
            code = resolved.read_text(encoding="utf-8", errors="replace")
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
        categories = self._build_categories(code, resolved, parallel)
        overall = self._calculate_overall(categories)

        return ScoreResult(
            file_path=str_path,
            categories=categories,
            overall_score=overall,
            lint_issues=parallel.lint_issues,
            type_issues=parallel.type_issues,
            security_issues=parallel.security_issues,
            dead_code_count=len(parallel.dead_code),
            dependency_vuln_count=self._dependency_vuln_count,
            degraded=parallel.degraded,
            missing_tools=parallel.missing_tools,
            tool_errors=parallel.tool_errors,
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
        self._dependency_vuln_count = 0

        # 1) Complexity (radon cc -> 0-10, lower complexity = higher quality)
        cplx_details: dict[str, object] = {"functions_analysed": len(parallel.radon_cc)}
        using_radon_cc = bool(parallel.radon_cc)
        if using_radon_cc:
            complexity_raw = calculate_complexity_score(parallel.radon_cc)
            max_entry = max(parallel.radon_cc, key=lambda e: float(str(e.get("complexity", 0))))
            cplx_details["max_cc"] = float(str(max_entry.get("complexity", 0)))
            cplx_details["max_cc_function"] = str(max_entry.get("name", ""))
        else:
            complexity_raw = self._ast_complexity(code)
            cplx_details["fallback"] = True
        cats["complexity"] = CategoryScore(
            name="complexity",
            score=complexity_raw,
            weight=w.complexity,
            details=cplx_details,
            suggestions=_suggest_complexity(complexity_raw, cplx_details, using_radon_cc),
        )

        # 2) Security (bandit -> 0-10, plus dependency vulnerability penalty)
        sec_details: dict[str, object] = {"issue_count": len(parallel.security_issues)}
        using_bandit = parallel.security_issues or "bandit" not in parallel.missing_tools
        if using_bandit:
            sec_score = calculate_security_score(parallel.security_issues)
        else:
            sec_score = self._heuristic_security(code)
            sec_details["fallback"] = True
            sec_details["patterns_found"] = [p for p in _INSECURE_PATTERNS if p in code]

        # Apply dependency vulnerability penalty (from cached pip-audit results)
        dep_findings: list = []
        if self._settings.dependency_scan_enabled:
            from tapps_mcp.scoring.dependency_security import (
                calculate_dependency_penalty,
                suggest_dependency_fixes,
            )
            from tapps_mcp.tools.dependency_scan_cache import get_dependency_findings

            dep_findings = get_dependency_findings(str(self._settings.project_root))
            if dep_findings:
                penalty = calculate_dependency_penalty(dep_findings)
                sec_score = clamp_individual(sec_score - penalty / 10.0)
                sec_details["dependency_vulnerabilities"] = len(dep_findings)
                sev_breakdown: dict[str, int] = {}
                for f in dep_findings:
                    sev_breakdown[f.severity] = sev_breakdown.get(f.severity, 0) + 1
                sec_details["dependency_severity_breakdown"] = sev_breakdown

        sec_suggestions = _suggest_security(sec_score, sec_details)
        if dep_findings:
            sec_suggestions = suggest_dependency_fixes(dep_findings)[:5] + sec_suggestions

        cats["security"] = CategoryScore(
            name="security",
            score=sec_score,
            weight=w.security,
            details=sec_details,
            suggestions=sec_suggestions,
        )

        # Store for ScoreResult.dependency_vuln_count
        self._dependency_vuln_count = len(dep_findings)

        # 3) Maintainability (radon mi -> 0-10, with dead code penalty)
        maint_details: dict[str, object] = {"mi_value": parallel.radon_mi}
        if "radon" not in parallel.missing_tools:
            maint_score = calculate_maintainability_score(parallel.radon_mi)
        else:
            maint_score = self._ast_maintainability(code)
            maint_details["fallback"] = True
        has_docstring = '"""' in code or "'''" in code
        maint_details["has_docstring"] = has_docstring
        maint_details["line_count"] = len(code.splitlines())

        # Dead code penalty (from vulture findings)
        maint_suggestions: list[str] = []
        if parallel.dead_code:
            from tapps_mcp.scoring.dead_code import (
                calculate_dead_code_penalty,
                suggest_dead_code_fixes,
            )

            dc_maint_penalty, dc_struct_penalty = calculate_dead_code_penalty(parallel.dead_code)
            maint_score = clamp_individual(maint_score - dc_maint_penalty / 10.0)
            maint_details["dead_code_count"] = len(parallel.dead_code)
            maint_details["dead_code_penalty"] = round(dc_maint_penalty, 2)
            maint_suggestions = suggest_dead_code_fixes(parallel.dead_code[:5])
            # Store structure penalty for later use
            self._dead_code_struct_penalty = dc_struct_penalty
        else:
            self._dead_code_struct_penalty = 0.0

        cats["maintainability"] = CategoryScore(
            name="maintainability",
            score=maint_score,
            weight=w.maintainability,
            details=maint_details,
            suggestions=_suggest_maintainability(maint_score, maint_details) + maint_suggestions,
        )

        # 4) Test coverage (heuristic)
        coverage = self._coverage_heuristic(file_path)
        cov_details: dict[str, object] = {"stem": file_path.stem}
        is_test = file_path.name.startswith("test_") or file_path.name.endswith("_test.py")
        cov_details["is_test_file"] = is_test
        cats["test_coverage"] = CategoryScore(
            name="test_coverage",
            score=coverage,
            weight=w.test_coverage,
            details=cov_details,
            suggestions=_suggest_test_coverage(coverage, cov_details),
        )

        # 5) Performance (AST-based)
        perf, perf_issues = self._ast_performance_detailed(code)
        perf_details: dict[str, object] = {"issues_found": sorted(perf_issues)}
        cats["performance"] = CategoryScore(
            name="performance",
            score=perf,
            weight=w.performance,
            details=perf_details,
            suggestions=_suggest_performance(perf, perf_details),
        )

        # 6) Structure (project layout, with dead code penalty)
        structure = self._structure_score(file_path)
        if self._dead_code_struct_penalty > 0:
            structure = clamp_individual(structure - self._dead_code_struct_penalty / 10.0)
        cats["structure"] = CategoryScore(
            name="structure",
            score=structure,
            weight=w.structure,
            suggestions=_suggest_structure(structure),
        )

        # 7) DevEx (tooling / docs)
        devex = self._devex_score(file_path)
        cats["devex"] = CategoryScore(
            name="devex",
            score=devex,
            weight=w.devex,
            suggestions=_suggest_devex(devex),
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
        # If the file itself is a test file
        if file_path.name.startswith("test_") or file_path.name.endswith("_test.py"):
            return 5.0
        stem = file_path.stem
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
            # Fuzzy: test_*{stem}*.py (e.g. test_server_tools.py for server.py)
            for match in td_path.glob(f"test_*{stem}*.py"):
                if match.name not in exact_patterns:
                    fuzzy_count += 1
        total = exact_count + fuzzy_count
        multi_test_threshold = 2
        if total >= multi_test_threshold:
            return 7.0
        if exact_count >= 1:
            return 5.0
        if fuzzy_count >= 1:
            return 3.0
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
            if isinstance(node, ast.FunctionDef):
                _check_function_size(node, seen)
            if isinstance(node, ast.For):
                _check_nested_for(node, seen)
            if isinstance(node, ast.ListComp):
                _check_expensive_comp(node, seen)
        penalty = sum(PERFORMANCE_PENALTY_MAP.get(i, 0.5) for i in seen)
        return clamp_individual(10.0 - penalty), sorted(seen)

    def _error_result(self, path: str) -> ScoreResult:
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

# Suggestion thresholds
_CC_HIGH = 10
_CC_MODERATE = 5
_MI_VERY_LOW = 20
_MI_LOW = 40
_FILE_LONG_LINES = 300
_SCORE_LOW = 5


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


# ------------------------------------------------------------------
# Suggestion generators (one per scored category)
# ------------------------------------------------------------------


def _suggest_complexity(
    score: float,
    details: dict[str, object],
    using_radon: bool,
) -> list[str]:
    """Actionable suggestions for the complexity category."""
    tips: list[str] = []
    if not using_radon:
        tips.append("Install radon for accurate complexity measurement (pip install radon).")
        return tips
    if not isinstance(details, dict):
        return tips
    max_cc = float(str(details.get("max_cc", 0)))
    func_name = str(details.get("max_cc_function", ""))
    if max_cc > _CC_HIGH:
        tips.append(
            f"Function '{func_name}' has CC={int(max_cc)}. "
            f"Extract branches into helper functions to reduce below {_CC_HIGH}."
        )
    elif max_cc > _CC_MODERATE:
        tips.append(
            f"Function '{func_name}' has CC={int(max_cc)}. Consider simplifying conditional logic."
        )
    return tips


def _suggest_security(
    score: float,
    details: dict[str, object],
) -> list[str]:
    """Actionable suggestions for the security category."""
    tips: list[str] = []
    if not isinstance(details, dict):
        return tips
    issue_count = int(str(details.get("issue_count", 0)))
    if issue_count > 0:
        tips.append(f"Found {issue_count} security issue(s). Run tapps_security_scan for details.")
    patterns = details.get("patterns_found")
    if isinstance(patterns, list) and patterns:
        joined = ", ".join(str(p) for p in patterns)
        tips.append(f"Avoid insecure patterns: {joined} - use safer alternatives.")
    return tips


def _suggest_maintainability(
    score: float,
    details: dict[str, object],
) -> list[str]:
    """Actionable suggestions for the maintainability category."""
    tips: list[str] = []
    if not isinstance(details, dict):
        return tips
    mi = float(str(details.get("mi_value", 100)))
    if mi < _MI_VERY_LOW:
        tips.append(f"MI={mi:.0f} (very low). Split this file into smaller modules.")
    elif mi < _MI_LOW:
        tips.append(f"MI={mi:.0f} (low). Add docstrings and reduce function sizes.")
    if not details.get("has_docstring"):
        tips.append("Add module and function docstrings to improve maintainability.")
    line_count = int(str(details.get("line_count", 0)))
    if line_count > _FILE_LONG_LINES:
        tips.append(f"File has {line_count} lines. Consider splitting into smaller modules.")
    return tips


def _suggest_test_coverage(
    score: float,
    details: dict[str, object],
) -> list[str]:
    """Actionable suggestions for the test_coverage category."""
    tips: list[str] = []
    if not isinstance(details, dict):
        return tips
    stem = str(details.get("stem", "module"))
    is_test = bool(details.get("is_test_file"))
    if score == 0:
        tips.append(f"No test file found. Create tests/unit/test_{stem}.py.")
    elif is_test and score <= _SCORE_LOW:
        tips.append("This is a test file (coverage score capped at 5/10).")
    return tips


def _suggest_performance(
    score: float,
    details: dict[str, object],
) -> list[str]:
    """Actionable suggestions for the performance category."""
    tips: list[str] = []
    if not isinstance(details, dict):
        return tips
    issues = details.get("issues_found")
    if not isinstance(issues, list) or not issues:
        return tips
    for issue in issues:
        issue_str = str(issue)
        if issue_str == "very_large_function":
            tips.append(
                f"Function exceeds {VERY_LARGE_FUNCTION_LINES} lines. "
                "Decompose into smaller functions."
            )
        elif issue_str == "large_function":
            tips.append(f"Function exceeds {LARGE_FUNCTION_LINES} lines. Consider breaking it up.")
        elif issue_str == "very_deep_nesting":
            tips.append(
                f"Nesting depth > {VERY_DEEP_NESTING_THRESHOLD}. "
                "Extract inner logic into helpers or use early returns."
            )
        elif issue_str == "deep_nesting":
            tips.append(
                f"Nesting depth > {DEEP_NESTING_THRESHOLD}. Extract inner logic into helpers."
            )
        elif issue_str == "nested_loops":
            tips.append(
                "Nested for-loops detected. Consider alternative data structures or itertools."
            )
        elif issue_str == "expensive_comprehension":
            tips.append(
                "List comprehension with many function calls. Consider a plain loop for clarity."
            )
    return tips


def _suggest_structure(score: float) -> list[str]:
    """Actionable suggestions for the structure category."""
    tips: list[str] = []
    if score < _SCORE_LOW:
        tips.append("Add pyproject.toml and a tests/ directory for better project structure.")
    return tips


def _suggest_devex(score: float) -> list[str]:
    """Actionable suggestions for the devex category."""
    tips: list[str] = []
    if score < _SCORE_LOW:
        tips.append("Add CLAUDE.md or AGENTS.md for AI-assisted development guidance.")
    return tips

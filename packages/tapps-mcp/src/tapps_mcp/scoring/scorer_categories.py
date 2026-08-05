"""Per-category scorers for the Python code scorer.

The seven scoring categories — complexity, security, maintainability,
test coverage, performance, structure, devex — plus the penalty helpers
and the pure AST/metric functions they call. Split out of ``scorer.py``
under TAP-5628, which had the whole thing in one 1,100-line file scoring
38.4 against a threshold of 70.

``CodeScorer`` mixes this in, so every ``self._x()`` call site resolves
through the MRO exactly as before.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import structlog

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

if TYPE_CHECKING:
    from tapps_mcp.tools.pip_audit import VulnerabilityFinding
    from tapps_mcp.tools.vulture import DeadCodeFinding
from tapps_mcp.scoring.ast_metrics import (
    _INSECURE_PATTERNS,
    AstMetricsMixin,
    _halstead_issues,
    _perflint_issues,
)
from tapps_mcp.scoring.constants import (
    PERFLINT_PENALTY_CAP,
    PERFORMANCE_PENALTY_MAP,
    clamp_individual,
)
from tapps_mcp.scoring.models import CategoryScore
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
from tapps_mcp.tools.bandit import calculate_security_score
from tapps_mcp.tools.mypy import calculate_type_score
from tapps_mcp.tools.parallel import ParallelResults
from tapps_mcp.tools.radon import (
    calculate_complexity_score,
    calculate_maintainability_score,
)
from tapps_mcp.tools.ruff import calculate_lint_score

logger = structlog.get_logger(__name__)


class CategoryScorersMixin(AstMetricsMixin):
    """The seven scoring categories and the metrics behind them."""

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
            suggestions=_suggest_complexity(details, using_radon_cc),
        )

    def _score_security_category(
        self, code: str, parallel: ParallelResults
    ) -> tuple[CategoryScore, int]:
        """Security category: bandit + dependency vulnerabilities.

        Returns (CategoryScore, dependency_vuln_count).
        """
        w = self._weights
        details: dict[str, object] = {"issue_count": len(parallel.security_issues)}
        # Provenance breakdown so semgrep findings are visible next to bandit's.
        if parallel.semgrep_issues:
            details["semgrep_issue_count"] = sum(
                1 for i in parallel.security_issues if i.source == "semgrep"
            )
        if "semgrep" in parallel.skipped_tools:
            details["semgrep_skipped"] = True
        # Use the real bandit result unless: (a) bandit is missing/unavailable, or
        # (b) bandit ran but its output was empty/unparseable (parse failure).
        bandit_parse_failed = "bandit" in parallel.tool_parse_failures
        using_bandit = not bandit_parse_failed and (
            parallel.security_issues or "bandit" not in parallel.missing_tools
        )
        if using_bandit:
            score = calculate_security_score(parallel.security_issues)
        else:
            score = self._heuristic_security(code)
            details["fallback"] = True
            details["patterns_found"] = [p for p in _INSECURE_PATTERNS if p in code]

        score, dep_findings = self._apply_dependency_penalty(score, details)

        suggestions = _suggest_security(details)
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
            suggestions=_suggest_maintainability(details) + extra_suggestions,
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
        if self._is_narrative_path(file_path):
            return CategoryScore(
                name="test_coverage",
                score=10.0,
                weight=0.0,
                details={"narrative_path": True, "stem": file_path.stem},
                suggestions=[],
            )
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
            suggestions=_suggest_performance(details),
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

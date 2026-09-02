"""Main scoring engine — 7-category code quality scoring.

Scores Python files across seven categories:
  complexity, security, maintainability, test_coverage,
  performance, structure, devex

Each category produces a 0-10 score.  The overall score (0-100) is the
weighted sum ``Σ(category_score * weight) * 10``, with ``complexity``
inverted (10 - score) because lower complexity is better.
"""

from __future__ import annotations

import asyncio
import math
from pathlib import Path

import structlog

from tapps_core.config.settings import ScoringWeights, TappsMCPSettings
from tapps_mcp.scoring.ast_metrics import (
    _EXPENSIVE_CALL_THRESHOLD as _EXPENSIVE_CALL_THRESHOLD,
)
from tapps_mcp.scoring.ast_metrics import (
    _INSECURE_PATTERNS as _INSECURE_PATTERNS,
)
from tapps_mcp.scoring.ast_metrics import (
    _halstead_issues as _halstead_issues,
)
from tapps_mcp.scoring.ast_metrics import (
    _max_nesting_depth as _max_nesting_depth,
)
from tapps_mcp.scoring.ast_metrics import (
    _perflint_issues as _perflint_issues,
)
from tapps_mcp.scoring.ast_metrics import (
    _walk_skip_nested_defs as _walk_skip_nested_defs,
)
from tapps_mcp.scoring.constants import (
    PERFORMANCE_PENALTY_MAP,
    clamp_individual,
    clamp_overall,
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
from tapps_mcp.scoring.models import CategoryScore, ScoreResult
from tapps_mcp.scoring.scorer_base import STANDARD_CATEGORIES
from tapps_mcp.scoring.scorer_categories import (
    CategoryScorersMixin,
)
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
from tapps_mcp.tools.parallel import ParallelResults, run_all_tools
from tapps_mcp.tools.radon import (
    _is_radon_importable,
    _radon_cc_direct,
    _radon_hal_direct,
    _radon_mi_direct,
    calculate_complexity_score,
    calculate_maintainability_score,
)
from tapps_mcp.tools.ruff import calculate_lint_score, run_ruff_check

logger = structlog.get_logger(__name__)

# TAP-5628: the category scorers and their helpers moved to
# `scorer_categories`, and the coverage heuristic to `coverage_heuristic`.
# These names stay importable from `tapps_mcp.scoring.scorer` — existing
# callers and tests import them from here.
__all__ = [
    "_EXPENSIVE_CALL_THRESHOLD",
    "_INSECURE_PATTERNS",
    "CodeScorer",
    "_count_test_files",
    "_find_project_root",
    "_halstead_issues",
    "_max_nesting_depth",
    "_perflint_issues",
    "_suggest_complexity",
    "_suggest_devex",
    "_suggest_maintainability",
    "_suggest_performance",
    "_suggest_security",
    "_suggest_structure",
    "_suggest_test_coverage",
    "_test_roots",
    "_walk_skip_nested_defs",
    "_workspace_members",
]


class CodeScorer(CategoryScorersMixin):
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

    def score_file_quick(
        self, file_path: Path, *, identity_path: Path | None = None
    ) -> ScoreResult:
        """Quick mode: ruff-only scoring (< 500 ms target)."""
        resolved = file_path.resolve()
        identity = self._identity_of(file_path, identity_path)
        issues = run_ruff_check(str(resolved), cwd=str(resolved.parent))
        ruff_failed = issues is None
        if issues is None:
            issues = []
        lint_score = calculate_lint_score(issues)

        categories = {
            "linting": CategoryScore(
                name="linting",
                score=lint_score,
                weight=1.0,
                details={"issue_count": len(issues), "fallback": ruff_failed},
            ),
        }

        return ScoreResult(
            file_path=str(identity),
            categories=categories,
            overall_score=clamp_overall(lint_score * 10.0),
            lint_issues=issues,
            degraded=ruff_failed,
            missing_tools=["ruff"] if ruff_failed else [],
        )

    def score_file_quick_enriched(
        self, file_path: Path, *, identity_path: Path | None = None
    ) -> ScoreResult:
        """Quick-enriched mode: ruff + real tool data (when available) for all 7 categories.

        Runs ruff for linting, then uses radon in-process (``_radon_cc_direct``,
        ``_radon_mi_direct``) for complexity and maintainability when the radon
        library is installed — falling back to AST heuristics only when it is not.
        Security uses a heuristic placeholder; the caller (``_quick_check_single``)
        merges real bandit data via ``_merge_bandit_into_score_result`` after the
        parallel security scan completes.

        This keeps the method synchronous (no subprocess latency for radon) while
        producing scores that agree with ``score_file``'s formula when tools are
        present.
        """
        resolved = file_path.resolve()
        identity = self._identity_of(file_path, identity_path)
        str_path = str(resolved)
        cwd = str(resolved.parent)
        missing: list[str] = []
        issues = run_ruff_check(str_path, cwd=cwd)
        if issues is None:
            missing.append("ruff")
            issues = []
        lint_score = calculate_lint_score(issues)

        try:
            code = resolved.read_text(encoding="utf-8", errors="replace")
        except (OSError, PermissionError):
            logger.exception("file_read_failed", path=str_path)
            return self._error_result(str(identity))

        w = self._weights
        cats: dict[str, CategoryScore] = {}

        # 1) Complexity — radon CC direct (in-process, ~1ms) or AST fallback
        radon_cc = _radon_cc_direct(str_path)
        if radon_cc:
            complexity_raw = calculate_complexity_score(radon_cc)
            max_entry = max(radon_cc, key=lambda e: float(str(e.get("complexity", 0))))
            complexity_details: dict[str, object] = {
                "functions_analysed": len(radon_cc),
                "max_cc": float(str(max_entry.get("complexity", 0))),
                "max_cc_function": str(max_entry.get("name", "")),
            }
        else:
            complexity_raw = self._ast_complexity(code)
            complexity_details = {"fallback": True}
            if not _is_radon_importable():
                missing.append("radon")
        cats["complexity"] = CategoryScore(
            name="complexity",
            score=complexity_raw,
            weight=w.complexity,
            details=complexity_details,
        )

        # 2) Security — heuristic placeholder; real bandit data merged by caller
        # after the parallel run_security_scan completes in _quick_check_single.
        sec_score = self._heuristic_security(code)
        patterns_found = [p for p in _INSECURE_PATTERNS if p in code]
        cats["security"] = CategoryScore(
            name="security",
            score=sec_score,
            weight=w.security,
            details={"fallback": True, "patterns_found": patterns_found},
        )
        missing.append("bandit")

        # 3) Maintainability — radon MI direct (in-process, ~1ms) or AST fallback
        nan_inf_coerced = False
        if _is_radon_importable():
            radon_mi = _radon_mi_direct(str_path)
            if math.isnan(radon_mi) or math.isinf(radon_mi):
                nan_inf_coerced = True
            maint_score = calculate_maintainability_score(radon_mi)
            maint_details: dict[str, object] = {
                "mi_value": radon_mi,
                "line_count": len(code.splitlines()),
                "has_docstring": '"""' in code or "'''" in code,
            }
        else:
            maint_score = self._ast_maintainability(code)
            maint_details = {"fallback": True, "line_count": len(code.splitlines())}
            if "radon" not in missing:
                missing.append("radon")
        cats["maintainability"] = CategoryScore(
            name="maintainability",
            score=maint_score,
            weight=w.maintainability,
            details=maint_details,
        )

        # 4) Test coverage (heuristic — no external tool). Path-derived, so it
        # asks about `identity`, not about wherever the bytes were read from.
        coverage = self._coverage_heuristic(identity)
        cats["test_coverage"] = CategoryScore(
            name="test_coverage",
            score=coverage,
            weight=w.test_coverage,
            details={"stem": identity.stem},
        )

        # 5) Performance (AST heuristics + Halstead via radon_hal_direct when available)
        # Matches score_file formula: AST penalty + Halstead penalty; no perflint (subprocess)
        perf_ast, perf_ast_issues = self._ast_performance_detailed(code)
        ast_penalty = 10.0 - perf_ast
        radon_hal = _radon_hal_direct(str_path) if _is_radon_importable() else []
        hal_issues = _halstead_issues(radon_hal)
        hal_penalty = sum(PERFORMANCE_PENALTY_MAP.get(i, 0.5) for i in hal_issues)
        perf = clamp_individual(10.0 - ast_penalty - hal_penalty)
        perf_all_issues = sorted(set(perf_ast_issues) | set(hal_issues))
        cats["performance"] = CategoryScore(
            name="performance",
            score=perf,
            weight=w.performance,
            details={"issues_found": perf_all_issues},
        )

        # 6) Structure (path-derived)
        structure = self._structure_score(identity)
        cats["structure"] = CategoryScore(
            name="structure",
            score=structure,
            weight=w.structure,
        )

        # 7) DevEx (path-derived)
        devex = self._devex_score(identity)
        cats["devex"] = CategoryScore(
            name="devex",
            score=devex,
            weight=w.devex,
        )

        # Linting (informational, weight=0)
        cats["linting"] = CategoryScore(
            name="linting",
            score=lint_score,
            weight=0.0,
            details={"issue_count": len(issues)},
        )

        overall = self._calculate_overall(cats)

        # Derive degraded_categories from any non-informational category with fallback=True.
        degraded_cats = [
            name
            for name, cat in cats.items()
            if cat.details.get("fallback") is True and name != "linting"
        ]

        return ScoreResult(
            file_path=str(identity),
            categories=cats,
            overall_score=overall,
            lint_issues=issues,
            degraded=bool(missing or degraded_cats or nan_inf_coerced),
            missing_tools=missing,
            degraded_categories=degraded_cats,
        )

    async def score_file(
        self,
        file_path: Path,
        *,
        mode: str = "subprocess",
        identity_path: Path | None = None,
    ) -> ScoreResult:
        """Full mode: parallel ruff + mypy + bandit + radon → 7-category score.

        Args:
            file_path: Path the Python source is read from.
            mode: Execution mode for external tools - ``"subprocess"``,
                ``"direct"``, or ``"auto"``.
            identity_path: Path the content is judged *as* for the
                path-derived categories. Defaults to ``file_path``; see
                ``ScorerBase._identity_of``.
        """
        resolved = await asyncio.to_thread(file_path.resolve)
        identity = await asyncio.to_thread(self._identity_of, file_path, identity_path)
        str_path = str(resolved)
        cwd = str(resolved.parent)
        timeout = self._settings.tool_timeout

        # Read code for AST-based analysis
        try:
            code = await asyncio.to_thread(resolved.read_text, encoding="utf-8", errors="replace")
        except (OSError, PermissionError):
            logger.exception("file_read_failed", path=str_path)
            return self._error_result(str(identity))

        # Run external tools in parallel
        parallel = await run_all_tools(
            str_path,
            cwd=cwd,
            timeout=timeout,
            run_vulture=self._settings.dead_code_enabled,
            run_semgrep=self._settings.semgrep_enabled,
            vulture_whitelist_patterns=self._settings.dead_code_whitelist_patterns,
            vulture_min_confidence=self._settings.dead_code_min_confidence,
            mode=mode,
        )

        # Category AST/heuristic work is sync — offload so shared HTTP fleet
        # (nlt-build) can still answer Cursor initialize/tools/list.
        from tapps_mcp.tools.event_loop_guard import heavy_cpu

        async with heavy_cpu():
            categories, dep_vuln_count = await asyncio.to_thread(
                self._build_categories, code, identity, parallel
            )
        overall = self._calculate_overall(categories)

        # Derive degraded_categories: any non-informational category that fell back
        # to an AST heuristic because a tool ran but produced empty/unparseable output.
        degraded_cats = [
            name
            for name, cat in categories.items()
            if cat.details.get("fallback") is True and name != "linting"
        ]

        return ScoreResult(
            file_path=str(identity),
            categories=categories,
            overall_score=overall,
            lint_issues=parallel.lint_issues,
            type_issues=parallel.type_issues,
            security_issues=parallel.security_issues,
            dead_code_count=len(parallel.dead_code),
            dependency_vuln_count=dep_vuln_count,
            degraded=parallel.degraded or bool(degraded_cats),
            missing_tools=parallel.missing_tools,
            skipped_tools=parallel.skipped_tools,
            tool_errors=parallel.tool_errors,
            degraded_categories=degraded_cats,
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
        """Build all category scores, returning (categories, dependency_vuln_count).

        *file_path* is the file's **identity** path — the three categories
        below that take it (``test_coverage``, ``structure``, ``devex``)
        derive their verdict from the path, not from *code*.
        """
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

    # ------------------------------------------------------------------
    # Fallback heuristics (when external tools are unavailable)
    # ------------------------------------------------------------------


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


_SCORE_LOW = 5

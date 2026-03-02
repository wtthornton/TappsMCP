"""Quality gate evaluator.

Compares scoring results against configurable thresholds (presets)
and returns a pass / fail decision.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from tapps_core.config.settings import PRESETS, ScoringWeights
from tapps_mcp.gates.models import GateFailure, GateResult, GateThresholds
from tapps_mcp.scoring.constants import INDIVIDUAL_MAX

# Category weights for failure priority ordering (from ScoringWeights defaults)
_DEFAULT_WEIGHTS = ScoringWeights()
_CATEGORY_WEIGHTS: dict[str, float] = {
    "security": _DEFAULT_WEIGHTS.security,
    "maintainability": _DEFAULT_WEIGHTS.maintainability,
    "complexity": _DEFAULT_WEIGHTS.complexity,
    "test_coverage": _DEFAULT_WEIGHTS.test_coverage,
    "performance": _DEFAULT_WEIGHTS.performance,
    "structure": _DEFAULT_WEIGHTS.structure,
    "devex": _DEFAULT_WEIGHTS.devex,
    "overall": 1.0,  # overall failures always sort first
}

# Security floor: if the security category score (0-100 equivalent) is below
# this absolute threshold, the gate MUST fail regardless of overall score.
_SECURITY_FLOOR: float = 50.0
_SECURITY_FLOOR_INDIVIDUAL: float = _SECURITY_FLOOR / 10.0  # 5.0 on 0-10 scale

if TYPE_CHECKING:
    from tapps_mcp.scoring.models import ScoreResult

logger = structlog.get_logger(__name__)


def thresholds_for_preset(preset: str) -> GateThresholds:
    """Build ``GateThresholds`` from a named preset.

    Falls back to ``"standard"`` if *preset* is unknown.
    """
    data = PRESETS.get(preset, PRESETS["standard"])
    if not isinstance(data, dict):
        data = PRESETS["standard"]
    return GateThresholds(**data)


def _fail(
    failures: list[GateFailure],
    category: str,
    actual: float,
    threshold: float,
    msg: str,
) -> None:
    failures.append(
        GateFailure(
            category=category,
            actual=actual,
            threshold=threshold,
            message=msg,
            weight=_CATEGORY_WEIGHTS.get(category, 0.0),
        )
    )


def evaluate_gate(
    score_result: ScoreResult,
    preset: str = "standard",
    thresholds: GateThresholds | None = None,
) -> GateResult:
    """Evaluate a ``ScoreResult`` against quality gate thresholds.

    Args:
        score_result: The scoring output to evaluate.
        preset: Named preset (``"standard"``, ``"strict"``, ``"framework"``).
        thresholds: Explicit thresholds; if provided, *preset* is ignored.

    Returns:
        ``GateResult`` with pass/fail and failure details.
    """
    if thresholds is None:
        thresholds = thresholds_for_preset(preset)

    failures: list[GateFailure] = []
    warnings: list[str] = []
    scores: dict[str, float] = {}

    cats = score_result.categories
    for name, cat in cats.items():
        scores[name] = cat.score

    overall = score_result.overall_score
    scores["overall"] = overall

    # 1) Overall score
    if overall < thresholds.overall_min:
        _fail(
            failures,
            "overall",
            overall,
            thresholds.overall_min,
            f"Overall {overall:.1f} < {thresholds.overall_min:.1f}",
        )

    # 2) Security
    sec = cats.get("security")
    if sec and thresholds.security_min > 0 and sec.score < thresholds.security_min:
        _fail(
            failures,
            "security",
            sec.score,
            thresholds.security_min,
            f"Security {sec.score:.1f} < {thresholds.security_min:.1f}",
        )

    # 3) Maintainability
    maint = cats.get("maintainability")
    if (
        maint
        and thresholds.maintainability_min > 0
        and maint.score < thresholds.maintainability_min
    ):
        _fail(
            failures,
            "maintainability",
            maint.score,
            thresholds.maintainability_min,
            f"Maintainability {maint.score:.1f} < {thresholds.maintainability_min:.1f}",
        )

    # 4) Complexity (lower is better - fail if score > max)
    comp = cats.get("complexity")
    if (
        comp
        and thresholds.complexity_max < INDIVIDUAL_MAX
        and comp.score > thresholds.complexity_max
    ):
        _fail(
            failures,
            "complexity",
            comp.score,
            thresholds.complexity_max,
            f"Complexity {comp.score:.1f} > {thresholds.complexity_max:.1f}",
        )

    # 5) Test coverage
    cov = cats.get("test_coverage")
    if cov and thresholds.test_coverage_min > 0 and cov.score < thresholds.test_coverage_min:
        _fail(
            failures,
            "test_coverage",
            cov.score,
            thresholds.test_coverage_min,
            f"Coverage {cov.score:.1f} < {thresholds.test_coverage_min:.1f}",
        )

    # 6) Performance
    perf = cats.get("performance")
    if perf and thresholds.performance_min > 0 and perf.score < thresholds.performance_min:
        _fail(
            failures,
            "performance",
            perf.score,
            thresholds.performance_min,
            f"Performance {perf.score:.1f} < {thresholds.performance_min:.1f}",
        )

    # 7) Critical security floor — absolute minimum regardless of thresholds
    sec_for_floor = cats.get("security")
    if sec_for_floor and sec_for_floor.score < _SECURITY_FLOOR_INDIVIDUAL:
        # Only add floor failure if not already failing on security
        has_security_failure = any(f.category == "security" for f in failures)
        if not has_security_failure:
            _fail(
                failures,
                "security",
                sec_for_floor.score,
                _SECURITY_FLOOR_INDIVIDUAL,
                "CRITICAL: Security score below minimum threshold (50)",
            )

    # Sort failures by category weight (highest weight first)
    failures.sort(key=lambda f: f.weight, reverse=True)

    # Collect suggestions from failing categories
    failing_cats = {f.category for f in failures}
    for name, cat in cats.items():
        if name in failing_cats and cat.suggestions:
            for tip in cat.suggestions:
                warnings.append(f"[{name}] {tip}")

    # Priority fix suggestion when multiple failures exist
    if len(failures) > 1:
        warnings.append("Fix these in order of priority (highest-weight categories first)")

    # Degraded result warning
    if score_result.degraded:
        tools = ", ".join(score_result.missing_tools) or "unknown"
        warnings.append(f"Degraded result - missing tools: {tools}")

    passed = len(failures) == 0

    logger.info(
        "gate_evaluation",
        passed=passed,
        failure_count=len(failures),
        overall=overall,
        preset=preset,
    )

    return GateResult(
        passed=passed,
        failures=failures,
        warnings=warnings,
        scores=scores,
        thresholds=thresholds,
        preset=preset,
    )

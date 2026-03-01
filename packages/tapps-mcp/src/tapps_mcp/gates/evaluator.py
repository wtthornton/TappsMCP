"""Quality gate evaluator.

Compares scoring results against configurable thresholds (presets)
and returns a pass / fail decision.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from tapps_core.config.settings import PRESETS
from tapps_mcp.gates.models import GateFailure, GateResult, GateThresholds
from tapps_mcp.scoring.constants import INDIVIDUAL_MAX

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

    # Collect suggestions from failing categories
    failing_cats = {f.category for f in failures}
    for name, cat in cats.items():
        if name in failing_cats and cat.suggestions:
            for tip in cat.suggestions:
                warnings.append(f"[{name}] {tip}")

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

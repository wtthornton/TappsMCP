"""Template promotion gate for version management.

Evaluates whether a candidate template version should be promoted
based on resolution rate improvements, redundancy thresholds,
sample size requirements, and significance thresholds.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from tapps_mcp.benchmark.template_versions import TemplateVersion, TemplateVersionStore

__all__ = [
    "PromotionCriteria",
    "PromotionDecision",
    "auto_promote",
    "evaluate_promotion",
]

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class PromotionCriteria(BaseModel):
    """Criteria for approving a template version promotion."""

    model_config = ConfigDict(frozen=True)

    min_resolution_delta: float = Field(
        default=0.0,
        description="Minimum resolution rate improvement over current version.",
    )
    max_redundancy: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Maximum acceptable redundancy score.",
    )
    min_instances_evaluated: int = Field(
        default=20,
        ge=1,
        description="Minimum number of instances that must be evaluated.",
    )
    significance_threshold: float = Field(
        default=0.1,
        ge=0.0,
        description="Minimum absolute resolution delta to consider meaningful.",
    )


class PromotionDecision(BaseModel):
    """Decision result from promotion evaluation."""

    model_config = ConfigDict(frozen=True)

    approved: bool = Field(description="Whether the promotion is approved.")
    reason: str = Field(description="Explanation for the decision.")
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-blocking warnings about the candidate.",
    )


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def evaluate_promotion(
    candidate: TemplateVersion,
    current: TemplateVersion | None,
    criteria: PromotionCriteria,
) -> PromotionDecision:
    """Evaluate whether a candidate version should be promoted.

    Checks the candidate against the promotion criteria:
    1. Candidate must have benchmark scores
    2. Enough instances must have been evaluated
    3. Resolution rate must improve over current (if present)
    4. Redundancy must be within threshold
    5. Improvement must be above significance threshold

    Args:
        candidate: Candidate template version to evaluate.
        current: Currently promoted version (``None`` if first promotion).
        criteria: Promotion criteria to apply.

    Returns:
        Promotion decision with approval status and reasoning.
    """
    warnings: list[str] = []

    # Check 1: Candidate must have benchmark scores
    if candidate.benchmark_scores is None:
        return PromotionDecision(
            approved=False,
            reason="Candidate has no benchmark scores recorded.",
            warnings=warnings,
        )

    candidate_rate = candidate.benchmark_scores.resolution_rate
    candidate_instances = candidate.benchmark_scores.total_instances

    # Check 2: Minimum instances evaluated
    if candidate_instances < criteria.min_instances_evaluated:
        return PromotionDecision(
            approved=False,
            reason=(
                f"Insufficient evaluation: {candidate_instances} instances "
                f"evaluated, minimum required is {criteria.min_instances_evaluated}."
            ),
            warnings=warnings,
        )

    # Check 3: Redundancy threshold
    if candidate.redundancy_score is not None:
        if candidate.redundancy_score > criteria.max_redundancy:
            return PromotionDecision(
                approved=False,
                reason=(
                    f"Redundancy too high: {candidate.redundancy_score:.2f} "
                    f"exceeds maximum of {criteria.max_redundancy:.2f}."
                ),
                warnings=warnings,
            )
    else:
        warnings.append("No redundancy score available for candidate.")

    # Check 4: Resolution rate improvement over current
    if current is not None and current.benchmark_scores is not None:
        current_rate = current.benchmark_scores.resolution_rate

        delta = candidate_rate - current_rate

        if delta < criteria.min_resolution_delta:
            return PromotionDecision(
                approved=False,
                reason=(
                    f"Resolution rate did not improve enough: "
                    f"{candidate_rate:.1%} vs current {current_rate:.1%} "
                    f"(delta {delta:+.1%}, minimum required "
                    f"{criteria.min_resolution_delta:+.1%})."
                ),
                warnings=warnings,
            )

        # Check 5: Significance threshold
        if abs(delta) < criteria.significance_threshold:
            warnings.append(
                f"Resolution delta ({delta:+.1%}) is below "
                f"significance threshold ({criteria.significance_threshold:.1%})."
            )

        reason = (
            f"Approved: resolution rate improved from "
            f"{current_rate:.1%} to {candidate_rate:.1%} "
            f"(delta {delta:+.1%})."
        )
    else:
        # No current version to compare against - approve if scores exist
        reason = (
            f"Approved: first promotion with {candidate_rate:.1%} "
            f"resolution rate across {candidate_instances} instances."
        )
        if current is None:
            warnings.append("No current promoted version to compare against.")

    logger.info(
        "promotion_evaluated",
        version=candidate.version,
        approved=True,
        rate=round(candidate_rate, 4),
        warnings=warnings,
    )

    return PromotionDecision(
        approved=True,
        reason=reason,
        warnings=warnings,
    )


def auto_promote(
    candidate_version: int,
    store: TemplateVersionStore,
) -> bool:
    """Automatically evaluate and promote a candidate version.

    Looks up the candidate version, finds the current best for the
    same engagement level, evaluates against default criteria, and
    promotes if approved.

    Args:
        candidate_version: Version number of the candidate.
        store: Template version store.

    Returns:
        ``True`` if the version was promoted, ``False`` otherwise.
    """
    history = store.get_history("", limit=1000)
    candidate: TemplateVersion | None = None
    for v in history:
        if v.version == candidate_version:
            candidate = v
            break

    if candidate is None:
        # Try fetching directly from the store
        all_levels = ("high", "medium", "low")
        for level in all_levels:
            versions = store.get_history(level, limit=1000)
            for v in versions:
                if v.version == candidate_version:
                    candidate = v
                    break
            if candidate is not None:
                break

    if candidate is None:
        logger.warning(
            "auto_promote_candidate_not_found",
            version=candidate_version,
        )
        return False

    current = store.get_best(candidate.engagement_level)
    criteria = PromotionCriteria()
    decision = evaluate_promotion(candidate, current, criteria)

    if decision.approved:
        store.promote(candidate_version, decision.reason)
        logger.info(
            "auto_promote_success",
            version=candidate_version,
            reason=decision.reason,
        )
        return True

    logger.info(
        "auto_promote_rejected",
        version=candidate_version,
        reason=decision.reason,
    )
    return False

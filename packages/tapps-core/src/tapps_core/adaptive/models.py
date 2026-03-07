"""Pydantic models for the adaptive learning subsystem."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

# Weight matrix thresholds.
_PRIMARY_WEIGHT_FLOOR = 0.51
_WEIGHT_SUM_TOLERANCE = 0.01


def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(tz=UTC).isoformat()


# ---------------------------------------------------------------------------
# Outcome tracking
# ---------------------------------------------------------------------------


class CodeOutcome(BaseModel):
    """A single code-quality outcome record.

    Tracks initial vs. final scores for a workflow, enabling correlation
    analysis between individual metrics and first-pass success.
    """

    workflow_id: str = Field(description="Unique workflow identifier.")
    file_path: str = Field(description="Path to the scored file.")
    initial_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Scores from the first review pass (metric -> 0-10).",
    )
    final_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Scores from the last review pass (metric -> 0-10).",
    )
    iterations: int = Field(default=1, ge=1, description="Number of review iterations.")
    expert_consultations: list[str] = Field(
        default_factory=list,
        description="Expert IDs consulted during the workflow.",
    )
    time_to_correctness: float = Field(
        default=0.0,
        ge=0.0,
        description="Seconds to reach quality threshold.",
    )
    first_pass_success: bool = Field(
        default=False,
        description="Whether the code met the quality gate on the first pass.",
    )
    timestamp: str = Field(
        default_factory=_utc_now_iso,
        description="ISO-8601 UTC timestamp.",
    )
    agent_id: str | None = Field(default=None, description="Generating agent ID.")
    prompt_hash: str | None = Field(
        default=None, description="SHA-256 hash of the original prompt."
    )


# ---------------------------------------------------------------------------
# Expert performance
# ---------------------------------------------------------------------------


class ExpertPerformance(BaseModel):
    """Aggregated performance metrics for a single expert.

    Not frozen because fields are populated incrementally during calculation.
    """

    expert_id: str = Field(description="Expert identifier.")
    consultations: int = Field(default=0, ge=0, description="Total consultations.")
    avg_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Average confidence.")
    first_pass_success_rate: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Fraction of first-pass successes."
    )
    code_quality_improvement: float = Field(
        default=0.0,
        description="Average quality improvement (final - initial score).",
    )
    domain_coverage: list[str] = Field(
        default_factory=list, description="Domains this expert has been consulted on."
    )
    weaknesses: list[str] = Field(default_factory=list, description="Identified weakness areas.")
    last_updated: str = Field(default_factory=_utc_now_iso, description="ISO-8601 UTC timestamp.")


# ---------------------------------------------------------------------------
# Expert weight matrix
# ---------------------------------------------------------------------------


class ExpertWeightMatrix(BaseModel):
    """Expert-to-domain voting weight matrix.

    Each domain column should sum to 1.0, and each domain must have
    exactly one primary expert with weight >= 0.51.
    """

    weights: dict[str, dict[str, float]] = Field(
        default_factory=dict,
        description="Mapping of expert_id -> {domain -> weight}.",
    )
    domains: list[str] = Field(default_factory=list, description="All domains in the matrix.")
    experts: list[str] = Field(default_factory=list, description="All expert IDs in the matrix.")

    def get_expert_weight(self, expert_id: str, domain: str) -> float:
        """Return the weight for *expert_id* in *domain* (0.0 if absent)."""
        return self.weights.get(expert_id, {}).get(domain, 0.0)

    def get_primary_expert(self, domain: str) -> str | None:
        """Return the primary expert for *domain* (weight >= 0.51), or ``None``."""
        best_id: str | None = None
        best_weight = 0.0
        for expert_id in self.experts:
            w = self.get_expert_weight(expert_id, domain)
            if w > best_weight:
                best_weight = w
                best_id = expert_id
        if best_weight >= _PRIMARY_WEIGHT_FLOOR or (len(self.experts) == 1 and best_id is not None):
            return best_id
        return None

    def get_primary_expert_domain(self, expert_id: str) -> str | None:
        """Return the domain where *expert_id* is primary, or ``None``."""
        for domain in self.domains:
            if self.get_primary_expert(domain) == expert_id:
                return domain
        return None

    def validate_matrix(self) -> list[str]:
        """Return a list of validation errors (empty if valid)."""
        errors: list[str] = []
        for domain in self.domains:
            total = sum(self.get_expert_weight(eid, domain) for eid in self.experts)
            if abs(total - 1.0) > _WEIGHT_SUM_TOLERANCE:
                errors.append(f"Domain '{domain}' weights sum to {total:.4f}, expected 1.0")
            primary = self.get_primary_expert(domain)
            if primary is None:
                errors.append(f"Domain '{domain}' has no primary expert (>= 0.51)")
        return errors


# ---------------------------------------------------------------------------
# Persistence snapshots
# ---------------------------------------------------------------------------


class AdaptiveWeightsSnapshot(BaseModel):
    """Persisted snapshot of adaptive scoring weights."""

    weights: dict[str, float] = Field(description="Learned scoring weights.")
    correlations: dict[str, float] = Field(
        default_factory=dict, description="Last computed metric correlations."
    )
    outcomes_analyzed: int = Field(default=0, ge=0, description="Number of outcomes used.")
    timestamp: str = Field(default_factory=_utc_now_iso, description="ISO-8601 UTC timestamp.")
    learning_rate: float = Field(default=0.1, ge=0.0, le=1.0, description="Learning rate used.")


class ExpertWeightsSnapshot(BaseModel):
    """Persisted snapshot of expert voting weights."""

    matrix: ExpertWeightMatrix = Field(description="The expert weight matrix.")
    timestamp: str = Field(default_factory=_utc_now_iso, description="ISO-8601 UTC timestamp.")
    performance_summary: dict[str, Any] = Field(
        default_factory=dict, description="Summary of expert performance at snapshot time."
    )


# ---------------------------------------------------------------------------
# Domain routing weights (Epic 57)
# ---------------------------------------------------------------------------


class DomainWeightEntry(BaseModel):
    """A single domain routing weight entry.

    Tracks learned routing weight for a domain based on feedback.
    Higher weights indicate the domain should be prioritized in routing.
    """

    domain: str = Field(description="Domain identifier (e.g., 'security', 'acme-billing').")
    weight: float = Field(default=1.0, ge=0.0, description="Learned routing weight.")
    samples: int = Field(default=0, ge=0, description="Number of feedback samples.")
    positive_count: int = Field(default=0, ge=0, description="Positive feedback count.")
    negative_count: int = Field(default=0, ge=0, description="Negative feedback count.")
    last_updated: str = Field(default_factory=_utc_now_iso, description="ISO-8601 UTC timestamp.")


class DomainWeightsSnapshot(BaseModel):
    """Persisted snapshot of domain routing weights.

    Separates technical (built-in) and business (project-specific) domain weights
    to allow independent learning and persistence.
    """

    technical: dict[str, DomainWeightEntry] = Field(
        default_factory=dict,
        description="Weights for built-in technical domains.",
    )
    business: dict[str, DomainWeightEntry] = Field(
        default_factory=dict,
        description="Weights for project-specific business domains.",
    )
    timestamp: str = Field(default_factory=_utc_now_iso, description="ISO-8601 UTC timestamp.")
    version: int = Field(default=1, ge=1, description="Schema version for migrations.")

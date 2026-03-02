"""Pydantic v2 models for the benchmark subsystem."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

__all__ = [
    "BenchmarkConfig",
    "BenchmarkInstance",
    "BenchmarkResult",
    "BenchmarkSummary",
    "ComparisonReport",
    "ContextMode",
    "EngagementReport",
    "RepoBreakdown",
    "RunMetadata",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(tz=UTC).isoformat()


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ContextMode(StrEnum):
    """Context injection mode for benchmark runs."""

    NONE = "none"
    TAPPS = "tapps"
    HUMAN = "human"
    ALL = "all"


# ---------------------------------------------------------------------------
# Instance (input data)
# ---------------------------------------------------------------------------


class BenchmarkInstance(BaseModel):
    """A single benchmark instance mirroring the AGENTBench HuggingFace schema."""

    model_config = ConfigDict(frozen=True)

    instance_id: str = Field(description="Unique identifier for this instance.")
    repo: str = Field(description="Repository name (org/repo format).")
    problem_description: str = Field(description="Natural-language problem statement.")
    clean_pr_patch: str = Field(description="Gold-standard patch (unified diff).")
    test_commands: list[str] = Field(description="Commands to run the test suite.")
    test_file_names: list[str] = Field(description="Paths to test files.")
    test_file_contents: dict[str, str] = Field(
        description="Mapping of test file path to file contents."
    )
    docker_image: str = Field(description="Docker image for the evaluation sandbox.")
    setup_commands: list[str] = Field(
        default_factory=list, description="Commands to prepare the sandbox."
    )
    key_files: list[str] = Field(
        default_factory=list, description="Important files the agent should examine."
    )
    risk_factors: list[str] | None = Field(
        default=None, description="Known risk factors for this instance."
    )
    rationale: str | None = Field(
        default=None, description="Human rationale for expected difficulty."
    )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class BenchmarkConfig(BaseModel):
    """Configuration for a benchmark run."""

    model_config = ConfigDict(frozen=True)

    dataset_name: str = Field(
        default="eth-sri/agentbench",
        description="HuggingFace dataset ID or local path.",
    )
    context_mode: ContextMode = Field(
        default=ContextMode.NONE,
        description="Context injection mode.",
    )
    engagement_level: str = Field(
        default="medium",
        description="TappsMCP engagement level (high/medium/low).",
    )
    subset_size: int = Field(
        default=20,
        ge=0,
        description="Number of instances to sample (0 = all).",
    )
    workers: int = Field(
        default=4,
        ge=1,
        description="Number of parallel evaluation workers.",
    )
    output_dir: Path = Field(
        default=Path(".tapps-mcp/benchmark/"),
        description="Directory for benchmark output artifacts.",
    )
    docker_timeout: int = Field(
        default=300,
        ge=30,
        description="Per-instance Docker sandbox timeout in seconds.",
    )
    random_seed: int = Field(
        default=42,
        description="Random seed for reproducible instance sampling.",
    )

    @field_validator("engagement_level")
    @classmethod
    def _validate_engagement_level(cls, v: str) -> str:
        allowed = {"high", "medium", "low"}
        if v not in allowed:
            msg = f"engagement_level must be one of {sorted(allowed)}, got {v!r}"
            raise ValueError(msg)
        return v


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


class BenchmarkResult(BaseModel):
    """Result for a single benchmark instance evaluation."""

    instance_id: str = Field(description="Instance that was evaluated.")
    context_mode: ContextMode = Field(description="Context mode used.")
    engagement_level: str = Field(description="Engagement level used.")
    resolved: bool = Field(description="Whether the agent resolved the issue.")
    token_usage: int = Field(default=0, ge=0, description="Total tokens consumed.")
    inference_cost: float = Field(default=0.0, ge=0.0, description="Estimated cost in USD.")
    steps: int = Field(default=0, ge=0, description="Number of agent steps taken.")
    patch_size: int = Field(default=0, ge=0, description="Lines changed in the agent patch.")
    error: str | None = Field(default=None, description="Error message if evaluation failed.")
    duration_ms: int = Field(default=0, ge=0, description="Wall-clock duration in milliseconds.")
    timestamp: str = Field(
        default_factory=_utc_now_iso,
        description="ISO-8601 timestamp of result creation.",
    )


# ---------------------------------------------------------------------------
# Aggregations
# ---------------------------------------------------------------------------


class RepoBreakdown(BaseModel):
    """Per-repository resolution statistics."""

    repo: str = Field(description="Repository name.")
    total: int = Field(ge=0, description="Total instances for this repo.")
    resolved: int = Field(ge=0, description="Resolved instances for this repo.")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def resolution_rate(self) -> float:
        """Fraction of resolved instances (0.0-1.0)."""
        if self.total == 0:
            return 0.0
        return self.resolved / self.total


class BenchmarkSummary(BaseModel):
    """Aggregated results for a benchmark run."""

    total_instances: int = Field(ge=0, description="Total instances evaluated.")
    resolved_count: int = Field(ge=0, description="Total instances resolved.")
    avg_tokens: float = Field(ge=0.0, description="Mean token usage per instance.")
    avg_cost: float = Field(ge=0.0, description="Mean inference cost per instance.")
    avg_steps: float = Field(ge=0.0, description="Mean steps per instance.")
    per_repo_breakdown: dict[str, RepoBreakdown] = Field(
        default_factory=dict,
        description="Per-repository breakdown.",
    )
    context_mode: ContextMode = Field(description="Context mode for this run.")
    engagement_level: str = Field(description="Engagement level for this run.")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def resolution_rate(self) -> float:
        """Fraction of resolved instances (0.0-1.0)."""
        if self.total_instances == 0:
            return 0.0
        return self.resolved_count / self.total_instances


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


class ComparisonReport(BaseModel):
    """Comparison between a baseline and treatment benchmark run."""

    baseline: BenchmarkSummary = Field(description="Baseline run summary.")
    treatment: BenchmarkSummary = Field(description="Treatment run summary.")
    resolution_delta: float = Field(description="Treatment resolution rate minus baseline rate.")
    token_delta: float = Field(description="Treatment avg tokens minus baseline avg tokens.")
    cost_delta: float = Field(description="Treatment avg cost minus baseline avg cost.")
    per_repo_deltas: dict[str, float] = Field(
        default_factory=dict,
        description="Per-repository resolution rate deltas.",
    )
    statistically_significant: bool | None = Field(
        default=None,
        description="Whether the delta is statistically significant (None if not computed).",
    )
    p_value: float | None = Field(
        default=None,
        description="P-value from significance test (None if not computed).",
    )


# ---------------------------------------------------------------------------
# Run metadata
# ---------------------------------------------------------------------------


class RunMetadata(BaseModel):
    """Metadata for a benchmark run."""

    run_id: str = Field(description="Unique run identifier.")
    timestamp: str = Field(
        default_factory=_utc_now_iso,
        description="ISO-8601 timestamp of run start.",
    )
    config: BenchmarkConfig = Field(description="Configuration used for the run.")
    instance_count: int = Field(ge=0, description="Number of instances in this run.")
    context_mode: ContextMode = Field(description="Context mode for the run.")


# ---------------------------------------------------------------------------
# Engagement comparison
# ---------------------------------------------------------------------------


class EngagementReport(BaseModel):
    """Side-by-side comparison of engagement levels."""

    results_by_level: dict[str, BenchmarkSummary] = Field(description="Per-level results.")
    recommended_level: str = Field(description="Recommended level.")
    recommendation_reason: str = Field(description="Why this level is recommended.")

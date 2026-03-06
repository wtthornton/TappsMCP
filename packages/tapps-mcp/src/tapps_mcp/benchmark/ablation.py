"""Section ablation testing for template optimization.

Systematically removes one section at a time from a template and
evaluates the impact on benchmark resolution rates. Identifies
sections that are essential, neutral, or harmful to performance.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

import structlog
from pydantic import BaseModel, ConfigDict, Field

from tapps_mcp.benchmark.models import BenchmarkConfig, BenchmarkResult  # noqa: TC001

__all__ = [
    "AblationConfig",
    "AblationResult",
    "AblationRunner",
]

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Thresholds for section classification
# ---------------------------------------------------------------------------

# If removing a section causes resolution to drop by more than 2%, it is essential.
_ESSENTIAL_THRESHOLD = -0.02

# If removing a section improves resolution by more than 1%, it is harmful.
_HARMFUL_THRESHOLD = 0.01


# ---------------------------------------------------------------------------
# Evaluator protocol
# ---------------------------------------------------------------------------


class _EvaluatorProtocol(Protocol):
    """Protocol matching MockEvaluator and Evaluator interfaces."""

    async def evaluate_batch(
        self,
        instances: Any,  # noqa: ANN401
        context_mode: Any,  # noqa: ANN401
        engagement_level: str,
    ) -> list[BenchmarkResult]: ...


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class AblationConfig(BaseModel):
    """Configuration for an ablation test run."""

    model_config = ConfigDict(frozen=True)

    base_template: str = Field(description="Full template content to ablate.")
    sections: list[str] = Field(description="Section names to test removing.")
    benchmark_config: BenchmarkConfig = Field(description="Benchmark configuration.")
    baseline_results: list[BenchmarkResult] | None = Field(
        default=None,
        description="Pre-computed baseline results (full template). "
        "Computed automatically if not provided.",
    )


class AblationResult(BaseModel):
    """Result of removing a single section from the template."""

    model_config = ConfigDict(frozen=True)

    removed_section: str = Field(description="Name of the removed section.")
    resolution_rate: float = Field(description="Resolution rate with section removed.")
    delta_vs_full: float = Field(
        description="Delta compared to full template (negative = worse without section)."
    )
    delta_vs_none: float = Field(description="Delta compared to no-context baseline.")
    cost_delta: float = Field(default=0.0, description="Cost delta vs full template.")
    recommendation: str = Field(description="Classification: 'essential', 'neutral', or 'harmful'.")


# ---------------------------------------------------------------------------
# Section manipulation
# ---------------------------------------------------------------------------


def _split_sections(text: str) -> list[tuple[str, str]]:
    """Split markdown on ``## `` headers into (name, full_text) tuples.

    The full_text includes the ``## `` prefix so sections can be
    reassembled by concatenation.
    """
    parts = re.split(r"(?m)(?=^## )", text)
    sections: list[tuple[str, str]] = []
    for part in parts:
        stripped = part.strip()
        if not stripped:
            continue
        # Extract section name from first line
        first_line = stripped.split("\n", 1)[0]
        name = first_line.lstrip("#").strip()
        sections.append((name, part))
    return sections


def _remove_section(template: str, section_name: str) -> str:
    """Remove a named section from a markdown template.

    Finds the section starting with ``## {section_name}`` and removes
    everything up to the next ``## `` header or end of text.
    """
    pattern = rf"(?m)^## {re.escape(section_name)}\s*\n(?:(?!^## ).|\n)*"
    result = re.sub(pattern, "", template)
    # Clean up multiple blank lines
    return re.sub(r"\n{3,}", "\n\n", result).strip() + "\n"


def _compute_resolution_rate(results: list[BenchmarkResult]) -> float:
    """Compute resolution rate from a list of results."""
    if not results:
        return 0.0
    resolved = sum(1 for r in results if r.resolved)
    return resolved / len(results)


def _compute_avg_cost(results: list[BenchmarkResult]) -> float:
    """Compute average inference cost from results."""
    if not results:
        return 0.0
    return sum(r.inference_cost for r in results) / len(results)


def _classify_section(delta_vs_full: float) -> str:
    """Classify a section based on the ablation delta.

    - ``"essential"``: Removing it drops resolution by more than 2%
    - ``"harmful"``: Removing it improves resolution by more than 1%
    - ``"neutral"``: Everything in between
    """
    if delta_vs_full < _ESSENTIAL_THRESHOLD:
        return "essential"
    if delta_vs_full > _HARMFUL_THRESHOLD:
        return "harmful"
    return "neutral"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class AblationRunner:
    """Runs section ablation tests on a template."""

    async def run_ablation(
        self,
        config: AblationConfig,
        evaluator: _EvaluatorProtocol,
    ) -> list[AblationResult]:
        """Run ablation tests, removing one section at a time.

        If ``config.baseline_results`` is not provided, the full template
        is evaluated first as the baseline.

        Args:
            config: Ablation configuration.
            evaluator: Evaluator (mock or real) for running benchmarks.

        Returns:
            List of ablation results, one per section.
        """
        from tapps_mcp.benchmark.dataset import DatasetLoader

        # Load instances
        loader = DatasetLoader(config.benchmark_config)
        instances = await loader.load()

        # Compute or use provided baseline
        baseline_results = config.baseline_results
        if baseline_results is None:
            baseline_results = await evaluator.evaluate_batch(
                instances,
                config.benchmark_config.context_mode,
                config.benchmark_config.engagement_level,
            )

        full_rate = _compute_resolution_rate(baseline_results)
        full_cost = _compute_avg_cost(baseline_results)

        # Compute no-context baseline for delta_vs_none
        from tapps_mcp.benchmark.models import ContextMode

        none_results = await evaluator.evaluate_batch(
            instances,
            ContextMode.NONE,
            config.benchmark_config.engagement_level,
        )
        none_rate = _compute_resolution_rate(none_results)

        logger.info(
            "ablation_baseline",
            full_rate=round(full_rate, 4),
            none_rate=round(none_rate, 4),
            sections=len(config.sections),
        )

        # Run ablation for each section
        results: list[AblationResult] = []
        for section_name in config.sections:
            ablated_template = _remove_section(config.base_template, section_name)

            # Evaluate with ablated template
            # TODO: pass ablated_template to evaluator when template injection is wired up
            ablated_results = await evaluator.evaluate_batch(
                instances,
                config.benchmark_config.context_mode,
                config.benchmark_config.engagement_level,
            )

            ablated_rate = _compute_resolution_rate(ablated_results)
            ablated_cost = _compute_avg_cost(ablated_results)

            delta_vs_full = ablated_rate - full_rate
            delta_vs_none = ablated_rate - none_rate
            cost_delta = ablated_cost - full_cost

            result = AblationResult(
                removed_section=section_name,
                resolution_rate=round(ablated_rate, 4),
                delta_vs_full=round(delta_vs_full, 4),
                delta_vs_none=round(delta_vs_none, 4),
                cost_delta=round(cost_delta, 6),
                recommendation=_classify_section(delta_vs_full),
            )
            results.append(result)

            logger.debug(
                "ablation_section_result",
                section=section_name,
                ablated_template_len=len(ablated_template),
                rate=round(ablated_rate, 4),
                delta=round(delta_vs_full, 4),
                recommendation=result.recommendation,
            )

        return results

    def generate_optimal_template(
        self,
        results: list[AblationResult],
        base_template: str,
    ) -> str:
        """Generate an optimal template by removing harmful sections.

        Args:
            results: Ablation results from ``run_ablation``.
            base_template: Original full template.

        Returns:
            Template with harmful sections removed.
        """
        harmful_sections = [r.removed_section for r in results if r.recommendation == "harmful"]

        optimized = base_template
        for section_name in harmful_sections:
            optimized = _remove_section(optimized, section_name)

        logger.info(
            "optimal_template_generated",
            removed_sections=harmful_sections,
            removed_count=len(harmful_sections),
        )

        return optimized

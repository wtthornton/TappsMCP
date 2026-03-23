"""Mock evaluator for benchmark testing without Docker or API access."""

from __future__ import annotations

import hashlib
from typing import Any

from tapps_mcp.benchmark.models import (
    BenchmarkInstance,
    BenchmarkResult,
    ContextMode,
)

__all__ = ["MockEvaluator", "make_test_result"]


class MockEvaluator:
    """Returns predetermined results for benchmark testing.

    Can be configured with specific outcomes per instance, or uses defaults:
    - NONE context: 30% resolution rate
    - TAPPS context: 45% resolution rate
    - HUMAN context: 50% resolution rate
    """

    def __init__(
        self,
        outcomes: dict[tuple[str, ContextMode], bool] | None = None,
        default_resolution_rates: dict[ContextMode, float] | None = None,
        seed: int = 42,
    ) -> None:
        self._outcomes = outcomes or {}
        self._rates = default_resolution_rates or {
            ContextMode.NONE: 0.30,
            ContextMode.TAPPS: 0.45,
            ContextMode.HUMAN: 0.50,
        }
        self._seed = seed
        self._call_count = 0

    async def evaluate_instance(
        self,
        instance: BenchmarkInstance,
        context_mode: ContextMode,
        engagement_level: str = "medium",
    ) -> BenchmarkResult:
        """Evaluate a single instance with mock results."""
        self._call_count += 1

        # Check for predetermined outcome
        key = (instance.instance_id, context_mode)
        if key in self._outcomes:
            resolved = self._outcomes[key]
        else:
            # Use deterministic pseudo-random based on instance_id + mode
            hash_input = f"{instance.instance_id}:{context_mode.value}:{self._seed}"
            hash_val = int(hashlib.sha256(hash_input.encode()).hexdigest()[:8], 16)
            threshold = self._rates.get(context_mode, 0.3)
            resolved = (hash_val % 100) / 100.0 < threshold

        # Generate realistic mock metrics
        base_tokens = 1500 + (self._call_count * 100) % 500
        return BenchmarkResult(
            instance_id=instance.instance_id,
            context_mode=context_mode,
            engagement_level=engagement_level,
            resolved=resolved,
            token_usage=base_tokens + (200 if context_mode != ContextMode.NONE else 0),
            inference_cost=base_tokens * 0.00001,
            steps=3 + self._call_count % 5,
            patch_size=len(instance.clean_pr_patch) if resolved else 0,
            duration_ms=2000 + (self._call_count * 300) % 3000,
        )

    async def evaluate_batch(
        self,
        instances: list[BenchmarkInstance],
        context_mode: ContextMode,
        engagement_level: str = "medium",
        template_override: str | None = None,
    ) -> list[BenchmarkResult]:
        """Evaluate a batch of instances."""
        results: list[BenchmarkResult] = []
        for inst in instances:
            result = await self.evaluate_instance(inst, context_mode, engagement_level)
            results.append(result)
        return results

    @property
    def call_count(self) -> int:
        """Number of evaluate_instance calls made."""
        return self._call_count


def make_test_result(
    instance_id: str = "test-001",
    context_mode: ContextMode = ContextMode.NONE,
    resolved: bool = True,
    **kwargs: Any,  # noqa: ANN401
) -> BenchmarkResult:
    """Factory for creating BenchmarkResult instances in tests."""
    defaults: dict[str, Any] = {
        "instance_id": instance_id,
        "context_mode": context_mode,
        "engagement_level": "medium",
        "resolved": resolved,
        "token_usage": 1500,
        "inference_cost": 0.015,
        "steps": 5,
        "patch_size": 200 if resolved else 0,
        "duration_ms": 3000,
    }
    defaults.update(kwargs)
    return BenchmarkResult(**defaults)

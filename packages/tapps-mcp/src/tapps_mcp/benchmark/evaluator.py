"""Benchmark evaluation orchestrator.

Coordinates running benchmark instances across context modes with
configurable parallelism, progress tracking, and error isolation.
"""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

import structlog

from tapps_mcp.benchmark.context_injector import ContextInjector
from tapps_mcp.benchmark.models import (
    BenchmarkConfig,
    BenchmarkInstance,
    BenchmarkResult,
    ContextMode,
)

logger = structlog.get_logger()

__all__ = ["Evaluator", "EvaluatorBackend"]


class EvaluatorBackend(Protocol):
    """Protocol for evaluation backends (Docker or Mock)."""

    async def evaluate_instance(
        self,
        instance: BenchmarkInstance,
        context_mode: ContextMode,
        engagement_level: str,
    ) -> BenchmarkResult: ...


class Evaluator:
    """Orchestrates benchmark evaluation across instances and conditions.

    Delegates actual evaluation to a backend (Docker or Mock) while
    managing parallelism, error handling, and progress reporting.
    """

    def __init__(
        self,
        config: BenchmarkConfig,
        backend: EvaluatorBackend | None = None,
    ) -> None:
        self._config = config
        self._backend = backend
        self._injector = ContextInjector(config.engagement_level)

    @property
    def injector(self) -> ContextInjector:
        """Access the context injector for this evaluator."""
        return self._injector

    async def evaluate_instance(
        self,
        instance: BenchmarkInstance,
        context_mode: ContextMode,
    ) -> BenchmarkResult:
        """Evaluate a single instance with a given context mode.

        When a backend is configured, delegates to it. Otherwise returns
        an unresolved result with an error message.

        Args:
            instance: Benchmark instance to evaluate.
            context_mode: Context injection mode.

        Returns:
            Evaluation result for the instance.
        """
        if self._backend is not None:
            return await self._backend.evaluate_instance(
                instance,
                context_mode,
                self._config.engagement_level,
            )
        # Fallback: return unresolved result (no backend configured)
        return BenchmarkResult(
            instance_id=instance.instance_id,
            context_mode=context_mode,
            engagement_level=self._config.engagement_level,
            resolved=False,
            error="No evaluation backend configured",
        )

    async def evaluate_batch(
        self,
        instances: list[BenchmarkInstance],
        context_mode: ContextMode,
        progress_callback: Any = None,
        template_override: str | None = None,
    ) -> list[BenchmarkResult]:
        """Evaluate a batch with configurable parallelism.

        Individual failures are caught and returned as unresolved results
        rather than crashing the entire batch.

        Args:
            instances: Benchmark instances to evaluate.
            context_mode: Context injection mode.
            progress_callback: Optional callable(completed, total) for
                progress reporting.
            template_override: Optional template content to use instead
                of the default generated template (for ablation testing).

        Returns:
            List of results in the same order as instances.
        """
        semaphore = asyncio.Semaphore(self._config.workers)
        completed = 0

        async def _eval_one(
            inst: BenchmarkInstance,
        ) -> BenchmarkResult:
            nonlocal completed
            async with semaphore:
                try:
                    result = await self.evaluate_instance(inst, context_mode)
                except Exception as exc:
                    result = BenchmarkResult(
                        instance_id=inst.instance_id,
                        context_mode=context_mode,
                        engagement_level=self._config.engagement_level,
                        resolved=False,
                        error=str(exc),
                    )
                completed += 1
                if progress_callback:
                    progress_callback(completed, len(instances))
                return result

        tasks = [_eval_one(inst) for inst in instances]
        results = await asyncio.gather(*tasks)
        return list(results)

    async def evaluate_all_conditions(
        self,
        instances: list[BenchmarkInstance],
    ) -> dict[ContextMode, list[BenchmarkResult]]:
        """Evaluate instances across all context modes.

        When the config context_mode is ALL, evaluates NONE, TAPPS, and
        HUMAN. Otherwise evaluates only the specified mode.

        Args:
            instances: Benchmark instances to evaluate.

        Returns:
            Mapping from context mode to evaluation results.
        """
        modes: list[ContextMode]
        if self._config.context_mode == ContextMode.ALL:
            modes = [
                ContextMode.NONE,
                ContextMode.TAPPS,
                ContextMode.HUMAN,
            ]
        else:
            modes = [self._config.context_mode]

        results: dict[ContextMode, list[BenchmarkResult]] = {}
        for mode in modes:
            logger.info(
                "evaluating_condition",
                mode=mode.value,
                instances=len(instances),
            )
            results[mode] = await self.evaluate_batch(instances, mode)
        return results

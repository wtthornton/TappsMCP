"""Tool impact measurement and effectiveness evaluation.

Evaluates how individual MCP tools affect task resolution by running
tasks under different tool availability conditions (all tools, no tools,
all-minus-one) and computing per-tool impact rankings.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from enum import StrEnum

import structlog
from pydantic import BaseModel, ConfigDict, Field

from tapps_mcp.benchmark.tool_task_models import BUILTIN_TASKS, ToolTask, ToolTaskResult

__all__ = [
    "MockToolEvaluator",
    "ToolCondition",
    "ToolEffectivenessReport",
    "ToolImpactEvaluator",
    "ToolImpactResult",
    "ToolRanking",
]

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ToolCondition(StrEnum):
    """Tool availability condition for evaluation."""

    ALL_TOOLS = "all_tools"
    NO_TOOLS = "no_tools"
    SINGLE_TOOL = "single_tool"
    ALL_MINUS_ONE = "all_minus_one"


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class ToolImpactResult(BaseModel):
    """Result from evaluating a task under a specific tool condition."""

    model_config = ConfigDict(frozen=True)

    task_id: str = Field(description="Task that was evaluated.")
    condition: ToolCondition = Field(description="Tool availability condition.")
    tool_name: str | None = Field(
        default=None,
        description="Tool that was removed or isolated.",
    )
    resolved: bool = Field(description="Whether the task was resolved.")
    tools_called: list[str] = Field(
        default_factory=list,
        description="Tools that were called during evaluation.",
    )
    call_count: int = Field(default=0, ge=0, description="Total tool calls made.")
    token_usage: int = Field(default=0, ge=0, description="Total tokens consumed.")
    duration_ms: int = Field(default=0, ge=0, description="Duration in milliseconds.")


class ToolRanking(BaseModel):
    """Aggregated ranking for a single tool's effectiveness."""

    model_config = ConfigDict(frozen=True)

    tool_name: str = Field(description="Name of the tool.")
    impact_score: float = Field(description="Aggregate impact score (higher is better).")
    tasks_helped: int = Field(ge=0, description="Tasks where removing the tool hurt resolution.")
    tasks_hurt: int = Field(ge=0, description="Tasks where removing the tool helped resolution.")
    tasks_neutral: int = Field(ge=0, description="Tasks unaffected by tool removal.")
    avg_token_cost: int = Field(ge=0, description="Average additional tokens when tool is present.")
    pass_at_k: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Pass@k metric (fraction of tasks helped).",
    )


class ToolEffectivenessReport(BaseModel):
    """Report summarizing tool effectiveness across all tasks."""

    model_config = ConfigDict(frozen=True)

    tool_rankings: list[ToolRanking] = Field(
        description="Tools ranked by impact score (descending).",
    )
    task_count: int = Field(ge=0, description="Total tasks evaluated.")
    condition_count: int = Field(ge=0, description="Total conditions evaluated.")


# ---------------------------------------------------------------------------
# Mock tool evaluator (for testing without a real agent)
# ---------------------------------------------------------------------------


class MockToolEvaluator:
    """Simulates tool availability effects on task resolution.

    Uses deterministic hashing to produce consistent results across runs.
    Tool availability affects resolution probability based on whether the
    task's expected tools overlap with available tools.
    """

    def __init__(self, seed: int = 42) -> None:
        self._seed = seed
        self._call_count = 0

    async def evaluate_task(
        self,
        task: ToolTask,
        available_tools: list[str],
    ) -> ToolTaskResult:
        """Evaluate a task with a specific set of available tools.

        Resolution probability is determined by how many of the task's
        expected tools are available. Full overlap gives ~80% resolution;
        no overlap gives ~20%.
        """
        self._call_count += 1

        expected = set(task.expected_tools)
        available = set(available_tools)
        overlap = expected & available
        coverage = len(overlap) / max(len(expected), 1)

        # Deterministic resolution based on task_id + available_tools
        tools_key = ",".join(sorted(available_tools))
        hash_input = f"{task.task_id}:{tools_key}:{self._seed}"
        hash_val = int(hashlib.sha256(hash_input.encode()).hexdigest()[:8], 16)
        threshold = 0.20 + (coverage * 0.60)
        resolved = (hash_val % 100) / 100.0 < threshold

        # Simulate tool calls (only call tools that are available and expected)
        tools_called = sorted(overlap)
        call_count = len(tools_called) + (1 if not tools_called else 0)

        base_tokens = 800 + (self._call_count * 50) % 400
        token_bonus = len(tools_called) * 150

        return ToolTaskResult(
            task_id=task.task_id,
            condition="all_tools" if len(available_tools) > 5 else "all_minus_one",
            tool_name=None,
            resolved=resolved,
            tools_called=tools_called,
            call_count=call_count,
            token_usage=base_tokens + token_bonus,
            duration_ms=1000 + call_count * 500,
        )

    @property
    def call_count(self) -> int:
        """Total evaluate_task calls made."""
        return self._call_count


# ---------------------------------------------------------------------------
# Tool impact evaluator
# ---------------------------------------------------------------------------

# All known tools that can be evaluated.
_ALL_TOOL_NAMES = [
    "tapps_session_start",
    "tapps_score_file",
    "tapps_quality_gate",
    "tapps_quick_check",
    "tapps_security_scan",
    "tapps_validate_changed",
    "tapps_lookup_docs",
    "tapps_checklist",
    "tapps_impact_analysis",
    "tapps_dead_code",
    "tapps_dependency_scan",
    "tapps_dependency_graph",
    "tapps_memory",
]


class ToolImpactEvaluator:
    """Evaluate the impact of individual MCP tools on task resolution.

    Runs tasks under different tool availability conditions and computes
    per-tool impact rankings based on resolution deltas.
    """

    def __init__(self, tasks: list[ToolTask] | None = None) -> None:
        self._tasks = tasks if tasks is not None else BUILTIN_TASKS

    @property
    def tasks(self) -> list[ToolTask]:
        """Tasks used for evaluation."""
        return list(self._tasks)

    async def evaluate_tool_impact(
        self,
        tool_name: str,
        evaluator: MockToolEvaluator,
    ) -> list[ToolImpactResult]:
        """Evaluate the impact of a single tool across all tasks.

        For each task, runs with ALL_TOOLS and ALL_MINUS_ONE (removing
        tool_name) to measure the delta in resolution.

        Args:
            tool_name: The tool to measure impact for.
            evaluator: Mock evaluator to simulate tool effects.

        Returns:
            Paired results (all_tools, all_minus_one) for each task.
        """
        results: list[ToolImpactResult] = []

        for task in self._tasks:
            # Run with all tools
            all_result = await evaluator.evaluate_task(task, _ALL_TOOL_NAMES)
            results.append(
                ToolImpactResult(
                    task_id=task.task_id,
                    condition=ToolCondition.ALL_TOOLS,
                    tool_name=tool_name,
                    resolved=all_result.resolved,
                    tools_called=all_result.tools_called,
                    call_count=all_result.call_count,
                    token_usage=all_result.token_usage,
                    duration_ms=all_result.duration_ms,
                )
            )

            # Run without the target tool
            minus_tools = [t for t in _ALL_TOOL_NAMES if t != tool_name]
            minus_result = await evaluator.evaluate_task(task, minus_tools)
            results.append(
                ToolImpactResult(
                    task_id=task.task_id,
                    condition=ToolCondition.ALL_MINUS_ONE,
                    tool_name=tool_name,
                    resolved=minus_result.resolved,
                    tools_called=minus_result.tools_called,
                    call_count=minus_result.call_count,
                    token_usage=minus_result.token_usage,
                    duration_ms=minus_result.duration_ms,
                )
            )

        logger.debug(
            "tool_impact_evaluated",
            tool=tool_name,
            task_count=len(self._tasks),
            result_count=len(results),
        )
        return results

    async def evaluate_all_tools(
        self,
        tools: list[str],
        evaluator: MockToolEvaluator,
    ) -> ToolEffectivenessReport:
        """Evaluate impact of all specified tools.

        For each tool, runs paired evaluation across all tasks, then
        ranks tools by aggregate impact score.

        Args:
            tools: List of tool names to evaluate.
            evaluator: Mock evaluator to simulate tool effects.

        Returns:
            Report with tool rankings ordered by impact score.
        """
        all_results: list[ToolImpactResult] = []
        for tool in tools:
            tool_results = await self.evaluate_tool_impact(tool, evaluator)
            all_results.extend(tool_results)

        rankings = self.compute_ranking(all_results)

        logger.info(
            "all_tools_evaluated",
            tool_count=len(tools),
            task_count=len(self._tasks),
            total_results=len(all_results),
        )

        return ToolEffectivenessReport(
            tool_rankings=rankings,
            task_count=len(self._tasks),
            condition_count=len(all_results),
        )

    def compute_ranking(self, results: list[ToolImpactResult]) -> list[ToolRanking]:
        """Compute per-tool rankings from paired evaluation results.

        Groups results by tool_name, then compares ALL_TOOLS vs
        ALL_MINUS_ONE outcomes per task to determine if the tool
        helped, hurt, or was neutral.

        Args:
            results: Paired ToolImpactResult entries.

        Returns:
            Rankings sorted by impact_score descending.
        """
        # Group by tool_name
        by_tool: dict[str, list[ToolImpactResult]] = defaultdict(list)
        for r in results:
            if r.tool_name:
                by_tool[r.tool_name].append(r)

        rankings: list[ToolRanking] = []

        for tool_name, tool_results in by_tool.items():
            # Pair ALL_TOOLS and ALL_MINUS_ONE by task_id
            all_tools_map: dict[str, ToolImpactResult] = {}
            minus_one_map: dict[str, ToolImpactResult] = {}

            for r in tool_results:
                if r.condition == ToolCondition.ALL_TOOLS:
                    all_tools_map[r.task_id] = r
                elif r.condition == ToolCondition.ALL_MINUS_ONE:
                    minus_one_map[r.task_id] = r

            helped = 0
            hurt = 0
            neutral = 0
            total_token_delta = 0
            pairs = 0

            for task_id, all_result in all_tools_map.items():
                if task_id not in minus_one_map:
                    continue
                pairs += 1
                minus_result = minus_one_map[task_id]

                if all_result.resolved and not minus_result.resolved:
                    helped += 1
                elif not all_result.resolved and minus_result.resolved:
                    hurt += 1
                else:
                    neutral += 1

                total_token_delta += all_result.token_usage - minus_result.token_usage

            # Impact score: fraction of tasks helped minus fraction hurt
            total_tasks = helped + hurt + neutral
            impact_score = 0.0
            if total_tasks > 0:
                impact_score = (helped - hurt) / total_tasks

            avg_token_cost = total_token_delta // max(pairs, 1)
            pass_at_k = helped / max(total_tasks, 1) if total_tasks > 0 else None

            rankings.append(
                ToolRanking(
                    tool_name=tool_name,
                    impact_score=round(impact_score, 4),
                    tasks_helped=helped,
                    tasks_hurt=hurt,
                    tasks_neutral=neutral,
                    avg_token_cost=max(avg_token_cost, 0),
                    pass_at_k=round(pass_at_k, 4) if pass_at_k is not None else None,
                )
            )

        # Sort by impact_score descending, then by name for stability
        rankings.sort(key=lambda r: (-r.impact_score, r.tool_name))
        return rankings

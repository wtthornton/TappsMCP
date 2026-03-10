"""Unit tests for Epic 32: MCP Tool Effectiveness Benchmarking.

Covers all 7 stories:
- Story 32.1: ToolTask models and BUILTIN_TASKS
- Story 32.2: ToolImpactEvaluator and MockToolEvaluator
- Story 32.3: CallPatternAnalyzer
- Story 32.4: ChecklistCalibrator
- Story 32.5: ExpertEffectivenessAnalyzer and MemoryEffectivenessAnalyzer
- Story 32.6: AdaptiveFeedbackGenerator
- Story 32.7: ToolEffectivenessSection and report generation
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from tapps_mcp.benchmark.adaptive_feedback import (
    AdaptiveFeedbackGenerator,
    BenchmarkFeedback,
)
from tapps_mcp.benchmark.call_patterns import (
    CallPattern,
    CallPatternAnalyzer,
    CallPatternReport,
    CallRecommendation,
)
from tapps_mcp.benchmark.checklist_calibrator import (
    ChecklistCalibration,
    ChecklistCalibrator,
    ToolTierClassification,
)
from tapps_mcp.benchmark.expert_tracker import (
    ExpertEffectiveness,
    ExpertEffectivenessAnalyzer,
    ExpertEffectivenessReport,
)
from tapps_mcp.benchmark.memory_tracker import (
    MemoryEffectiveness,
    MemoryEffectivenessAnalyzer,
    MemoryEffectivenessReport,
)
from tapps_mcp.benchmark.tool_evaluator import (
    MockToolEvaluator,
    ToolCondition,
    ToolEffectivenessReport,
    ToolImpactEvaluator,
    ToolImpactResult,
    ToolRanking,
)
from tapps_mcp.benchmark.tool_report import (
    ToolEffectivenessSection,
    generate_tool_effectiveness_report,
)
from tapps_mcp.benchmark.tool_task_models import (
    BUILTIN_TASKS,
    ToolTask,
    ToolTaskResult,
    ToolTaskVerification,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_impact_result(
    task_id: str = "test-task",
    condition: ToolCondition = ToolCondition.ALL_TOOLS,
    tool_name: str | None = None,
    resolved: bool = True,
    tools_called: list[str] | None = None,
    call_count: int = 2,
    token_usage: int = 1500,
    duration_ms: int = 2000,
) -> ToolImpactResult:
    """Factory for ToolImpactResult in tests."""
    return ToolImpactResult(
        task_id=task_id,
        condition=condition,
        tool_name=tool_name,
        resolved=resolved,
        tools_called=tools_called or [],
        call_count=call_count,
        token_usage=token_usage,
        duration_ms=duration_ms,
    )


def _make_ranking(
    tool_name: str = "tapps_score_file",
    impact_score: float = 0.1,
    tasks_helped: int = 5,
    tasks_hurt: int = 1,
    tasks_neutral: int = 14,
    avg_token_cost: int = 200,
    pass_at_k: float | None = 0.25,
) -> ToolRanking:
    """Factory for ToolRanking in tests."""
    return ToolRanking(
        tool_name=tool_name,
        impact_score=impact_score,
        tasks_helped=tasks_helped,
        tasks_hurt=tasks_hurt,
        tasks_neutral=tasks_neutral,
        avg_token_cost=avg_token_cost,
        pass_at_k=pass_at_k,
    )


def _make_task(
    task_id: str = "test-task",
    category: str = "quality",
    expected_tools: list[str] | None = None,
) -> ToolTask:
    """Factory for minimal ToolTask in tests."""
    return ToolTask(
        task_id=task_id,
        category=category,
        description="Test task.",
        setup_files={"test.py": "pass"},
        expected_tools=expected_tools or ["tapps_score_file"],
        verification=ToolTaskVerification(check_type="test_pass"),
        difficulty="easy",
    )


# ===========================================================================
# Story 32.1: ToolTask models and BUILTIN_TASKS
# ===========================================================================


class TestToolTaskVerification:
    """Tests for ToolTaskVerification model."""

    def test_basic_creation(self) -> None:
        v = ToolTaskVerification(check_type="file_content")
        assert v.check_type == "file_content"
        assert v.expected_file is None
        assert v.expected_content_patterns is None
        assert v.min_quality_score is None

    def test_all_fields(self) -> None:
        v = ToolTaskVerification(
            check_type="score_threshold",
            expected_file="test.py",
            expected_content_patterns=[r"def \w+"],
            min_quality_score=80.0,
            custom_verify="Custom check.",
        )
        assert v.min_quality_score == 80.0
        assert len(v.expected_content_patterns) == 1


class TestToolTask:
    """Tests for ToolTask model."""

    def test_basic_creation(self) -> None:
        task = _make_task()
        assert task.task_id == "test-task"
        assert task.category == "quality"
        assert task.difficulty == "easy"

    def test_frozen_model(self) -> None:
        task = _make_task()
        with pytest.raises(ValidationError):
            task.task_id = "changed"  # type: ignore[misc]


class TestToolTaskResult:
    """Tests for ToolTaskResult model."""

    def test_basic_creation(self) -> None:
        result = ToolTaskResult(
            task_id="task-1",
            condition="all_tools",
            resolved=True,
            tools_called=["tapps_score_file"],
            call_count=1,
            token_usage=1000,
            duration_ms=500,
        )
        assert result.resolved is True
        assert result.call_count == 1


class TestBuiltinTasks:
    """Tests for the BUILTIN_TASKS collection."""

    def test_has_minimum_tasks(self) -> None:
        assert len(BUILTIN_TASKS) >= 20

    def test_all_tasks_have_unique_ids(self) -> None:
        ids = [t.task_id for t in BUILTIN_TASKS]
        assert len(ids) == len(set(ids))

    def test_all_categories_covered(self) -> None:
        categories = {t.category for t in BUILTIN_TASKS}
        expected = {"quality", "security", "architecture", "debugging", "refactoring"}
        assert categories == expected

    def test_all_tasks_have_setup_files(self) -> None:
        for task in BUILTIN_TASKS:
            assert len(task.setup_files) > 0, f"Task {task.task_id} has no setup files"

    def test_all_tasks_have_expected_tools(self) -> None:
        for task in BUILTIN_TASKS:
            assert len(task.expected_tools) > 0, f"Task {task.task_id} has no expected tools"


# ===========================================================================
# Story 32.2: ToolImpactEvaluator and MockToolEvaluator
# ===========================================================================


class TestToolCondition:
    """Tests for ToolCondition enum."""

    def test_values(self) -> None:
        assert ToolCondition.ALL_TOOLS == "all_tools"
        assert ToolCondition.NO_TOOLS == "no_tools"
        assert ToolCondition.SINGLE_TOOL == "single_tool"
        assert ToolCondition.ALL_MINUS_ONE == "all_minus_one"

    def test_member_count(self) -> None:
        assert len(ToolCondition) == 4


class TestToolImpactResult:
    """Tests for ToolImpactResult model."""

    def test_creation(self) -> None:
        result = _make_impact_result()
        assert result.task_id == "test-task"
        assert result.condition == ToolCondition.ALL_TOOLS


class TestToolRanking:
    """Tests for ToolRanking model."""

    def test_creation(self) -> None:
        ranking = _make_ranking()
        assert ranking.tool_name == "tapps_score_file"
        assert ranking.impact_score == 0.1
        assert ranking.pass_at_k == 0.25


class TestMockToolEvaluator:
    """Tests for MockToolEvaluator."""

    @pytest.mark.asyncio()
    async def test_evaluate_task_deterministic(self) -> None:
        evaluator = MockToolEvaluator(seed=42)
        task = _make_task()
        result1 = await evaluator.evaluate_task(task, ["tapps_score_file"])

        evaluator2 = MockToolEvaluator(seed=42)
        result2 = await evaluator2.evaluate_task(task, ["tapps_score_file"])

        assert result1.resolved == result2.resolved

    @pytest.mark.asyncio()
    async def test_evaluate_task_tracks_calls(self) -> None:
        evaluator = MockToolEvaluator()
        task = _make_task()
        assert evaluator.call_count == 0
        await evaluator.evaluate_task(task, ["tapps_score_file"])
        assert evaluator.call_count == 1

    @pytest.mark.asyncio()
    async def test_more_tools_higher_resolution(self) -> None:
        """With more expected tools available, resolution should be more likely."""
        seed = 100
        task = _make_task(expected_tools=["tapps_score_file", "tapps_quick_check"])
        # Run many evaluations to check statistical tendency
        full_resolved = 0
        empty_resolved = 0
        trials = 50
        for i in range(trials):
            ev = MockToolEvaluator(seed=seed + i)
            r_full = await ev.evaluate_task(task, ["tapps_score_file", "tapps_quick_check"])
            ev2 = MockToolEvaluator(seed=seed + i)
            r_empty = await ev2.evaluate_task(task, [])
            full_resolved += int(r_full.resolved)
            empty_resolved += int(r_empty.resolved)
        # Full tools should resolve more often (higher probability)
        assert full_resolved >= empty_resolved


class TestToolImpactEvaluator:
    """Tests for ToolImpactEvaluator."""

    @pytest.mark.asyncio()
    async def test_evaluate_tool_impact_returns_paired_results(self) -> None:
        tasks = [_make_task(task_id=f"t-{i}") for i in range(3)]
        evaluator = ToolImpactEvaluator(tasks=tasks)
        mock = MockToolEvaluator()
        results = await evaluator.evaluate_tool_impact("tapps_score_file", mock)
        # Should have 2 results per task (ALL_TOOLS + ALL_MINUS_ONE)
        assert len(results) == 6

    @pytest.mark.asyncio()
    async def test_evaluate_tool_impact_conditions(self) -> None:
        tasks = [_make_task()]
        evaluator = ToolImpactEvaluator(tasks=tasks)
        mock = MockToolEvaluator()
        results = await evaluator.evaluate_tool_impact("tapps_score_file", mock)
        conditions = {r.condition for r in results}
        assert ToolCondition.ALL_TOOLS in conditions
        assert ToolCondition.ALL_MINUS_ONE in conditions

    @pytest.mark.asyncio()
    async def test_evaluate_all_tools_returns_report(self) -> None:
        tasks = [_make_task(task_id=f"t-{i}") for i in range(3)]
        evaluator = ToolImpactEvaluator(tasks=tasks)
        mock = MockToolEvaluator()
        report = await evaluator.evaluate_all_tools(
            ["tapps_score_file", "tapps_quick_check"],
            mock,
        )
        assert isinstance(report, ToolEffectivenessReport)
        assert report.task_count == 3
        assert len(report.tool_rankings) > 0

    @pytest.mark.asyncio()
    async def test_compute_ranking_sorts_by_impact(self) -> None:
        results = [
            _make_impact_result(
                task_id="t-1",
                condition=ToolCondition.ALL_TOOLS,
                tool_name="tool_a",
                resolved=True,
            ),
            _make_impact_result(
                task_id="t-1",
                condition=ToolCondition.ALL_MINUS_ONE,
                tool_name="tool_a",
                resolved=False,
            ),
            _make_impact_result(
                task_id="t-1",
                condition=ToolCondition.ALL_TOOLS,
                tool_name="tool_b",
                resolved=True,
            ),
            _make_impact_result(
                task_id="t-1",
                condition=ToolCondition.ALL_MINUS_ONE,
                tool_name="tool_b",
                resolved=True,
            ),
        ]
        evaluator = ToolImpactEvaluator(tasks=[])
        rankings = evaluator.compute_ranking(results)
        assert len(rankings) == 2
        # tool_a helped (resolved with, not without) -> higher impact
        assert rankings[0].tool_name == "tool_a"
        assert rankings[0].tasks_helped == 1

    def test_tasks_property(self) -> None:
        tasks = [_make_task(task_id="t-1"), _make_task(task_id="t-2")]
        evaluator = ToolImpactEvaluator(tasks=tasks)
        assert len(evaluator.tasks) == 2

    def test_default_tasks_are_builtin(self) -> None:
        evaluator = ToolImpactEvaluator()
        assert len(evaluator.tasks) == len(BUILTIN_TASKS)


# ===========================================================================
# Story 32.3: CallPatternAnalyzer
# ===========================================================================


class TestCallPattern:
    """Tests for CallPattern model."""

    def test_creation(self) -> None:
        pattern = CallPattern(
            task_id="t-1",
            tools_called=["tapps_score_file"],
            tools_expected=["tapps_score_file", "tapps_quick_check"],
            overcalls=[],
            undercalls=["tapps_quick_check"],
            call_efficiency=0.5,
        )
        assert pattern.call_efficiency == 0.5
        assert len(pattern.undercalls) == 1


class TestCallPatternAnalyzer:
    """Tests for CallPatternAnalyzer."""

    def test_analyze_basic(self) -> None:
        results = [
            _make_impact_result(
                task_id="t-1",
                condition=ToolCondition.ALL_TOOLS,
                tools_called=["tapps_score_file"],
            ),
        ]
        tasks = [
            _make_task(
                task_id="t-1",
                expected_tools=["tapps_score_file", "tapps_quick_check"],
            ),
        ]
        analyzer = CallPatternAnalyzer()
        report = analyzer.analyze(results, tasks)
        assert isinstance(report, CallPatternReport)
        assert len(report.patterns) == 1
        assert "tapps_quick_check" in report.patterns[0].undercalls

    def test_analyze_overcall_detection(self) -> None:
        results = [
            _make_impact_result(
                task_id="t-1",
                condition=ToolCondition.ALL_TOOLS,
                tools_called=["tapps_score_file", "tapps_memory"],
            ),
        ]
        tasks = [_make_task(task_id="t-1", expected_tools=["tapps_score_file"])]
        analyzer = CallPatternAnalyzer()
        report = analyzer.analyze(results, tasks)
        assert "tapps_memory" in report.patterns[0].overcalls

    def test_analyze_efficiency(self) -> None:
        results = [
            _make_impact_result(
                task_id="t-1",
                condition=ToolCondition.ALL_TOOLS,
                tools_called=["tapps_score_file", "tapps_quick_check"],
            ),
        ]
        tasks = [
            _make_task(task_id="t-1", expected_tools=["tapps_score_file"]),
        ]
        analyzer = CallPatternAnalyzer()
        report = analyzer.analyze(results, tasks)
        # 1 useful out of 2 called = 0.5
        assert report.patterns[0].call_efficiency == 0.5

    def test_generate_recommendations_keep(self) -> None:
        report = CallPatternReport(
            patterns=[
                CallPattern(
                    task_id="t-1",
                    tools_called=["tapps_score_file"],
                    tools_expected=["tapps_score_file"],
                    overcalls=[],
                    undercalls=[],
                    call_efficiency=1.0,
                ),
            ],
            avg_efficiency=1.0,
            most_overcalled=[],
            most_undercalled=[],
            common_sequences=[],
        )
        analyzer = CallPatternAnalyzer()
        recommendations = analyzer.generate_recommendations(report)
        assert len(recommendations) >= 1
        for rec in recommendations:
            assert isinstance(rec, CallRecommendation)

    def test_generate_recommendations_increase(self) -> None:
        report = CallPatternReport(
            patterns=[
                CallPattern(
                    task_id=f"t-{i}",
                    tools_called=[],
                    tools_expected=["tapps_score_file"],
                    overcalls=[],
                    undercalls=["tapps_score_file"],
                    call_efficiency=0.0,
                )
                for i in range(5)
            ],
            avg_efficiency=0.0,
            most_overcalled=[],
            most_undercalled=[("tapps_score_file", 5)],
            common_sequences=[],
        )
        analyzer = CallPatternAnalyzer()
        recommendations = analyzer.generate_recommendations(report)
        score_rec = next(
            (r for r in recommendations if r.tool_name == "tapps_score_file"),
            None,
        )
        assert score_rec is not None
        assert score_rec.recommendation == "increase"

    def test_skips_non_all_tools_results(self) -> None:
        results = [
            _make_impact_result(
                task_id="t-1",
                condition=ToolCondition.ALL_MINUS_ONE,
                tools_called=["tapps_score_file"],
            ),
        ]
        tasks = [_make_task(task_id="t-1")]
        analyzer = CallPatternAnalyzer()
        report = analyzer.analyze(results, tasks)
        assert len(report.patterns) == 0


# ===========================================================================
# Story 32.4: ChecklistCalibrator
# ===========================================================================


class TestToolTierClassification:
    """Tests for ToolTierClassification model."""

    def test_creation(self) -> None:
        classification = ToolTierClassification(
            tool_name="tapps_score_file",
            measured_impact=0.05,
            measured_cost=0.1,
            call_frequency=0.8,
            recommended_tier="required",
            current_tier="recommended",
            tier_change="promoted",
            justification="High impact, low cost.",
        )
        assert classification.recommended_tier == "required"
        assert classification.tier_change == "promoted"


class TestChecklistCalibrator:
    """Tests for ChecklistCalibrator."""

    def test_calibrate_required_tier(self) -> None:
        rankings = [_make_ranking(impact_score=0.05, avg_token_cost=100)]
        call_report = CallPatternReport(
            patterns=[
                CallPattern(
                    task_id="t-1",
                    tools_called=["tapps_score_file"],
                    tools_expected=["tapps_score_file"],
                    overcalls=[],
                    undercalls=[],
                    call_efficiency=1.0,
                ),
            ],
            avg_efficiency=1.0,
            most_overcalled=[],
            most_undercalled=[],
            common_sequences=[],
        )
        calibrator = ChecklistCalibrator()
        result = calibrator.calibrate_tiers(rankings, call_report, "medium")
        assert isinstance(result, ChecklistCalibration)
        assert len(result.classifications) == 1
        assert result.classifications[0].recommended_tier == "required"

    def test_calibrate_optional_tier(self) -> None:
        rankings = [_make_ranking(impact_score=-0.05, avg_token_cost=500)]
        call_report = CallPatternReport(
            patterns=[],
            avg_efficiency=0.0,
            most_overcalled=[],
            most_undercalled=[],
            common_sequences=[],
        )
        calibrator = ChecklistCalibrator()
        result = calibrator.calibrate_tiers(rankings, call_report, "medium")
        assert result.classifications[0].recommended_tier == "optional"

    def test_high_engagement_lower_threshold(self) -> None:
        """High engagement has a lower threshold (1%) so more tools are required."""
        rankings = [_make_ranking(impact_score=0.02, avg_token_cost=100)]
        call_report = CallPatternReport(
            patterns=[
                CallPattern(
                    task_id="t-1",
                    tools_called=["tapps_score_file"],
                    tools_expected=["tapps_score_file"],
                    overcalls=[],
                    undercalls=[],
                    call_efficiency=1.0,
                ),
            ],
            avg_efficiency=1.0,
            most_overcalled=[],
            most_undercalled=[],
            common_sequences=[],
        )
        calibrator = ChecklistCalibrator()

        high = calibrator.calibrate_tiers(rankings, call_report, "high")
        medium = calibrator.calibrate_tiers(rankings, call_report, "medium")

        # 2% impact: required at high (>1%) but recommended at medium (>3% needed)
        assert high.classifications[0].recommended_tier == "required"
        assert medium.classifications[0].recommended_tier == "recommended"

    def test_engagement_level_persisted(self) -> None:
        rankings = [_make_ranking()]
        call_report = CallPatternReport(
            patterns=[],
            avg_efficiency=0.0,
            most_overcalled=[],
            most_undercalled=[],
            common_sequences=[],
        )
        calibrator = ChecklistCalibrator()
        result = calibrator.calibrate_tiers(rankings, call_report, "low")
        assert result.engagement_level == "low"

    def test_tier_change_detection(self) -> None:
        rankings = [_make_ranking(impact_score=0.05, avg_token_cost=100)]
        call_report = CallPatternReport(
            patterns=[
                CallPattern(
                    task_id="t-1",
                    tools_called=["tapps_score_file"],
                    tools_expected=["tapps_score_file"],
                    overcalls=[],
                    undercalls=[],
                    call_efficiency=1.0,
                ),
            ],
            avg_efficiency=1.0,
            most_overcalled=[],
            most_undercalled=[],
            common_sequences=[],
        )
        calibrator = ChecklistCalibrator()
        result = calibrator.calibrate_tiers(rankings, call_report, "medium")
        # Current tier defaults to "recommended", recommended is "required"
        assert result.classifications[0].tier_change == "promoted"


# ===========================================================================
# Story 32.5: ExpertTracker and MemoryTracker
# ===========================================================================


class TestExpertEffectiveness:
    """Tests for ExpertEffectiveness model."""

    def test_creation(self) -> None:
        eff = ExpertEffectiveness(
            domain="security",
            consultations=10,
            resolution_with=0.8,
            resolution_without=0.5,
            impact=0.3,
            avg_confidence=0.7,
        )
        assert eff.impact == 0.3


class TestExpertEffectivenessAnalyzer:
    """Tests for ExpertEffectivenessAnalyzer."""

    def test_analyze_basic(self) -> None:
        results = [
            _make_impact_result(
                task_id="t-1",
                condition=ToolCondition.ALL_TOOLS,
                resolved=True,
                tools_called=["tapps_consult_expert"],
            ),
            _make_impact_result(
                task_id="t-1",
                condition=ToolCondition.ALL_MINUS_ONE,
                tool_name="tapps_consult_expert",
                resolved=False,
            ),
        ]
        tasks = [_make_task(task_id="t-1", category="security")]
        analyzer = ExpertEffectivenessAnalyzer()
        report = analyzer.analyze(results, tasks)
        assert isinstance(report, ExpertEffectivenessReport)
        assert len(report.per_domain) > 0
        assert report.most_effective_domain != ""

    def test_analyze_multiple_categories(self) -> None:
        results = []
        tasks = []
        for i, category in enumerate(["security", "quality", "architecture"]):
            tid = f"t-{i}"
            results.append(
                _make_impact_result(
                    task_id=tid,
                    condition=ToolCondition.ALL_TOOLS,
                    resolved=True,
                    tools_called=["tapps_consult_expert"],
                ),
            )
            tasks.append(_make_task(task_id=tid, category=category))

        analyzer = ExpertEffectivenessAnalyzer()
        report = analyzer.analyze(results, tasks)
        domains = {e.domain for e in report.per_domain}
        assert len(domains) >= 2

    def test_analyze_empty_results(self) -> None:
        analyzer = ExpertEffectivenessAnalyzer()
        report = analyzer.analyze([], [])
        assert report.most_effective_domain == "none"
        assert report.least_effective_domain == "none"

    def test_report_sorted_by_impact(self) -> None:
        results = [
            _make_impact_result(
                task_id="t-sec",
                condition=ToolCondition.ALL_TOOLS,
                resolved=True,
                tools_called=["tapps_consult_expert"],
            ),
            _make_impact_result(
                task_id="t-qual",
                condition=ToolCondition.ALL_TOOLS,
                resolved=False,
                tools_called=["tapps_consult_expert"],
            ),
        ]
        tasks = [
            _make_task(task_id="t-sec", category="security"),
            _make_task(task_id="t-qual", category="quality"),
        ]
        analyzer = ExpertEffectivenessAnalyzer()
        report = analyzer.analyze(results, tasks)
        # Sorted by impact descending
        if len(report.per_domain) >= 2:
            assert report.per_domain[0].impact >= report.per_domain[-1].impact


class TestMemoryEffectiveness:
    """Tests for MemoryEffectiveness model."""

    def test_creation(self) -> None:
        eff = MemoryEffectiveness(
            memory_tier="architectural",
            retrievals=5,
            resolution_with=0.9,
            resolution_without=0.6,
            impact=0.3,
            relevance_score=0.85,
        )
        assert eff.memory_tier == "architectural"


class TestMemoryEffectivenessAnalyzer:
    """Tests for MemoryEffectivenessAnalyzer."""

    def test_analyze_basic(self) -> None:
        results = [
            _make_impact_result(
                task_id="t-1",
                condition=ToolCondition.ALL_TOOLS,
                resolved=True,
            ),
            _make_impact_result(
                task_id="t-1",
                condition=ToolCondition.ALL_MINUS_ONE,
                tool_name="tapps_memory",
                resolved=False,
            ),
        ]
        analyzer = MemoryEffectivenessAnalyzer()
        report = analyzer.analyze(results)
        assert isinstance(report, MemoryEffectivenessReport)
        assert report.most_effective_tier in {"architectural", "pattern", "procedural", "context"}

    def test_analyze_empty_results(self) -> None:
        analyzer = MemoryEffectivenessAnalyzer()
        report = analyzer.analyze([])
        assert len(report.per_tier) == 4  # Epic 65.11: procedural added
        assert report.most_effective_tier in {"architectural", "pattern", "procedural", "context"}

    def test_tier_assignment_deterministic(self) -> None:
        analyzer = MemoryEffectivenessAnalyzer()
        tier1 = analyzer._assign_tier("task-abc")
        tier2 = analyzer._assign_tier("task-abc")
        assert tier1 == tier2

    def test_relevance_scores_bounded(self) -> None:
        analyzer = MemoryEffectivenessAnalyzer()
        for tier in ["architectural", "pattern", "procedural", "context"]:
            score = analyzer._estimate_relevance(tier, 100)
            assert 0.0 <= score <= 1.0


# ===========================================================================
# Story 32.6: AdaptiveFeedbackGenerator
# ===========================================================================


class TestBenchmarkFeedback:
    """Tests for BenchmarkFeedback model."""

    def test_creation(self) -> None:
        fb = BenchmarkFeedback(
            tool_name="tapps_score_file",
            impact_score=0.1,
            cost_ratio=0.05,
            category_impacts={"complexity": 0.05, "maintainability": 0.05},
            sample_size=20,
            confidence=0.8,
        )
        assert fb.source == "benchmark"
        assert len(fb.category_impacts) == 2


class TestAdaptiveFeedbackGenerator:
    """Tests for AdaptiveFeedbackGenerator."""

    def test_generate_feedback_basic(self) -> None:
        rankings = [
            _make_ranking(
                tool_name="tapps_score_file",
                impact_score=0.1,
                tasks_helped=5,
                tasks_hurt=1,
                tasks_neutral=14,
            ),
        ]
        report = ToolEffectivenessReport(
            tool_rankings=rankings,
            task_count=20,
            condition_count=40,
        )
        generator = AdaptiveFeedbackGenerator()
        feedback = generator.generate_feedback(report)
        assert len(feedback) == 1
        assert feedback[0].tool_name == "tapps_score_file"
        assert feedback[0].confidence > 0

    def test_generate_feedback_skips_low_confidence(self) -> None:
        rankings = [
            _make_ranking(
                tool_name="tapps_score_file",
                tasks_helped=0,
                tasks_hurt=0,
                tasks_neutral=1,
            ),
        ]
        report = ToolEffectivenessReport(
            tool_rankings=rankings,
            task_count=1,
            condition_count=2,
        )
        generator = AdaptiveFeedbackGenerator()
        feedback = generator.generate_feedback(report)
        # 1 task -> confidence = 1/(1+5) = 0.167 < 0.3 threshold
        assert len(feedback) == 0

    def test_generate_weight_adjustments(self) -> None:
        feedback = [
            BenchmarkFeedback(
                tool_name="tapps_score_file",
                impact_score=0.1,
                cost_ratio=0.05,
                category_impacts={"complexity": 0.05, "maintainability": 0.05},
                sample_size=20,
                confidence=0.8,
            ),
        ]
        generator = AdaptiveFeedbackGenerator()
        adjustments = generator.generate_weight_adjustments(feedback)
        assert isinstance(adjustments, dict)
        # Should have entries for standard categories
        assert "complexity" in adjustments
        assert "security" in adjustments

    def test_weight_adjustments_sum_near_zero(self) -> None:
        feedback = [
            BenchmarkFeedback(
                tool_name="tapps_security_scan",
                impact_score=0.2,
                cost_ratio=0.03,
                category_impacts={"security": 0.2},
                sample_size=20,
                confidence=0.9,
            ),
            BenchmarkFeedback(
                tool_name="tapps_score_file",
                impact_score=0.1,
                cost_ratio=0.05,
                category_impacts={"complexity": 0.05, "maintainability": 0.05},
                sample_size=20,
                confidence=0.8,
            ),
        ]
        generator = AdaptiveFeedbackGenerator()
        adjustments = generator.generate_weight_adjustments(feedback)
        total = sum(adjustments.values())
        assert abs(total) < 0.001


# ===========================================================================
# Story 32.7: ToolEffectivenessSection and report generation
# ===========================================================================


class TestToolEffectivenessSection:
    """Tests for ToolEffectivenessSection model."""

    def test_creation(self) -> None:
        section = ToolEffectivenessSection(
            tool_rankings=[_make_ranking()],
            call_efficiency=0.85,
            calibration_pending=False,
        )
        assert len(section.tool_rankings) == 1
        assert section.call_efficiency == 0.85


class TestToolReport:
    """Tests for report generation."""

    def _make_reports(self) -> tuple[ToolEffectivenessReport, CallPatternReport]:
        """Create test report data."""
        tool_report = ToolEffectivenessReport(
            tool_rankings=[
                _make_ranking(tool_name="tapps_score_file", impact_score=0.15),
                _make_ranking(tool_name="tapps_security_scan", impact_score=0.10),
                _make_ranking(tool_name="tapps_dead_code", impact_score=-0.02),
            ],
            task_count=20,
            condition_count=120,
        )
        call_report = CallPatternReport(
            patterns=[],
            avg_efficiency=0.75,
            most_overcalled=[("tapps_memory", 5)],
            most_undercalled=[("tapps_security_scan", 3)],
            common_sequences=[],
        )
        return tool_report, call_report

    def test_markdown_report_format(self) -> None:
        tool_report, call_report = self._make_reports()
        report = generate_tool_effectiveness_report(tool_report, call_report, "markdown")
        assert "# Tool Effectiveness Report" in report
        assert "tapps_score_file" in report
        assert "tapps_security_scan" in report

    def test_json_report_format(self) -> None:
        tool_report, call_report = self._make_reports()
        report = generate_tool_effectiveness_report(tool_report, call_report, "json")
        data = json.loads(report)
        assert "summary" in data
        assert "tool_rankings" in data
        assert data["summary"]["task_count"] == 20

    def test_markdown_includes_rankings_table(self) -> None:
        tool_report, call_report = self._make_reports()
        report = generate_tool_effectiveness_report(tool_report, call_report, "markdown")
        assert "| Rank |" in report
        assert "| 1 |" in report

    def test_markdown_includes_high_impact_section(self) -> None:
        tool_report, call_report = self._make_reports()
        report = generate_tool_effectiveness_report(tool_report, call_report, "markdown")
        assert "High-Impact Tools" in report


# ===========================================================================
# CLI integration (smoke test)
# ===========================================================================


class TestToolsCLI:
    """Smoke tests for the tools CLI commands."""

    def test_tools_group_exists(self) -> None:
        from tapps_mcp.benchmark.cli_commands import tools_group

        assert tools_group is not None
        assert tools_group.name == "tools"

    def test_tools_report_command_registered(self) -> None:
        from tapps_mcp.benchmark.cli_commands import tools_group

        commands = set(tools_group.commands)
        assert "report" in commands

    def test_tools_rank_command_registered(self) -> None:
        from tapps_mcp.benchmark.cli_commands import tools_group

        commands = set(tools_group.commands)
        assert "rank" in commands

    def test_tools_calibrate_command_registered(self) -> None:
        from tapps_mcp.benchmark.cli_commands import tools_group

        commands = set(tools_group.commands)
        assert "calibrate" in commands

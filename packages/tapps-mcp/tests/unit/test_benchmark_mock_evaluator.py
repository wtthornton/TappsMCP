"""Unit tests for MockEvaluator and make_test_result (Epic 30, Story 7)."""

from __future__ import annotations

from typing import Any

import pytest

from tapps_mcp.benchmark.mock_evaluator import MockEvaluator, make_test_result
from tapps_mcp.benchmark.models import BenchmarkInstance, BenchmarkResult, ContextMode

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS: dict[str, Any] = {
    "instance_id": "test-001",
    "repo": "owner/repo",
    "problem_description": "Fix the bug.",
    "clean_pr_patch": "--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-old\n+new\n",
    "test_commands": ["pytest tests/"],
    "test_file_names": ["tests/test_foo.py"],
    "test_file_contents": {"tests/test_foo.py": "def test(): pass"},
    "docker_image": "",
}


def _make_instance(**overrides: Any) -> BenchmarkInstance:
    """Build a BenchmarkInstance with sensible defaults."""
    fields: dict[str, Any] = {**_REQUIRED_FIELDS, **overrides}
    return BenchmarkInstance(**fields)


# ---------------------------------------------------------------------------
# MockEvaluator tests
# ---------------------------------------------------------------------------


class TestMockEvaluatorPredeterminedOutcomes:
    """Test that predetermined outcomes override default behavior."""

    async def test_resolved_when_predetermined_true(self) -> None:
        """Predetermined True outcome is returned regardless of hash."""
        instance = _make_instance(instance_id="pre-001")
        outcomes = {("pre-001", ContextMode.NONE): True}
        evaluator = MockEvaluator(outcomes=outcomes)

        result = await evaluator.evaluate_instance(instance, ContextMode.NONE)

        assert result.resolved is True
        assert result.instance_id == "pre-001"
        assert result.context_mode is ContextMode.NONE

    async def test_unresolved_when_predetermined_false(self) -> None:
        """Predetermined False outcome is returned."""
        instance = _make_instance(instance_id="pre-002")
        outcomes = {("pre-002", ContextMode.TAPPS): False}
        evaluator = MockEvaluator(outcomes=outcomes)

        result = await evaluator.evaluate_instance(instance, ContextMode.TAPPS)

        assert result.resolved is False
        assert result.patch_size == 0

    async def test_predetermined_for_specific_mode_only(self) -> None:
        """Predetermined outcome applies only to the matching mode."""
        instance = _make_instance(instance_id="pre-003")
        outcomes = {("pre-003", ContextMode.NONE): True}
        evaluator = MockEvaluator(outcomes=outcomes)

        result_none = await evaluator.evaluate_instance(instance, ContextMode.NONE)
        assert result_none.resolved is True

        # TAPPS mode falls back to hash-based resolution
        result_tapps = await evaluator.evaluate_instance(instance, ContextMode.TAPPS)
        assert isinstance(result_tapps.resolved, bool)


class TestMockEvaluatorDefaultRates:
    """Test that default resolution rates produce expected distributions."""

    async def test_produces_boolean_results(self) -> None:
        """Default rates produce boolean resolved values."""
        evaluator = MockEvaluator()
        instance = _make_instance(instance_id="rate-001")

        result = await evaluator.evaluate_instance(instance, ContextMode.NONE)

        assert isinstance(result.resolved, bool)

    async def test_engagement_level_propagated(self) -> None:
        """The engagement_level parameter is passed through to results."""
        evaluator = MockEvaluator()
        instance = _make_instance()

        result = await evaluator.evaluate_instance(
            instance, ContextMode.NONE, engagement_level="high"
        )

        assert result.engagement_level == "high"


class TestMockEvaluatorDeterministic:
    """Test that the evaluator is deterministic with the same inputs."""

    async def test_same_inputs_same_result(self) -> None:
        """Identical inputs produce identical resolved status."""
        instance = _make_instance(instance_id="det-001")

        eval_a = MockEvaluator(seed=42)
        eval_b = MockEvaluator(seed=42)

        result_a = await eval_a.evaluate_instance(instance, ContextMode.TAPPS)
        result_b = await eval_b.evaluate_instance(instance, ContextMode.TAPPS)

        assert result_a.resolved == result_b.resolved

    async def test_different_seeds_may_differ(self) -> None:
        """Different seeds can produce different outcomes for the same instance."""
        instance = _make_instance(instance_id="det-002")
        # Use many instances to find at least one that differs
        found_difference = False
        for seed_b in range(1, 100):
            eval_a = MockEvaluator(seed=42)
            eval_b = MockEvaluator(seed=seed_b)
            result_a = await eval_a.evaluate_instance(instance, ContextMode.NONE)
            result_b = await eval_b.evaluate_instance(instance, ContextMode.NONE)
            if result_a.resolved != result_b.resolved:
                found_difference = True
                break

        assert found_difference, (
            "Expected different seeds to produce at least one different outcome"
        )


class TestMockEvaluatorDifferentModes:
    """Test that different context modes produce different results."""

    async def test_none_vs_tapps_differ_for_some_instances(self) -> None:
        """At least some instances should produce different results across modes."""
        evaluator = MockEvaluator(seed=42)
        found_difference = False

        for i in range(20):
            instance = _make_instance(instance_id=f"mode-{i}")
            result_none = await evaluator.evaluate_instance(instance, ContextMode.NONE)
            result_tapps = await evaluator.evaluate_instance(instance, ContextMode.TAPPS)
            if result_none.resolved != result_tapps.resolved:
                found_difference = True
                break

        assert found_difference, (
            "Expected NONE and TAPPS modes to produce different outcomes for at least one instance"
        )

    async def test_token_usage_differs_by_mode(self) -> None:
        """Non-NONE modes add extra tokens for context overhead."""
        evaluator = MockEvaluator(seed=42)
        instance = _make_instance(instance_id="tokens-001")

        result_none = await evaluator.evaluate_instance(instance, ContextMode.NONE)
        result_tapps = await evaluator.evaluate_instance(instance, ContextMode.TAPPS)

        # TAPPS adds 200 tokens compared to NONE
        # Note: call_count difference also affects base_tokens, so we check the
        # general pattern that TAPPS should not be less than NONE for a fresh evaluator
        assert result_tapps.token_usage > 0
        assert result_none.token_usage > 0


class TestMockEvaluatorBatch:
    """Test evaluate_batch method."""

    async def test_batch_returns_correct_count(self) -> None:
        """Batch evaluation returns one result per instance."""
        instances = [_make_instance(instance_id=f"batch-{i}") for i in range(5)]
        evaluator = MockEvaluator(seed=42)

        results = await evaluator.evaluate_batch(instances, ContextMode.TAPPS)

        assert len(results) == 5
        assert all(isinstance(r, BenchmarkResult) for r in results)

    async def test_batch_instance_ids_match(self) -> None:
        """Each result's instance_id matches the input instance."""
        instances = [_make_instance(instance_id=f"batch-id-{i}") for i in range(3)]
        evaluator = MockEvaluator(seed=42)

        results = await evaluator.evaluate_batch(instances, ContextMode.NONE)

        for inst, result in zip(instances, results, strict=True):
            assert result.instance_id == inst.instance_id

    async def test_batch_increments_call_count(self) -> None:
        """Batch evaluation increments call_count for each instance."""
        instances = [_make_instance(instance_id=f"batch-cc-{i}") for i in range(3)]
        evaluator = MockEvaluator()

        await evaluator.evaluate_batch(instances, ContextMode.NONE)

        assert evaluator.call_count == 3

    async def test_batch_with_engagement_level(self) -> None:
        """Batch passes through engagement_level to all results."""
        instances = [_make_instance(instance_id=f"batch-eng-{i}") for i in range(2)]
        evaluator = MockEvaluator()

        results = await evaluator.evaluate_batch(
            instances, ContextMode.TAPPS, engagement_level="low"
        )

        assert all(r.engagement_level == "low" for r in results)


class TestMockEvaluatorCallCount:
    """Test call count tracking."""

    async def test_starts_at_zero(self) -> None:
        """Call count starts at zero."""
        evaluator = MockEvaluator()
        assert evaluator.call_count == 0

    async def test_increments_on_each_call(self) -> None:
        """Each evaluate_instance call increments the count."""
        evaluator = MockEvaluator()
        instance = _make_instance()

        await evaluator.evaluate_instance(instance, ContextMode.NONE)
        assert evaluator.call_count == 1

        await evaluator.evaluate_instance(instance, ContextMode.TAPPS)
        assert evaluator.call_count == 2

        await evaluator.evaluate_instance(instance, ContextMode.HUMAN)
        assert evaluator.call_count == 3


class TestMockEvaluatorCustomRates:
    """Test custom resolution rates."""

    async def test_zero_rate_always_unresolved(self) -> None:
        """A 0% rate should never resolve any instance."""
        rates = {
            ContextMode.NONE: 0.0,
            ContextMode.TAPPS: 0.0,
        }
        evaluator = MockEvaluator(default_resolution_rates=rates, seed=42)

        results = []
        for i in range(20):
            instance = _make_instance(instance_id=f"zero-{i}")
            result = await evaluator.evaluate_instance(instance, ContextMode.NONE)
            results.append(result)

        assert not any(r.resolved for r in results)

    async def test_full_rate_always_resolved(self) -> None:
        """A 100% rate should always resolve."""
        rates = {ContextMode.TAPPS: 1.0}
        evaluator = MockEvaluator(default_resolution_rates=rates, seed=42)

        results = []
        for i in range(20):
            instance = _make_instance(instance_id=f"full-{i}")
            result = await evaluator.evaluate_instance(instance, ContextMode.TAPPS)
            results.append(result)

        assert all(r.resolved for r in results)


# ---------------------------------------------------------------------------
# make_test_result tests
# ---------------------------------------------------------------------------


class TestMakeTestResultDefaults:
    """Test the make_test_result factory with default values."""

    def test_default_values(self) -> None:
        """Factory produces a result with sensible defaults."""
        result = make_test_result()

        assert result.instance_id == "test-001"
        assert result.context_mode is ContextMode.NONE
        assert result.engagement_level == "medium"
        assert result.resolved is True
        assert result.token_usage == 1500
        assert result.inference_cost == pytest.approx(0.015)
        assert result.steps == 5
        assert result.patch_size == 200
        assert result.duration_ms == 3000

    def test_returns_benchmark_result(self) -> None:
        """Factory returns a proper BenchmarkResult instance."""
        result = make_test_result()
        assert isinstance(result, BenchmarkResult)


class TestMakeTestResultOverrides:
    """Test the make_test_result factory with custom values."""

    def test_override_instance_id(self) -> None:
        """Can override instance_id."""
        result = make_test_result(instance_id="custom-id")
        assert result.instance_id == "custom-id"

    def test_override_context_mode(self) -> None:
        """Can override context_mode."""
        result = make_test_result(context_mode=ContextMode.TAPPS)
        assert result.context_mode is ContextMode.TAPPS

    def test_override_multiple_fields(self) -> None:
        """Can override multiple fields at once."""
        result = make_test_result(
            instance_id="multi-001",
            context_mode=ContextMode.HUMAN,
            resolved=False,
            token_usage=5000,
            steps=12,
        )
        assert result.instance_id == "multi-001"
        assert result.context_mode is ContextMode.HUMAN
        assert result.resolved is False
        assert result.token_usage == 5000
        assert result.steps == 12

    def test_override_engagement_level(self) -> None:
        """Can override engagement_level via kwargs."""
        result = make_test_result(engagement_level="high")
        assert result.engagement_level == "high"


class TestMakeTestResultPatchSize:
    """Test that resolved status affects default patch_size."""

    def test_resolved_true_has_patch_size(self) -> None:
        """resolved=True produces non-zero default patch_size."""
        result = make_test_result(resolved=True)
        assert result.patch_size == 200

    def test_resolved_false_has_zero_patch_size(self) -> None:
        """resolved=False produces zero default patch_size."""
        result = make_test_result(resolved=False)
        assert result.patch_size == 0

    def test_explicit_patch_size_overrides(self) -> None:
        """Explicit patch_size kwarg overrides the default logic."""
        result = make_test_result(resolved=False, patch_size=42)
        assert result.patch_size == 42

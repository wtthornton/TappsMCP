"""Tests for scoring.constants."""

import math

from tapps_mcp.scoring.constants import (
    COMPLEXITY_SCALING_FACTOR,
    DEEP_NESTING_THRESHOLD,
    INDIVIDUAL_MAX,
    INDIVIDUAL_MIN,
    INSECURE_PATTERN_PENALTY,
    LARGE_FUNCTION_LINES,
    MAX_EXPECTED_COMPLEXITY,
    MYPY_ERROR_PENALTY,
    OVERALL_MAX,
    OVERALL_MIN,
    PERFORMANCE_PENALTY_MAP,
    RUFF_ERROR_PENALTY,
    RUFF_FATAL_PENALTY,
    RUFF_WARNING_PENALTY,
    VERY_DEEP_NESTING_THRESHOLD,
    VERY_LARGE_FUNCTION_LINES,
    clamp_individual,
    clamp_overall,
)


class TestConstants:
    def test_individual_bounds(self):
        assert INDIVIDUAL_MIN == 0.0
        assert INDIVIDUAL_MAX == 10.0

    def test_overall_bounds(self):
        assert OVERALL_MIN == 0.0
        assert OVERALL_MAX == 100.0

    def test_complexity_scaling(self):
        assert COMPLEXITY_SCALING_FACTOR == MAX_EXPECTED_COMPLEXITY / 10.0
        assert COMPLEXITY_SCALING_FACTOR == 5.0

    def test_ruff_penalties_ordered(self):
        assert RUFF_FATAL_PENALTY > RUFF_ERROR_PENALTY > RUFF_WARNING_PENALTY

    def test_function_line_thresholds_ordered(self):
        assert VERY_LARGE_FUNCTION_LINES > LARGE_FUNCTION_LINES

    def test_nesting_thresholds_ordered(self):
        assert VERY_DEEP_NESTING_THRESHOLD > DEEP_NESTING_THRESHOLD

    def test_performance_penalty_map_keys(self):
        expected_keys = {
            # AST heuristics
            "large_function",
            "very_large_function",
            "deep_nesting",
            "very_deep_nesting",
            "nested_loops",
            "expensive_comprehension",
            # Halstead metrics
            "halstead_high_volume",
            "halstead_very_high_volume",
            "halstead_high_difficulty",
            "halstead_high_effort",
            "halstead_high_bugs",
            # Perflint anti-patterns
            "perflint_loop_invariant",
            "perflint_dotted_import_in_loop",
            "perflint_unnecessary_list_cast",
            "perflint_incorrect_dict_iterator",
            "perflint_loop_global_usage",
            "perflint_memoryview_over_bytes",
            "perflint_use_tuple_over_list",
            "perflint_use_comprehension",
        }
        assert set(PERFORMANCE_PENALTY_MAP.keys()) == expected_keys

    def test_performance_penalties_positive(self):
        for penalty in PERFORMANCE_PENALTY_MAP.values():
            assert penalty > 0

    def test_insecure_pattern_penalty_positive(self):
        assert INSECURE_PATTERN_PENALTY > 0

    def test_mypy_penalty_positive(self):
        assert MYPY_ERROR_PENALTY > 0


class TestClampIndividual:
    def test_within_range(self):
        assert clamp_individual(5.0) == 5.0

    def test_at_min(self):
        assert clamp_individual(0.0) == 0.0

    def test_at_max(self):
        assert clamp_individual(10.0) == 10.0

    def test_below_min(self):
        assert clamp_individual(-5.0) == 0.0

    def test_above_max(self):
        assert clamp_individual(15.0) == 10.0

    def test_nan(self):
        assert clamp_individual(float("nan")) == 5.0

    def test_positive_inf(self):
        assert clamp_individual(float("inf")) == 5.0

    def test_negative_inf(self):
        assert clamp_individual(float("-inf")) == 5.0

    def test_returns_float(self):
        result = clamp_individual(7.5)
        assert isinstance(result, float)


class TestClampOverall:
    def test_within_range(self):
        assert clamp_overall(50.0) == 50.0

    def test_at_min(self):
        assert clamp_overall(0.0) == 0.0

    def test_at_max(self):
        assert clamp_overall(100.0) == 100.0

    def test_below_min(self):
        assert clamp_overall(-10.0) == 0.0

    def test_above_max(self):
        assert clamp_overall(150.0) == 100.0

    def test_nan(self):
        assert clamp_overall(float("nan")) == 50.0

    def test_positive_inf(self):
        assert clamp_overall(math.inf) == 50.0

    def test_negative_inf(self):
        assert clamp_overall(-math.inf) == 50.0

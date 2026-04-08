"""Score constants and normalisation utilities."""

from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# Scale boundaries
# ---------------------------------------------------------------------------
INDIVIDUAL_MIN: float = 0.0
INDIVIDUAL_MAX: float = 10.0
OVERALL_MIN: float = 0.0
OVERALL_MAX: float = 100.0

# ---------------------------------------------------------------------------
# Complexity constants
# ---------------------------------------------------------------------------
MAX_EXPECTED_COMPLEXITY: float = 50.0
COMPLEXITY_SCALING_FACTOR: float = MAX_EXPECTED_COMPLEXITY / 10.0  # 5.0

# ---------------------------------------------------------------------------
# Security constants
# ---------------------------------------------------------------------------
INSECURE_PATTERN_PENALTY: float = 2.0

# ---------------------------------------------------------------------------
# Linting scoring weights
# ---------------------------------------------------------------------------
RUFF_ERROR_PENALTY: float = 2.0
RUFF_FATAL_PENALTY: float = 3.0
RUFF_WARNING_PENALTY: float = 0.5

# ---------------------------------------------------------------------------
# mypy scoring
# ---------------------------------------------------------------------------
MYPY_ERROR_PENALTY: float = 0.5

# ---------------------------------------------------------------------------
# Performance analysis thresholds
# ---------------------------------------------------------------------------
LARGE_FUNCTION_LINES: int = 50
VERY_LARGE_FUNCTION_LINES: int = 100
DEEP_NESTING_THRESHOLD: int = 4
VERY_DEEP_NESTING_THRESHOLD: int = 6

# Halstead metrics thresholds (per-function)
HALSTEAD_HIGH_VOLUME: float = 1500.0
HALSTEAD_VERY_HIGH_VOLUME: float = 3000.0
HALSTEAD_HIGH_DIFFICULTY: float = 30.0
HALSTEAD_HIGH_EFFORT: float = 100000.0
HALSTEAD_HIGH_BUGS: float = 1.0

# Maximum total penalty contribution from perflint findings
PERFLINT_PENALTY_CAP: float = 3.0

PERFORMANCE_PENALTY_MAP: dict[str, float] = {
    # AST heuristics
    "large_function": 0.5,
    "very_large_function": 1.5,
    "deep_nesting": 1.0,
    "very_deep_nesting": 2.0,
    "nested_loops": 1.5,
    "expensive_comprehension": 0.5,
    # Halstead metrics
    "halstead_high_volume": 0.5,
    "halstead_very_high_volume": 1.0,
    "halstead_high_difficulty": 0.8,
    "halstead_high_effort": 0.5,
    "halstead_high_bugs": 1.0,
    # Perflint anti-patterns
    "perflint_loop_invariant": 0.8,
    "perflint_dotted_import_in_loop": 0.5,
    "perflint_unnecessary_list_cast": 0.3,
    "perflint_incorrect_dict_iterator": 0.5,
    "perflint_loop_global_usage": 0.5,
    "perflint_memoryview_over_bytes": 0.3,
    "perflint_use_tuple_over_list": 0.2,
    "perflint_use_comprehension": 0.3,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def clamp_individual(score: float) -> float:
    """Clamp a 0-10 category score."""
    if math.isnan(score) or math.isinf(score):
        return 5.0
    return max(INDIVIDUAL_MIN, min(INDIVIDUAL_MAX, score))


def clamp_overall(score: float) -> float:
    """Clamp a 0-100 overall score."""
    if math.isnan(score) or math.isinf(score):
        return 50.0
    return max(OVERALL_MIN, min(OVERALL_MAX, score))

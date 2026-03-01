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

PERFORMANCE_PENALTY_MAP: dict[str, float] = {
    "large_function": 0.5,
    "very_large_function": 1.5,
    "deep_nesting": 1.0,
    "very_deep_nesting": 2.0,
    "nested_loops": 1.5,
    "expensive_comprehension": 0.5,
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

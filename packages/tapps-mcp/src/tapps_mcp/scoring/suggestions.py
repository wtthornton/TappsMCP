"""Actionable suggestions for each scoring category.

Extracted from ``scorer.py`` to reduce file size and improve maintainability.
"""

from __future__ import annotations

from tapps_mcp.scoring.constants import (
    DEEP_NESTING_THRESHOLD,
    LARGE_FUNCTION_LINES,
    VERY_DEEP_NESTING_THRESHOLD,
    VERY_LARGE_FUNCTION_LINES,
)

# Thresholds for suggestion generation
_CC_HIGH = 10
_CC_MODERATE = 5
_MI_VERY_LOW = 20
_MI_LOW = 40
_FILE_LONG_LINES = 300
_SCORE_LOW = 5


def suggest_complexity(
    score: float,
    details: dict[str, object],
    using_radon: bool,
) -> list[str]:
    """Actionable suggestions for the complexity category."""
    tips: list[str] = []
    if not using_radon:
        tips.append("Install radon for accurate complexity measurement (pip install radon).")
        return tips
    if not isinstance(details, dict):
        return tips
    max_cc = float(str(details.get("max_cc", 0)))
    func_name = str(details.get("max_cc_function", ""))
    if max_cc > _CC_HIGH:
        tips.append(
            f"Function '{func_name}' has CC={int(max_cc)}. "
            f"Extract branches into helper functions to reduce below {_CC_HIGH}."
        )
    elif max_cc > _CC_MODERATE:
        tips.append(
            f"Function '{func_name}' has CC={int(max_cc)}. Consider simplifying conditional logic."
        )
    return tips


def suggest_security(
    score: float,
    details: dict[str, object],
) -> list[str]:
    """Actionable suggestions for the security category."""
    tips: list[str] = []
    if not isinstance(details, dict):
        return tips
    issue_count = int(str(details.get("issue_count", 0)))
    if issue_count > 0:
        tips.append(f"Found {issue_count} security issue(s). Run tapps_security_scan for details.")
    patterns = details.get("patterns_found")
    if isinstance(patterns, list) and patterns:
        joined = ", ".join(str(p) for p in patterns)
        tips.append(f"Avoid insecure patterns: {joined} - use safer alternatives.")
    return tips


def suggest_maintainability(
    score: float,
    details: dict[str, object],
) -> list[str]:
    """Actionable suggestions for the maintainability category."""
    tips: list[str] = []
    if not isinstance(details, dict):
        return tips
    mi = float(str(details.get("mi_value", 100)))
    if mi < _MI_VERY_LOW:
        tips.append(f"MI={mi:.0f} (very low). Split this file into smaller modules.")
    elif mi < _MI_LOW:
        tips.append(f"MI={mi:.0f} (low). Add docstrings and reduce function sizes.")
    if not details.get("has_docstring"):
        tips.append("Add module and function docstrings to improve maintainability.")
    line_count = int(str(details.get("line_count", 0)))
    if line_count > _FILE_LONG_LINES:
        tips.append(f"File has {line_count} lines. Consider splitting into smaller modules.")
    return tips


def suggest_test_coverage(
    score: float,
    details: dict[str, object],
) -> list[str]:
    """Actionable suggestions for the test_coverage category."""
    tips: list[str] = []
    if not isinstance(details, dict):
        return tips
    stem = str(details.get("stem", "module"))
    is_test = bool(details.get("is_test_file"))
    if score == 0:
        tips.append(f"No test file found. Create tests/unit/test_{stem}.py.")
    elif is_test and score <= _SCORE_LOW:
        tips.append("This is a test file (coverage score capped at 5/10).")
    return tips


_PERFORMANCE_SUGGESTIONS: dict[str, str] = {
    "very_large_function": (
        f"Function exceeds {VERY_LARGE_FUNCTION_LINES} lines. "
        "Decompose into smaller functions."
    ),
    "large_function": (
        f"Function exceeds {LARGE_FUNCTION_LINES} lines. Consider breaking it up."
    ),
    "very_deep_nesting": (
        f"Nesting depth > {VERY_DEEP_NESTING_THRESHOLD}. "
        "Extract inner logic into helpers or use early returns."
    ),
    "deep_nesting": (
        f"Nesting depth > {DEEP_NESTING_THRESHOLD}. Extract inner logic into helpers."
    ),
    "nested_loops": (
        "Nested for-loops detected. Consider alternative data structures or itertools."
    ),
    "expensive_comprehension": (
        "List comprehension with many function calls. Consider a plain loop for clarity."
    ),
}


def suggest_performance(
    score: float,
    details: dict[str, object],
) -> list[str]:
    """Actionable suggestions for the performance category."""
    if not isinstance(details, dict):
        return []
    issues = details.get("issues_found")
    if not isinstance(issues, list) or not issues:
        return []
    return [
        _PERFORMANCE_SUGGESTIONS[str(i)]
        for i in issues
        if str(i) in _PERFORMANCE_SUGGESTIONS
    ]


def suggest_structure(score: float) -> list[str]:
    """Actionable suggestions for the structure category."""
    tips: list[str] = []
    if score < _SCORE_LOW:
        tips.append("Add pyproject.toml and a tests/ directory for better project structure.")
    return tips


def suggest_devex(score: float) -> list[str]:
    """Actionable suggestions for the devex category."""
    tips: list[str] = []
    if score < _SCORE_LOW:
        tips.append("Add CLAUDE.md or AGENTS.md for AI-assisted development guidance.")
    return tips

"""Dead code scoring integration.

Converts vulture findings into maintainability and structure penalties
that can be applied by the main scoring engine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tapps_mcp.tools.vulture import DeadCodeFinding

# ---------------------------------------------------------------------------
# Penalty constants
# ---------------------------------------------------------------------------
DEAD_CODE_PENALTY_PER_FINDING: float = 2.0
DEAD_CODE_MAX_PENALTY: float = 20.0
UNREACHABLE_CODE_PENALTY: float = 5.0

# Split ratio: 60% maintainability, 40% structure
_MAINTAINABILITY_RATIO: float = 0.6
_STRUCTURE_RATIO: float = 0.4


def calculate_dead_code_penalty(
    findings: list[DeadCodeFinding],
) -> tuple[float, float]:
    """Calculate scoring penalties from dead-code findings.

    Each finding contributes a confidence-weighted penalty
    (``confidence / 100 * DEAD_CODE_PENALTY_PER_FINDING``), split
    60/40 between maintainability and structure.  Unreachable code
    gets an extra flat penalty.  Both values are capped at
    ``DEAD_CODE_MAX_PENALTY``.

    Args:
        findings: List of dead-code findings from vulture.

    Returns:
        ``(maintainability_penalty, structure_penalty)`` tuple.
    """
    if not findings:
        return 0.0, 0.0

    total_penalty = 0.0
    unreachable_penalty = 0.0

    for finding in findings:
        weight = finding.confidence / 100.0
        total_penalty += weight * DEAD_CODE_PENALTY_PER_FINDING
        if finding.finding_type == "unreachable_code":
            unreachable_penalty += UNREACHABLE_CODE_PENALTY

    maintainability = total_penalty * _MAINTAINABILITY_RATIO + unreachable_penalty
    structure = total_penalty * _STRUCTURE_RATIO

    maintainability = min(maintainability, DEAD_CODE_MAX_PENALTY)
    structure = min(structure, DEAD_CODE_MAX_PENALTY)

    return maintainability, structure


def suggest_dead_code_fixes(
    findings: list[DeadCodeFinding],
) -> list[str]:
    """Generate actionable fix suggestions from dead-code findings.

    Args:
        findings: List of dead-code findings from vulture.

    Returns:
        Human-readable suggestions, one per finding.
    """
    if not findings:
        return []

    suggestions: list[str] = []
    for finding in findings:
        if finding.finding_type == "unreachable_code":
            suggestions.append(
                f"Remove unreachable code '{finding.name}' "
                f"at line {finding.line} ({finding.confidence}% confidence)"
            )
        else:
            suggestions.append(
                f"Remove unused {finding.finding_type} '{finding.name}' "
                f"at line {finding.line} ({finding.confidence}% confidence)"
            )
    return suggestions

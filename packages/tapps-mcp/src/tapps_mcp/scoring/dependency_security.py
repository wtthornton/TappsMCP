"""Scoring helpers for dependency vulnerability integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tapps_mcp.tools.pip_audit import VulnerabilityFinding

# ---------------------------------------------------------------------------
# Penalty constants per severity level
# ---------------------------------------------------------------------------
CRITICAL_VULN_PENALTY: float = 15.0
HIGH_VULN_PENALTY: float = 10.0
MEDIUM_VULN_PENALTY: float = 5.0
LOW_VULN_PENALTY: float = 2.0
MAX_DEPENDENCY_PENALTY: float = 40.0

_PENALTY_MAP: dict[str, float] = {
    "critical": CRITICAL_VULN_PENALTY,
    "high": HIGH_VULN_PENALTY,
    "medium": MEDIUM_VULN_PENALTY,
    "low": LOW_VULN_PENALTY,
}


def calculate_dependency_penalty(findings: list[VulnerabilityFinding]) -> float:
    """Calculate security score penalty from dependency vulnerabilities.

    Each finding contributes a penalty based on its severity. The total
    penalty is capped at ``MAX_DEPENDENCY_PENALTY`` to avoid dominating
    the overall score.

    Args:
        findings: List of vulnerability findings from pip-audit.

    Returns:
        Penalty value between 0 and ``MAX_DEPENDENCY_PENALTY``.
    """
    total = 0.0
    for finding in findings:
        severity = finding.severity.lower()
        total += _PENALTY_MAP.get(severity, 0.0)
    return min(total, MAX_DEPENDENCY_PENALTY)


def suggest_dependency_fixes(findings: list[VulnerabilityFinding]) -> list[str]:
    """Generate actionable upgrade suggestions from vulnerability findings.

    Examples (illustrative — vulnerability IDs in real output come from
    pip-audit and refer to specific CVEs / GHSAs):

    For findings with a known fix version:
        "Upgrade cryptography from 39.0.0 to 42.0.0 to fix CVE-2023-38325"

    For findings without a fix version:
        "cryptography v39.0.0 has vulnerability CVE-2023-38325"

    Args:
        findings: List of vulnerability findings from pip-audit.

    Returns:
        List of human-readable suggestion strings.
    """
    suggestions: list[str] = []
    for finding in findings:
        vuln_label = finding.vulnerability_id or "unknown vulnerability"
        if finding.fixed_version:
            suggestions.append(
                f"Upgrade {finding.package} from {finding.installed_version} "
                f"to {finding.fixed_version} to fix {vuln_label}"
            )
        else:
            suggestions.append(
                f"{finding.package} v{finding.installed_version} has vulnerability {vuln_label}"
            )
    return suggestions

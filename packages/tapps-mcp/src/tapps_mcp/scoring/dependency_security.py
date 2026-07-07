"""Scoring helpers for dependency vulnerability integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tapps_core.common.models import SecurityIssue
    from tapps_mcp.tools.pip_audit import VulnerabilityFinding


# ---------------------------------------------------------------------------
# Cross-checker security-finding assembly (TAP-4529)
# ---------------------------------------------------------------------------

# Semantic categories shared across checkers, so a bandit finding and a semgrep
# finding for the SAME issue (e.g. subprocess shell=True) collapse to one and
# are not double-counted. Keyed off the checker's rule code.
_SHELL_INJECTION_BANDIT = {"B602", "B603", "B604", "B605", "B606", "B607", "B609"}
_EVAL_EXEC_BANDIT = {"B102", "B307"}
_PICKLE_BANDIT = {"B301", "B403"}
_YAML_BANDIT = {"B506"}
_WEAK_HASH_BANDIT = {"B303", "B324"}


def _category_of(issue: SecurityIssue) -> str:
    """Map a finding to a coarse semantic category for cross-checker dedupe.

    Falls back to the raw rule code so distinct issues never collapse; only
    KNOWN equivalences (a bandit code and a semgrep rule for the same class of
    bug) share a category and therefore dedupe.
    """
    code = issue.code
    if code in _SHELL_INJECTION_BANDIT or "dangerous-subprocess-shell-true" in code:
        return "shell-injection"
    if code in _EVAL_EXEC_BANDIT or "dangerous-eval-exec" in code:
        return "eval-exec"
    if code in _PICKLE_BANDIT or "insecure-pickle-load" in code:
        return "insecure-pickle"
    if code in _YAML_BANDIT or "yaml-unsafe-load" in code:
        return "yaml-unsafe-load"
    if code in _WEAK_HASH_BANDIT or "weak-hash-md5-sha1" in code:
        return "weak-hash"
    return f"code:{code}"


def merge_security_findings(
    bandit_issues: list[SecurityIssue],
    semgrep_issues: list[SecurityIssue],
) -> list[SecurityIssue]:
    """Merge bandit + semgrep findings, deduping cross-checker overlaps.

    Dedupe key is ``(semantic-category, file, line)``. When both checkers flag
    the same issue at the same location, bandit wins (it is the established
    checker and its ``B###`` codes map to OWASP), so the finding is counted
    once with ``source="bandit"``. Semgrep findings with no bandit twin survive
    with ``source="semgrep"``. Ordering is deterministic: all bandit findings
    first (input order), then surviving semgrep findings (input order).
    """
    merged: list[SecurityIssue] = list(bandit_issues)
    seen: set[tuple[str, str, int]] = {
        (_category_of(i), i.file, i.line) for i in bandit_issues
    }
    for issue in semgrep_issues:
        key = (_category_of(issue), issue.file, issue.line)
        if key in seen:
            continue
        seen.add(key)
        merged.append(issue)
    return merged

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

"""Tests for scoring.dependency_security -- penalty calculation and suggestions."""

from __future__ import annotations

from tapps_mcp.scoring.dependency_security import (
    CRITICAL_VULN_PENALTY,
    HIGH_VULN_PENALTY,
    LOW_VULN_PENALTY,
    MAX_DEPENDENCY_PENALTY,
    MEDIUM_VULN_PENALTY,
    calculate_dependency_penalty,
    suggest_dependency_fixes,
)
from tapps_mcp.tools.pip_audit import VulnerabilityFinding


def _make_finding(
    severity: str = "medium",
    package: str = "pkg",
    installed_version: str = "1.0.0",
    fixed_version: str = "",
    vulnerability_id: str = "CVE-2024-0001",
) -> VulnerabilityFinding:
    """Helper to create a VulnerabilityFinding with sensible defaults."""
    return VulnerabilityFinding(
        package=package,
        installed_version=installed_version,
        fixed_version=fixed_version,
        vulnerability_id=vulnerability_id,
        severity=severity,
    )


class TestCalculateDependencyPenalty:
    """Tests for calculate_dependency_penalty."""

    def test_no_findings_zero_penalty(self) -> None:
        assert calculate_dependency_penalty([]) == 0.0

    def test_critical_penalty(self) -> None:
        findings = [_make_finding(severity="critical")]
        assert calculate_dependency_penalty(findings) == CRITICAL_VULN_PENALTY

    def test_high_penalty(self) -> None:
        findings = [_make_finding(severity="high")]
        assert calculate_dependency_penalty(findings) == HIGH_VULN_PENALTY

    def test_medium_penalty(self) -> None:
        findings = [_make_finding(severity="medium")]
        assert calculate_dependency_penalty(findings) == MEDIUM_VULN_PENALTY

    def test_low_penalty(self) -> None:
        findings = [_make_finding(severity="low")]
        assert calculate_dependency_penalty(findings) == LOW_VULN_PENALTY

    def test_unknown_severity_no_penalty(self) -> None:
        findings = [_make_finding(severity="unknown")]
        assert calculate_dependency_penalty(findings) == 0.0

    def test_multiple_findings_additive(self) -> None:
        findings = [
            _make_finding(severity="critical"),
            _make_finding(severity="high"),
            _make_finding(severity="medium"),
        ]
        expected = CRITICAL_VULN_PENALTY + HIGH_VULN_PENALTY + MEDIUM_VULN_PENALTY
        assert calculate_dependency_penalty(findings) == expected

    def test_penalty_cap(self) -> None:
        """Many findings should be capped at MAX_DEPENDENCY_PENALTY."""
        findings = [_make_finding(severity="critical") for _ in range(10)]
        result = calculate_dependency_penalty(findings)
        assert result == MAX_DEPENDENCY_PENALTY

    def test_penalty_exactly_at_cap(self) -> None:
        """Penalty exactly at cap should equal the cap."""
        # 4 critical = 60, capped at 40
        findings = [_make_finding(severity="critical") for _ in range(4)]
        assert calculate_dependency_penalty(findings) == MAX_DEPENDENCY_PENALTY

    def test_case_insensitive_severity(self) -> None:
        findings = [_make_finding(severity="HIGH")]
        assert calculate_dependency_penalty(findings) == HIGH_VULN_PENALTY


class TestSuggestDependencyFixes:
    """Tests for suggest_dependency_fixes."""

    def test_suggest_empty(self) -> None:
        assert suggest_dependency_fixes([]) == []

    def test_suggest_with_fix_version(self) -> None:
        findings = [
            _make_finding(
                package="cryptography",
                installed_version="39.0.0",
                fixed_version="42.0.0",
                vulnerability_id="CVE-2024-26130",
            ),
        ]
        suggestions = suggest_dependency_fixes(findings)
        assert len(suggestions) == 1
        assert "Upgrade cryptography from 39.0.0 to 42.0.0" in suggestions[0]
        assert "CVE-2024-26130" in suggestions[0]

    def test_suggest_without_fix_version(self) -> None:
        findings = [
            _make_finding(
                package="requests",
                installed_version="2.25.0",
                fixed_version="",
                vulnerability_id="CVE-2023-32681",
            ),
        ]
        suggestions = suggest_dependency_fixes(findings)
        assert len(suggestions) == 1
        assert "requests v2.25.0 has vulnerability" in suggestions[0]
        assert "CVE-2023-32681" in suggestions[0]

    def test_suggest_multiple_findings(self) -> None:
        findings = [
            _make_finding(
                package="pkg-a",
                installed_version="1.0",
                fixed_version="2.0",
                vulnerability_id="CVE-A",
            ),
            _make_finding(
                package="pkg-b",
                installed_version="3.0",
                fixed_version="",
                vulnerability_id="CVE-B",
            ),
        ]
        suggestions = suggest_dependency_fixes(findings)
        assert len(suggestions) == 2
        assert "Upgrade pkg-a" in suggestions[0]
        assert "pkg-b v3.0 has vulnerability" in suggestions[1]

    def test_suggest_missing_vulnerability_id(self) -> None:
        """Findings without an ID should use 'unknown vulnerability'."""
        findings = [
            _make_finding(
                package="mystery",
                installed_version="0.1",
                fixed_version="",
                vulnerability_id="",
            ),
        ]
        suggestions = suggest_dependency_fixes(findings)
        assert len(suggestions) == 1
        assert "unknown vulnerability" in suggestions[0]

    def test_suggest_with_fix_but_no_vuln_id(self) -> None:
        findings = [
            _make_finding(
                package="pkg",
                installed_version="1.0",
                fixed_version="2.0",
                vulnerability_id="",
            ),
        ]
        suggestions = suggest_dependency_fixes(findings)
        assert "unknown vulnerability" in suggestions[0]
        assert "Upgrade pkg from 1.0 to 2.0" in suggestions[0]

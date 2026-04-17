"""Unified security scanner — bandit + secret detection with OWASP mapping."""

from __future__ import annotations

import structlog
from pydantic import BaseModel, Field

from tapps_core.common.models import SecurityIssue
from tapps_core.security.secret_scanner import SecretFinding, SecretScanner
from tapps_mcp.tools.bandit import run_bandit_check

logger = structlog.get_logger(__name__)


def _is_bandit_available() -> bool:
    """Check bandit availability using the cached tool detection results."""
    try:
        from tapps_mcp.tools.tool_detection import detect_installed_tools

        tools = detect_installed_tools()
        return any(t.name == "bandit" and t.available for t in tools)
    except Exception:
        # Fallback to shutil.which if tool_detection is unavailable
        import shutil

        return shutil.which("bandit") is not None


class SecurityScanResult(BaseModel):
    """Full security scan result combining bandit and secret scanning."""

    bandit_issues: list[SecurityIssue] = Field(default_factory=list)
    secret_findings: list[SecretFinding] = Field(default_factory=list)
    total_issues: int = Field(default=0)
    critical_count: int = Field(default=0)
    high_count: int = Field(default=0)
    medium_count: int = Field(default=0)
    low_count: int = Field(default=0)
    passed: bool = Field(default=True, description="True if no critical/high findings.")
    bandit_available: bool = Field(default=True)


def _run_bandit_scan(
    file_path: str,
    *,
    cwd: str | None,
    timeout: int,
) -> tuple[list[SecurityIssue], bool]:
    """Run bandit if available, returning (issues, bandit_available)."""
    available = _is_bandit_available()
    if not available:
        logger.info("bandit_not_available", hint="pip install bandit")
        return [], False
    return run_bandit_check(file_path, cwd=cwd, timeout=timeout), True


def _run_secret_scan(file_path: str, *, scan_secrets: bool) -> list[SecretFinding]:
    """Run secret scanning if enabled."""
    if not scan_secrets:
        return []
    scanner = SecretScanner()
    return scanner.scan_file(file_path).findings


def _aggregate_severity_counts(
    bandit_issues: list[SecurityIssue],
    secret_findings: list[SecretFinding],
) -> tuple[int, int, int, int]:
    """Count (critical, high, medium, low) severities across all findings."""
    all_severities = [i.severity for i in bandit_issues] + [f.severity for f in secret_findings]
    return (
        sum(1 for s in all_severities if s == "critical"),
        sum(1 for s in all_severities if s == "high"),
        sum(1 for s in all_severities if s == "medium"),
        sum(1 for s in all_severities if s == "low"),
    )


def run_security_scan(
    file_path: str,
    *,
    scan_secrets: bool = True,
    cwd: str | None = None,
    timeout: int = 30,
) -> SecurityScanResult:
    """Run a full security scan on a single file.

    Combines:
      1. Bandit static analysis (if installed)
      2. Secret pattern detection (always runs)

    Args:
        file_path: Path to the Python file to scan.
        scan_secrets: Whether to run secret detection.
        cwd: Working directory for bandit subprocess.
        timeout: Bandit execution timeout.

    Returns:
        Unified ``SecurityScanResult``.
    """
    bandit_issues, bandit_available = _run_bandit_scan(file_path, cwd=cwd, timeout=timeout)
    secret_findings = _run_secret_scan(file_path, scan_secrets=scan_secrets)
    critical, high, medium, low = _aggregate_severity_counts(bandit_issues, secret_findings)

    return SecurityScanResult(
        bandit_issues=bandit_issues,
        secret_findings=secret_findings,
        total_issues=len(bandit_issues) + len(secret_findings),
        critical_count=critical,
        high_count=high,
        medium_count=medium,
        low_count=low,
        passed=(critical + high) == 0,
        bandit_available=bandit_available,
    )

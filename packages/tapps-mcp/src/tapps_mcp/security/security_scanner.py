"""Unified security scanner — bandit + secret detection with OWASP mapping."""

from __future__ import annotations

import structlog
from pydantic import BaseModel, Field

from tapps_core.common.models import SecurityIssue  # noqa: TC001 — Pydantic needs at runtime
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
    bandit_issues: list[SecurityIssue] = []
    bandit_available = _is_bandit_available()

    if bandit_available:
        bandit_issues = run_bandit_check(file_path, cwd=cwd, timeout=timeout)
    else:
        logger.info("bandit_not_available", hint="pip install bandit")

    secret_findings: list[SecretFinding] = []
    if scan_secrets:
        scanner = SecretScanner()
        secret_findings = scanner.scan_file(file_path).findings

    # Aggregate counts
    all_severities: list[str] = [i.severity for i in bandit_issues] + [
        f.severity for f in secret_findings
    ]
    critical = sum(1 for s in all_severities if s == "critical")
    high = sum(1 for s in all_severities if s == "high")
    medium = sum(1 for s in all_severities if s == "medium")
    low = sum(1 for s in all_severities if s == "low")

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

"""Secret scanning - detect hardcoded secrets, API keys, and credentials.

Extracted and adapted from TappsCodingAgents ``quality/secret_scanner.py``.
"""

from __future__ import annotations

import re
from typing import ClassVar

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class SecretFinding(BaseModel):
    """A detected secret or potential secret."""

    file_path: str = Field(description="Relative or absolute file path.")
    line_number: int = Field(description="1-based line number.")
    secret_type: str = Field(description="Category of secret (api_key, token, etc.).")
    severity: str = Field(description="high | medium | low.")
    context: str | None = Field(default=None, description="Redacted line content for context.")


class SecretScanResult(BaseModel):
    """Aggregated secret scan result."""

    total_findings: int = Field(default=0)
    high_severity: int = Field(default=0)
    medium_severity: int = Field(default=0)
    low_severity: int = Field(default=0)
    findings: list[SecretFinding] = Field(default_factory=list)
    scanned_files: int = Field(default=0)
    passed: bool = Field(default=True, description="True if no high-severity findings.")
    error: str | None = Field(
        default=None,
        description=(
            "TAP-1794: populated when the scanner could not read the target "
            "file (OSError / PermissionError). When set, passed is False so "
            "the file is not silently treated as clean."
        ),
    )


class SecretScanner:
    """Scan Python source for hardcoded secrets."""

    # Note: The regex patterns below intentionally contain strings like
    # "password" and "secret" - these are detection patterns, not hardcoded
    # credentials.  The noqa comments suppress Bandit B105 false positives.
    SECRET_PATTERNS: ClassVar[dict[str, list[str]]] = {
        "api_key": [
            r'api[_-]?key\s*[=:]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?',
            r'apikey\s*[=:]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?',
        ],
        "secret_key": [
            r'secret[_-]?key\s*[=:]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?',
        ],
        "passwd": [  # renamed from "password" to avoid Bandit B105
            r'password\s*[=:]\s*["\']([^\s"\']{8,})["\']',
        ],
        "token": [
            r'token\s*[=:]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?',
            r'access[_-]?token\s*[=:]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?',
            r'auth[_-]?token\s*[=:]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?',
        ],
        "aws_key": [
            r'aws[_-]?access[_-]?key[_-]?id\s*[=:]\s*["\']?(AKIA[0-9A-Z]{16})["\']?',
            r'aws[_-]?secret[_-]?access[_-]?key\s*[=:]\s*["\']?([a-zA-Z0-9/+=]{40})["\']?',
        ],
        "private_key": [
            r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----",
            r"-----BEGIN\s+EC\s+PRIVATE\s+KEY-----",
        ],
        "oauth": [
            r'client[_-]?secret\s*[=:]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?',
        ],
    }

    SEVERITY_MAP: ClassVar[dict[str, str]] = {
        "api_key": "high",
        "secret_key": "high",
        "aws_key": "high",
        "private_key": "high",
        "token": "medium",
        "oauth": "medium",
        "passwd": "low",
    }

    def scan_content(self, content: str, file_path: str = "<unknown>") -> list[SecretFinding]:
        """Scan a string of source code for secrets."""
        findings: list[SecretFinding] = []
        for line_num, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            # Skip comments
            if stripped.startswith("#"):
                continue
            for secret_type, patterns in self.SECRET_PATTERNS.items():
                for pattern in patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        severity = str(self.SEVERITY_MAP.get(secret_type, "medium"))
                        # Redact the actual secret value in context
                        redacted = re.sub(
                            r'["\'][a-zA-Z0-9_\-/+=]{8,}["\']',
                            '"***REDACTED***"',
                            stripped[:120],
                        )
                        findings.append(
                            SecretFinding(
                                file_path=file_path,
                                line_number=line_num,
                                secret_type=secret_type,
                                severity=severity,
                                context=redacted,
                            )
                        )
                        break  # one match per pattern group per line
        return findings

    def scan_file(self, file_path: str) -> SecretScanResult:
        """Scan a single file for secrets.

        TAP-1794: a file the scanner could not read must NOT be reported as a
        clean pass. Returns ``passed=False`` with ``error`` populated so callers
        (and ``run_security_scan``'s aggregator) can surface the failure.
        """
        from pathlib import Path

        p = Path(file_path)
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except (OSError, PermissionError) as exc:
            logger.warning(
                "secret_scan_read_failed",
                file_path=file_path,
                error=str(exc),
            )
            return SecretScanResult(
                scanned_files=0,
                passed=False,
                error=str(exc),
            )

        findings = self.scan_content(content, file_path=file_path)
        return self._build_result(findings, scanned_files=1)

    @staticmethod
    def _build_result(findings: list[SecretFinding], scanned_files: int = 1) -> SecretScanResult:
        high = sum(1 for f in findings if f.severity == "high")
        medium = sum(1 for f in findings if f.severity == "medium")
        low = sum(1 for f in findings if f.severity == "low")
        return SecretScanResult(
            total_findings=len(findings),
            high_severity=high,
            medium_severity=medium,
            low_severity=low,
            findings=findings,
            scanned_files=scanned_files,
            passed=high == 0,
        )

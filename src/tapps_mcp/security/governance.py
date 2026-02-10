"""Governance & safety layer.

Filters secrets, PII, and credentials from content before it appears
in tool responses or logs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import ClassVar


@dataclass
class GovernancePolicy:
    """Governance policy configuration."""

    filter_secrets: bool = True
    filter_tokens: bool = True
    filter_credentials: bool = True
    filter_pii: bool = True


@dataclass
class FilterResult:
    """Result of content filtering."""

    allowed: bool
    reason: str | None = None
    filtered_content: str | None = None
    detected_issues: list[str] = field(default_factory=list)


class GovernanceLayer:
    """Filters sensitive data from content.

    Used to scrub tool outputs, log messages, and knowledge-base entries
    before they are returned to the MCP client.
    """

    SECRET_PATTERNS: ClassVar[list[str]] = [
        r"(?i)(api[_-]?key|apikey)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{20,})",
        r"(?i)(secret[_-]?key|secretkey)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{20,})",
        r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"]?([^\s'\"\n]{8,})",
        r"(?i)(token)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-\.]{32,})",
        r"(?i)(bearer\s+)([a-zA-Z0-9_\-\.]{32,})",
        r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----",
        r"-----BEGIN\s+EC\s+PRIVATE\s+KEY-----",
        r"ssh-rsa\s+[A-Za-z0-9+/=]{100,}",
    ]

    PII_PATTERNS: ClassVar[list[str]] = [
        r"\b\d{3}-\d{2}-\d{4}\b",  # SSN
        r"\b\d{3}\.\d{2}\.\d{4}\b",  # SSN variant
        r"\b\d{16}\b",  # Credit card
    ]

    CREDENTIAL_PATTERNS: ClassVar[list[str]] = [
        r"(?i)(connection[_-]?string|conn[_-]?str)\s*[:=]\s*['\"]?([^\s'\"\n]+)",
    ]

    def __init__(self, policy: GovernancePolicy | None = None) -> None:
        self.policy = policy or GovernancePolicy()

    def filter_content(self, content: str, source: str | None = None) -> FilterResult:
        """Filter content for sensitive data.

        Args:
            content: Content to filter.
            source: Optional source identifier for logging.

        Returns:
            ``FilterResult`` indicating whether the content is clean.
        """
        detected_issues: list[str] = []
        filtered = content

        if self.policy.filter_secrets:
            for pattern in self.SECRET_PATTERNS:
                if re.search(pattern, filtered):
                    detected_issues.append(f"Secret pattern detected: {pattern[:50]}")
                    # Patterns with 2+ groups: keep group 1 (label), redact group 2 (value)
                    # Patterns with 0-1 groups: replace entire match
                    compiled = re.compile(pattern)
                    if compiled.groups >= 2:  # noqa: PLR2004
                        filtered = compiled.sub(r"\1 = [REDACTED]", filtered)
                    else:
                        filtered = compiled.sub("[REDACTED]", filtered)

        if self.policy.filter_tokens:
            token_pat = r"(?i)(token|bearer)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-\.]{32,})"  # noqa: S105
            if re.search(token_pat, filtered):
                detected_issues.append("Token detected")
                filtered = re.sub(token_pat, r"\1 = [REDACTED]", filtered)

        if self.policy.filter_credentials:
            for pattern in self.CREDENTIAL_PATTERNS:
                if re.search(pattern, filtered):
                    detected_issues.append("Credentials detected")
                    filtered = re.sub(pattern, r"\1 = [REDACTED]", filtered)

        if self.policy.filter_pii:
            for pattern in self.PII_PATTERNS:
                if re.search(pattern, filtered):
                    detected_issues.append("Potential PII detected")
                    filtered = re.sub(pattern, "[REDACTED]", filtered)

        allowed = len(detected_issues) == 0

        return FilterResult(
            allowed=allowed,
            reason=(f"Content filtered: {', '.join(detected_issues)}" if not allowed else None),
            filtered_content=filtered if filtered != content else None,
            detected_issues=detected_issues,
        )

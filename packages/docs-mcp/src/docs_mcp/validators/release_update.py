"""Validator for release update document bodies.

Pre-post gate: ``validate_release_update(body)`` returns
``{agent_ready, score, findings}`` so callers can confirm template
compliance before posting to Linear.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

RULE_MISSING_VERSION_HEADER = "missing_version_header"
RULE_MISSING_HEALTH = "missing_health"
RULE_MISSING_HIGHLIGHTS = "missing_highlights"
RULE_MISSING_ISSUES_CLOSED = "missing_issues_closed"
RULE_MISSING_LINKS = "missing_links"
RULE_NO_TAP_REF = "no_tap_ref_in_issues"

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"

_VERSION_HEADER_RE = re.compile(r"^## Release v\S+", re.MULTILINE)
_HEALTH_RE = re.compile(r"\*\*Health:\*\*\s*.+", re.MULTILINE)
_HIGHLIGHTS_RE = re.compile(r"### Highlights", re.MULTILINE)
_ISSUES_RE = re.compile(r"### Issues Closed", re.MULTILINE)
_LINKS_RE = re.compile(r"### Links", re.MULTILINE)
_TAP_REF_RE = re.compile(r"\bTAP-\d+\b")
_HIGHLIGHT_ITEM_RE = re.compile(r"^- (?!No highlights)", re.MULTILINE)
_ISSUES_ITEM_RE = re.compile(r"^- (?!None\.)", re.MULTILINE)


class ReleaseUpdateFinding(BaseModel):
    """One structural finding on a release update body."""

    severity: str
    rule: str
    message: str


class ReleaseUpdateReport(BaseModel):
    """Pre-post gate result for a release update body."""

    agent_ready: bool
    score: int
    findings: list[ReleaseUpdateFinding]


def validate_release_update(body: str) -> ReleaseUpdateReport:
    """Validate a release update body as a pre-post gate.

    Returns ``agent_ready=True`` iff there are zero HIGH-severity findings.
    Score starts at 100 and is reduced per finding category.
    """
    findings: list[ReleaseUpdateFinding] = []

    if not _VERSION_HEADER_RE.search(body):
        findings.append(
            ReleaseUpdateFinding(
                severity=SEVERITY_HIGH,
                rule=RULE_MISSING_VERSION_HEADER,
                message="Body must start with '## Release vX.Y.Z (date)' header.",
            )
        )

    if not _HEALTH_RE.search(body):
        findings.append(
            ReleaseUpdateFinding(
                severity=SEVERITY_HIGH,
                rule=RULE_MISSING_HEALTH,
                message="Body must contain '**Health:** On Track|At Risk|Off Track'.",
            )
        )

    has_highlights_section = bool(_HIGHLIGHTS_RE.search(body))
    if not has_highlights_section or not _HIGHLIGHT_ITEM_RE.search(body):
        findings.append(
            ReleaseUpdateFinding(
                severity=SEVERITY_HIGH,
                rule=RULE_MISSING_HIGHLIGHTS,
                message="Body must have a '### Highlights' section with at least one bullet.",
            )
        )

    has_issues_section = bool(_ISSUES_RE.search(body))
    if not has_issues_section:
        findings.append(
            ReleaseUpdateFinding(
                severity=SEVERITY_HIGH,
                rule=RULE_MISSING_ISSUES_CLOSED,
                message="Body must have a '### Issues Closed' section.",
            )
        )

    if has_issues_section and not _TAP_REF_RE.search(body):
        findings.append(
            ReleaseUpdateFinding(
                severity=SEVERITY_MEDIUM,
                rule=RULE_NO_TAP_REF,
                message="Issues Closed section contains no TAP-### references.",
            )
        )

    if not _LINKS_RE.search(body):
        findings.append(
            ReleaseUpdateFinding(
                severity=SEVERITY_MEDIUM,
                rule=RULE_MISSING_LINKS,
                message="Body should have a '### Links' section with at least a Changelog URL.",
            )
        )

    high_count = sum(1 for f in findings if f.severity == SEVERITY_HIGH)
    med_count = sum(1 for f in findings if f.severity == SEVERITY_MEDIUM)
    score = max(0, 100 - high_count * 25 - med_count * 10)
    agent_ready = high_count == 0

    return ReleaseUpdateReport(agent_ready=agent_ready, score=score, findings=findings)

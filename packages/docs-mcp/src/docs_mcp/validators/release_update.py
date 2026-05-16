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


_NEXT_HEADING_RE = re.compile(r"^#{2,3}\s", re.MULTILINE)


def _slice_section(body: str, heading_match: re.Match[str]) -> str:
    """Return the body of a section delimited by *heading_match*.

    The slice starts after the heading line and ends at the next ``## `` or
    ``### `` heading (whichever comes first) or at EOF. Mirrors the pattern in
    ``linters/linear_issue.py::_check_acceptance``.
    """
    start = heading_match.end()
    next_heading = _NEXT_HEADING_RE.search(body, pos=start)
    end = next_heading.start() if next_heading else len(body)
    return body[start:end]


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

    highlights_match = _HIGHLIGHTS_RE.search(body)
    highlights_section = _slice_section(body, highlights_match) if highlights_match else None
    # TAP-1793: search the Highlights section body, not the whole document — a
    # populated Issues Closed bullet otherwise silently satisfied the gate.
    if highlights_section is None or not _HIGHLIGHT_ITEM_RE.search(highlights_section):
        findings.append(
            ReleaseUpdateFinding(
                severity=SEVERITY_HIGH,
                rule=RULE_MISSING_HIGHLIGHTS,
                message="Body must have a '### Highlights' section with at least one bullet.",
            )
        )

    issues_match = _ISSUES_RE.search(body)
    issues_section = _slice_section(body, issues_match) if issues_match else None
    # TAP-1793: use the previously-unused _ISSUES_ITEM_RE to verify the Issues
    # Closed section has at least one non-placeholder bullet.
    if issues_section is None:
        findings.append(
            ReleaseUpdateFinding(
                severity=SEVERITY_HIGH,
                rule=RULE_MISSING_ISSUES_CLOSED,
                message="Body must have a '### Issues Closed' section.",
            )
        )
    elif not _ISSUES_ITEM_RE.search(issues_section):
        findings.append(
            ReleaseUpdateFinding(
                severity=SEVERITY_HIGH,
                rule=RULE_MISSING_ISSUES_CLOSED,
                message=(
                    "'### Issues Closed' section must list at least one closed "
                    "issue bullet (or 'None.' as an explicit placeholder)."
                ),
            )
        )

    if issues_section is not None and not _TAP_REF_RE.search(issues_section):
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

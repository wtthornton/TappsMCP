"""Tests for docs_mcp.validators.release_update."""

from __future__ import annotations

import pytest

from docs_mcp.validators.release_update import (
    RULE_MISSING_HEALTH,
    RULE_MISSING_HIGHLIGHTS,
    RULE_MISSING_ISSUES_CLOSED,
    RULE_MISSING_LINKS,
    RULE_MISSING_VERSION_HEADER,
    RULE_NO_TAP_REF,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
    validate_release_update,
)

_COMPLIANT_BODY = """\
## Release v1.5.0 (2026-04-29)

**Health:** On Track

### Highlights

- Added tapps_release_update tool

### Issues Closed

- TAP-1112: tapps_release_update MCP tool

### Links

- Changelog: https://example.com/CHANGELOG.md
"""


class TestCompliantBody:
    def test_agent_ready(self) -> None:
        report = validate_release_update(_COMPLIANT_BODY)
        assert report.agent_ready is True

    def test_perfect_score(self) -> None:
        report = validate_release_update(_COMPLIANT_BODY)
        assert report.score == 100

    def test_no_findings(self) -> None:
        report = validate_release_update(_COMPLIANT_BODY)
        assert report.findings == []


class TestMissingVersionHeader:
    def test_detected(self) -> None:
        body = _COMPLIANT_BODY.replace("## Release v1.5.0 (2026-04-29)\n", "")
        report = validate_release_update(body)
        rules = [f.rule for f in report.findings]
        assert RULE_MISSING_VERSION_HEADER in rules

    def test_is_high_severity(self) -> None:
        body = _COMPLIANT_BODY.replace("## Release v1.5.0 (2026-04-29)\n", "")
        report = validate_release_update(body)
        finding = next(f for f in report.findings if f.rule == RULE_MISSING_VERSION_HEADER)
        assert finding.severity == SEVERITY_HIGH

    def test_blocks_agent_ready(self) -> None:
        body = _COMPLIANT_BODY.replace("## Release v1.5.0 (2026-04-29)\n", "")
        report = validate_release_update(body)
        assert report.agent_ready is False


class TestMissingHealth:
    def test_detected(self) -> None:
        body = _COMPLIANT_BODY.replace("**Health:** On Track\n", "")
        report = validate_release_update(body)
        rules = [f.rule for f in report.findings]
        assert RULE_MISSING_HEALTH in rules

    def test_is_high_severity(self) -> None:
        body = _COMPLIANT_BODY.replace("**Health:** On Track\n", "")
        report = validate_release_update(body)
        finding = next(f for f in report.findings if f.rule == RULE_MISSING_HEALTH)
        assert finding.severity == SEVERITY_HIGH


class TestMissingHighlights:
    def test_missing_section_detected(self) -> None:
        body = _COMPLIANT_BODY.replace("### Highlights\n\n- Added tapps_release_update tool\n", "")
        report = validate_release_update(body)
        rules = [f.rule for f in report.findings]
        assert RULE_MISSING_HIGHLIGHTS in rules

    def test_is_high_severity(self) -> None:
        body = _COMPLIANT_BODY.replace("### Highlights\n\n- Added tapps_release_update tool\n", "")
        report = validate_release_update(body)
        finding = next(f for f in report.findings if f.rule == RULE_MISSING_HIGHLIGHTS)
        assert finding.severity == SEVERITY_HIGH


class TestMissingIssuesClosed:
    def test_detected(self) -> None:
        body = _COMPLIANT_BODY.replace(
            "### Issues Closed\n\n- TAP-1112: tapps_release_update MCP tool\n", ""
        )
        report = validate_release_update(body)
        rules = [f.rule for f in report.findings]
        assert RULE_MISSING_ISSUES_CLOSED in rules

    def test_is_high_severity(self) -> None:
        body = _COMPLIANT_BODY.replace(
            "### Issues Closed\n\n- TAP-1112: tapps_release_update MCP tool\n", ""
        )
        report = validate_release_update(body)
        finding = next(f for f in report.findings if f.rule == RULE_MISSING_ISSUES_CLOSED)
        assert finding.severity == SEVERITY_HIGH


class TestNoTapRef:
    def test_detected_when_no_tap_ref(self) -> None:
        body = _COMPLIANT_BODY.replace("TAP-1112: tapps_release_update MCP tool", "some tool")
        report = validate_release_update(body)
        rules = [f.rule for f in report.findings]
        assert RULE_NO_TAP_REF in rules

    def test_is_medium_severity(self) -> None:
        body = _COMPLIANT_BODY.replace("TAP-1112: tapps_release_update MCP tool", "some tool")
        report = validate_release_update(body)
        finding = next(f for f in report.findings if f.rule == RULE_NO_TAP_REF)
        assert finding.severity == SEVERITY_MEDIUM

    def test_does_not_block_agent_ready(self) -> None:
        body = _COMPLIANT_BODY.replace("TAP-1112: tapps_release_update MCP tool", "some tool")
        report = validate_release_update(body)
        assert report.agent_ready is True


class TestMissingLinks:
    def test_detected(self) -> None:
        body = _COMPLIANT_BODY.replace("### Links\n\n- Changelog: https://example.com/CHANGELOG.md\n", "")
        report = validate_release_update(body)
        rules = [f.rule for f in report.findings]
        assert RULE_MISSING_LINKS in rules

    def test_is_medium_severity(self) -> None:
        body = _COMPLIANT_BODY.replace("### Links\n\n- Changelog: https://example.com/CHANGELOG.md\n", "")
        report = validate_release_update(body)
        finding = next(f for f in report.findings if f.rule == RULE_MISSING_LINKS)
        assert finding.severity == SEVERITY_MEDIUM

    def test_does_not_block_agent_ready(self) -> None:
        body = _COMPLIANT_BODY.replace("### Links\n\n- Changelog: https://example.com/CHANGELOG.md\n", "")
        report = validate_release_update(body)
        assert report.agent_ready is True


class TestScoring:
    def test_one_high_finding_reduces_score_by_25(self) -> None:
        body = _COMPLIANT_BODY.replace("**Health:** On Track\n", "")
        report = validate_release_update(body)
        assert report.score == 75

    def test_one_medium_finding_reduces_score_by_10(self) -> None:
        body = _COMPLIANT_BODY.replace("### Links\n\n- Changelog: https://example.com/CHANGELOG.md\n", "")
        report = validate_release_update(body)
        assert report.score == 90

    def test_score_floored_at_zero(self) -> None:
        report = validate_release_update("no content at all")
        assert report.score >= 0

    def test_empty_body_not_agent_ready(self) -> None:
        report = validate_release_update("   ")
        assert report.agent_ready is False

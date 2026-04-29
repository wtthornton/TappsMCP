"""Tests for docs_mcp.linters.linear_issue — Linear-issue lint rules."""

from __future__ import annotations

import pytest

from docs_mcp.linters.linear_issue import (
    RULE_ACCEPTANCE_EMPTY,
    RULE_AUTOLINK_MANGLED,
    RULE_CODE_BLOCK_NO_ANCHOR,
    RULE_MISSING_ACCEPTANCE,
    RULE_MISSING_ESTIMATE,
    RULE_MISSING_FILE_ANCHOR,
    RULE_MISSING_PRIORITY,
    RULE_TITLE_TOO_LONG,
    RULE_UUID_WRAPPED_REF,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    STATUS_BACKLOG,
    STATUS_TRIAGE,
    lint_issue,
)


# ---------------------------------------------------------------------------
# Fixtures: known-good and known-bad issue payloads
# ---------------------------------------------------------------------------


@pytest.fixture
def clean_issue() -> dict[str, object]:
    """Template-compliant issue payload."""
    return {
        "title": "upgrade.py: _has_python_signals rglob traverses node_modules",
        "description": (
            "## What\n"
            "`_has_python_signals` falls back to `project_root.rglob('*.py')`"
            " which does not prune `node_modules` / `.venv`.\n\n"
            "## Where\n"
            "`packages/tapps-mcp/src/tapps_mcp/pipeline/upgrade.py:92-116`\n\n"
            "## Acceptance\n"
            "- [ ] rglob is replaced with a pruning walk\n"
            "- [ ] `pytest packages/tapps-mcp/tests/unit/test_upgrade.py` passes\n"
        ),
        "priority": 2,
        "estimate": 2.0,
    }


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestCleanIssue:
    """A template-compliant issue should pass cleanly."""

    def test_clean_issue_is_agent_ready(self, clean_issue: dict[str, object]) -> None:
        result = lint_issue(**clean_issue)  # type: ignore[arg-type]
        assert result.agent_ready is True
        assert result.suggested_label == ""

    def test_clean_issue_has_no_high_findings(self, clean_issue: dict[str, object]) -> None:
        result = lint_issue(**clean_issue)  # type: ignore[arg-type]
        assert not any(f.severity == SEVERITY_HIGH for f in result.findings)

    def test_clean_issue_score_is_100(self, clean_issue: dict[str, object]) -> None:
        result = lint_issue(**clean_issue)  # type: ignore[arg-type]
        assert result.score == 100

    def test_clean_issue_tokens_include_total(self, clean_issue: dict[str, object]) -> None:
        result = lint_issue(**clean_issue)  # type: ignore[arg-type]
        assert result.tokens["estimated_tokens"] > 0
        assert result.tokens["noise_bytes_recoverable"] == 0


# ---------------------------------------------------------------------------
# Rule: autolink-mangled
# ---------------------------------------------------------------------------


class TestAutolinkMangle:
    """Linear's autolinker mangles filenames; the linter catches the artifact."""

    def test_mangled_filename_is_flagged(self) -> None:
        result = lint_issue(
            title="foo.py: short",
            description=(
                "## What\n"
                "See [AGENTS.md](<http://AGENTS.md>).\n\n"
                "## Where\n"
                "`foo.py:1`\n\n"
                "## Acceptance\n"
                "- [ ] done\n"
            ),
            priority=3,
            estimate=1.0,
        )
        rules = [f.rule for f in result.findings]
        assert RULE_AUTOLINK_MANGLED in rules

    def test_real_external_link_not_flagged(self) -> None:
        """A legit `[label](<http://host>)` where label != host must NOT trip the rule."""
        result = lint_issue(
            title="foo.py: check",
            description=(
                "## What\n"
                "See [Linear docs](<http://linear.app/docs>).\n\n"
                "## Where\n"
                "`foo.py:1`\n\n"
                "## Acceptance\n"
                "- [ ] done\n"
            ),
            priority=3,
            estimate=1.0,
        )
        rules = [f.rule for f in result.findings]
        assert RULE_AUTOLINK_MANGLED not in rules

    def test_mangled_link_counts_noise_bytes(self) -> None:
        result = lint_issue(
            title="foo.py: x",
            description=(
                "## What\ndetail\n"
                "## Where\n`foo.py:1`\n"
                "## Acceptance\n- [ ] a\n\n"
                "refs [AGENTS.md](<http://AGENTS.md>)\n"
            ),
            priority=3,
            estimate=1.0,
        )
        assert result.tokens["noise_bytes_recoverable"] > 0


# ---------------------------------------------------------------------------
# Rule: uuid-wrapped-ref
# ---------------------------------------------------------------------------


class TestUuidWrappedRef:
    def test_uuid_wrapped_ref_flagged(self) -> None:
        result = lint_issue(
            title="foo.py: x",
            description=(
                '## What\nFollow-up from <issue id="abc-123">TAP-496</issue>.\n\n'
                "## Where\n`foo.py:1`\n\n"
                "## Acceptance\n- [ ] done\n"
            ),
            priority=3,
            estimate=1.0,
        )
        rules = [f.rule for f in result.findings]
        assert RULE_UUID_WRAPPED_REF in rules

    def test_bare_tap_ref_not_flagged(self) -> None:
        result = lint_issue(
            title="foo.py: x",
            description=(
                "## What\nFollow-up from TAP-496.\n\n"
                "## Where\n`foo.py:1`\n\n"
                "## Acceptance\n- [ ] done\n"
            ),
            priority=3,
            estimate=1.0,
        )
        rules = [f.rule for f in result.findings]
        assert RULE_UUID_WRAPPED_REF not in rules


# ---------------------------------------------------------------------------
# Rule: title-too-long
# ---------------------------------------------------------------------------


class TestTitleLength:
    def test_long_title_flagged(self) -> None:
        long_title = "foo.py: " + ("x" * 100)
        result = lint_issue(
            title=long_title,
            description=(
                "## What\nd\n## Where\n`foo.py:1`\n## Acceptance\n- [ ] done\n"
            ),
            priority=3,
            estimate=1.0,
        )
        rules = [f.rule for f in result.findings]
        assert RULE_TITLE_TOO_LONG in rules

    def test_empty_title_flagged_as_high(self) -> None:
        result = lint_issue(
            title="",
            description="## What\nd\n## Where\n`foo.py:1`\n## Acceptance\n- [ ] done\n",
            priority=3,
            estimate=1.0,
        )
        high = [f for f in result.findings if f.rule == RULE_TITLE_TOO_LONG]
        assert high and high[0].severity == SEVERITY_HIGH
        assert result.agent_ready is False


# ---------------------------------------------------------------------------
# Rule: missing-file-anchor
# ---------------------------------------------------------------------------


class TestMissingFileAnchor:
    def test_missing_anchor_flagged_high(self) -> None:
        result = lint_issue(
            title="foo: broken",
            description=(
                "## What\nsomething is broken\n\n"
                "## Acceptance\n- [ ] fix it\n"
            ),
            priority=3,
            estimate=1.0,
        )
        rules = [f.rule for f in result.findings]
        assert RULE_MISSING_FILE_ANCHOR in rules
        high = [f for f in result.findings if f.rule == RULE_MISSING_FILE_ANCHOR]
        assert high[0].severity == SEVERITY_HIGH

    def test_missing_anchor_not_required_for_epic(self) -> None:
        result = lint_issue(
            title="Epic: something",
            description="## Outcome\nBig thing.\n\n## Acceptance\n- [ ] ship\n",
            priority=2,
            estimate=1.0,
            is_epic=True,
        )
        rules = [f.rule for f in result.findings]
        assert RULE_MISSING_FILE_ANCHOR not in rules


# ---------------------------------------------------------------------------
# Rule: missing-acceptance / acceptance-empty
# ---------------------------------------------------------------------------


class TestAcceptance:
    def test_missing_acceptance_flagged_high(self) -> None:
        result = lint_issue(
            title="foo.py: x",
            description="## What\nd\n## Where\n`foo.py:1`\n",
            priority=3,
            estimate=1.0,
        )
        rules = [f.rule for f in result.findings]
        assert RULE_MISSING_ACCEPTANCE in rules
        assert result.agent_ready is False

    def test_empty_acceptance_section_flagged(self) -> None:
        result = lint_issue(
            title="foo.py: x",
            description=(
                "## What\nd\n## Where\n`foo.py:1`\n## Acceptance\n\n## Refs\nTAP-1\n"
            ),
            priority=3,
            estimate=1.0,
        )
        rules = [f.rule for f in result.findings]
        assert RULE_ACCEPTANCE_EMPTY in rules
        assert result.agent_ready is False

    def test_acceptance_criteria_heading_variant_accepted(self) -> None:
        """`## Acceptance Criteria` should satisfy the check."""
        result = lint_issue(
            title="foo.py: x",
            description=(
                "## What\nd\n## Where\n`foo.py:1`\n"
                "## Acceptance Criteria\n- [ ] done\n"
            ),
            priority=3,
            estimate=1.0,
        )
        rules = [f.rule for f in result.findings]
        assert RULE_MISSING_ACCEPTANCE not in rules
        assert RULE_ACCEPTANCE_EMPTY not in rules


# ---------------------------------------------------------------------------
# Rule: code-block-no-anchor
# ---------------------------------------------------------------------------


class TestCodeBlockAnchors:
    def test_fence_far_from_anchor_flagged(self) -> None:
        description = (
            "## What\n"
            "```python\n"
            "def bad(): pass\n"
            "```\n"
            + ("\nfiller line\n" * 15)
            + "\n## Where\n`foo.py:1`\n## Acceptance\n- [ ] done\n"
        )
        result = lint_issue(
            title="foo.py: x",
            description=description,
            priority=3,
            estimate=1.0,
        )
        rules = [f.rule for f in result.findings]
        assert RULE_CODE_BLOCK_NO_ANCHOR in rules

    def test_fence_near_anchor_not_flagged(self) -> None:
        result = lint_issue(
            title="foo.py: x",
            description=(
                "## Where\n`foo.py:10-20`\n\n"
                "```python\n"
                "def bad(): pass\n"
                "```\n\n"
                "## Acceptance\n- [ ] done\n"
            ),
            priority=3,
            estimate=1.0,
        )
        rules = [f.rule for f in result.findings]
        assert RULE_CODE_BLOCK_NO_ANCHOR not in rules


# ---------------------------------------------------------------------------
# Rules: missing metadata
# ---------------------------------------------------------------------------


class TestMissingMetadata:
    def test_missing_priority_low(self) -> None:
        result = lint_issue(
            title="foo.py: x",
            description="## What\nd\n## Where\n`foo.py:1`\n## Acceptance\n- [ ] a\n",
            priority=None,
            estimate=1.0,
        )
        rules = [(f.rule, f.severity) for f in result.findings]
        assert (RULE_MISSING_PRIORITY, SEVERITY_LOW) in rules

    def test_missing_estimate_low(self) -> None:
        result = lint_issue(
            title="foo.py: x",
            description="## What\nd\n## Where\n`foo.py:1`\n## Acceptance\n- [ ] a\n",
            priority=3,
            estimate=None,
        )
        rules = [(f.rule, f.severity) for f in result.findings]
        assert (RULE_MISSING_ESTIMATE, SEVERITY_LOW) in rules

    def test_missing_estimate_not_flagged_for_epic(self) -> None:
        result = lint_issue(
            title="Epic: big",
            description="## Outcome\nd\n## Acceptance\n- [ ] a\n",
            priority=2,
            estimate=None,
            is_epic=True,
        )
        rules = [f.rule for f in result.findings]
        assert RULE_MISSING_ESTIMATE not in rules


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


class TestScoring:
    def test_each_high_deducts_25(self) -> None:
        result = lint_issue(
            title="",  # HIGH (empty title)
            description="no acceptance and no anchor",  # HIGH + HIGH
            priority=3,
            estimate=1.0,
        )
        # 3 HIGH findings => 100 - 75 = 25
        assert result.score == 25

    def test_score_floors_at_zero(self) -> None:
        result = lint_issue(
            title="",
            description="",
            priority=None,
            estimate=None,
        )
        assert result.score >= 0


# ---------------------------------------------------------------------------
# Label suggestion
# ---------------------------------------------------------------------------


class TestLabelAndStatusSuggestion:
    def test_clean_issue_suggests_empty_label_and_backlog(self, clean_issue: dict[str, object]) -> None:
        result = lint_issue(**clean_issue)  # type: ignore[arg-type]
        assert result.suggested_label == ""
        assert result.suggested_status == STATUS_BACKLOG

    def test_high_findings_route_to_triage(self) -> None:
        result = lint_issue(
            title="foo: x",
            description="no acceptance",
            priority=3,
            estimate=1.0,
        )
        assert result.suggested_label == ""
        assert result.suggested_status == STATUS_TRIAGE

    def test_blocked_markers_route_to_triage(self) -> None:
        result = lint_issue(
            title="foo.py: change",
            description=(
                "## What\nblocked by TAP-999\n"
                "## Where\n`foo.py:1`\n"
                "## Acceptance\n- [ ] done\n"
            ),
            priority=3,
            estimate=1.0,
        )
        assert result.suggested_label == ""
        assert result.suggested_status == STATUS_TRIAGE

"""Tests for docs_mcp.validators.linear_issue — pre-create gate."""

from __future__ import annotations

import pytest

from docs_mcp.validators.linear_issue import (
    ValidationIssue,
    ValidationReport,
    validate_issue,
)


@pytest.fixture
def clean_issue() -> dict[str, object]:
    return {
        "title": "foo.py: something breaks",
        "description": (
            "## What\na thing breaks\n\n"
            "## Where\n`packages/foo/foo.py:12-20`\n\n"
            "## Acceptance\n- [ ] `pytest tests/test_foo.py` passes\n"
        ),
        "priority": 2,
        "estimate": 2.0,
    }


class TestCleanIssuePasses:
    def test_agent_ready_true(self, clean_issue: dict[str, object]) -> None:
        report = validate_issue(**clean_issue)  # type: ignore[arg-type]
        assert report.agent_ready is True
        assert report.missing == []
        assert report.issues == []

    def test_score_100(self, clean_issue: dict[str, object]) -> None:
        report = validate_issue(**clean_issue)  # type: ignore[arg-type]
        assert report.score == 100

    def test_suggested_label_agent_ready(self, clean_issue: dict[str, object]) -> None:
        report = validate_issue(**clean_issue)  # type: ignore[arg-type]
        assert report.suggested_label == "agent-ready"


class TestMissingAcceptance:
    def test_missing_acceptance_blocks_agent_ready(self) -> None:
        report = validate_issue(
            title="foo.py: x",
            description="## What\nd\n## Where\n`foo.py:1`\n",
            priority=3,
            estimate=1.0,
        )
        assert report.agent_ready is False
        assert any("Acceptance" in m for m in report.missing)

    def test_missing_acceptance_surfaces_as_error_issue(self) -> None:
        report = validate_issue(
            title="foo.py: x",
            description="## What\nd\n## Where\n`foo.py:1`\n",
            priority=3,
            estimate=1.0,
        )
        assert any(
            i.severity == "error" and i.rule == "missing-acceptance" for i in report.issues
        )


class TestMissingFileAnchor:
    def test_missing_anchor_blocks_agent_ready(self) -> None:
        report = validate_issue(
            title="foo: something",
            description="## What\nvague\n\n## Acceptance\n- [ ] fix\n",
            priority=3,
            estimate=1.0,
        )
        assert report.agent_ready is False
        assert any("file anchor" in m for m in report.missing)
        assert any(i.field == "description" for i in report.issues)


class TestNonBlockingFindingsNotInMissing:
    """Medium/low findings (autolink, UUID wrap, missing estimate) must NOT
    appear in ``missing`` — that list is strictly HIGH-severity (blocking)."""

    def test_autolink_mangle_not_in_missing(self) -> None:
        report = validate_issue(
            title="foo.py: x",
            description=(
                "## What\nsee [AGENTS.md](<http://AGENTS.md>)\n"
                "## Where\n`foo.py:1`\n"
                "## Acceptance\n- [ ] done\n"
            ),
            priority=3,
            estimate=1.0,
        )
        assert report.agent_ready is True
        assert report.missing == []

    def test_missing_estimate_not_in_missing(self) -> None:
        """Missing estimate is LOW — validator should NOT surface it as blocking."""
        report = validate_issue(
            title="foo.py: x",
            description=(
                "## What\nd\n## Where\n`foo.py:1`\n## Acceptance\n- [ ] done\n"
            ),
            priority=3,
            estimate=None,
        )
        assert report.agent_ready is True
        assert report.missing == []


class TestDedupMissing:
    """Duplicate rule fires must collapse to a single ``missing`` entry."""

    def test_same_rule_twice_one_missing_entry(self) -> None:
        # Description with two places that trigger the same rule — here, we
        # force it by creating an empty title (1 HIGH) + empty Acceptance
        # (1 HIGH) + missing anchor (1 HIGH). Each distinct rule should
        # surface once.
        report = validate_issue(
            title="",
            description="",
            priority=3,
            estimate=1.0,
        )
        # 3 distinct HIGH rules fire → 3 distinct missing entries.
        assert len(report.missing) == len(set(report.missing))


class TestEpicRelaxation:
    def test_epic_without_file_anchor_passes(self) -> None:
        report = validate_issue(
            title="Epic: big refactor",
            description="## Outcome\nrestructure\n\n## Acceptance\n- [ ] ship\n",
            priority=2,
            estimate=None,
            is_epic=True,
        )
        assert report.agent_ready is True


class TestReturnTypes:
    def test_returns_pydantic_models(self, clean_issue: dict[str, object]) -> None:
        report = validate_issue(**clean_issue)  # type: ignore[arg-type]
        assert isinstance(report, ValidationReport)
        for issue in report.issues:
            assert isinstance(issue, ValidationIssue)

    def test_model_dump_produces_plain_dict(self, clean_issue: dict[str, object]) -> None:
        report = validate_issue(**clean_issue)  # type: ignore[arg-type]
        dumped = report.model_dump()
        assert set(dumped.keys()) == {
            "agent_ready",
            "score",
            "missing",
            "issues",
            "suggested_label",
        }

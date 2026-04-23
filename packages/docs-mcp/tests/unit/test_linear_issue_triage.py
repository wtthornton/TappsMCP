"""Tests for docs_mcp.triage.linear_issue — batch triage."""

from __future__ import annotations

from typing import Any

import pytest

from docs_mcp.triage.linear_issue import (
    LabelProposal,
    ParentGrouping,
    TriageReport,
    _extract_file_paths,
    triage_issues,
)


def _clean_issue(id_: str, path: str = "packages/foo/foo.py") -> dict[str, Any]:
    """Minimal template-compliant issue payload."""
    return {
        "id": id_,
        "title": f"{path}: short symptom",
        "description": (
            f"## What\nbreaks\n\n"
            f"## Where\n`{path}:12-20`\n\n"
            f"## Acceptance\n- [ ] pytest passes\n"
        ),
        "labels": [],
        "priority": 2,
        "estimate": 2.0,
    }


def _bad_issue(id_: str) -> dict[str, Any]:
    """Issue missing Acceptance + anchor — triggers HIGH findings."""
    return {
        "id": id_,
        "title": f"{id_}: vague ask",
        "description": "please clean up memory",
        "labels": [],
        "priority": None,
        "estimate": None,
    }


# ---------------------------------------------------------------------------
# File path extraction
# ---------------------------------------------------------------------------


class TestExtractFilePaths:
    def test_extracts_basic_py_path(self) -> None:
        out = _extract_file_paths("edit packages/foo/bar.py:12 please")
        assert "packages/foo/bar.py" in out

    def test_skips_readme_and_license_noise(self) -> None:
        out = _extract_file_paths("see README.md and LICENSE")
        assert "README.md" not in out
        assert "LICENSE" not in out

    def test_deduplicates_repeated_path(self) -> None:
        out = _extract_file_paths("touch foo.py:1 and foo.py:2 and foo.py:3")
        assert out.count("foo.py") == 1

    def test_extracts_multiple_distinct_paths(self) -> None:
        out = _extract_file_paths("`a.py:1` and `b.ts:2` and `c.go:3`")
        assert {"a.py", "b.ts", "c.go"}.issubset(set(out))

    def test_no_paths_returns_empty(self) -> None:
        assert _extract_file_paths("nothing here") == []


# ---------------------------------------------------------------------------
# Per-issue triage results
# ---------------------------------------------------------------------------


class TestPerIssueResults:
    def test_returns_result_per_input(self) -> None:
        report = triage_issues(
            [_clean_issue("TAP-1"), _clean_issue("TAP-2"), _bad_issue("TAP-3")]
        )
        assert [r.id for r in report.per_issue] == ["TAP-1", "TAP-2", "TAP-3"]

    def test_clean_issue_is_agent_ready(self) -> None:
        report = triage_issues([_clean_issue("TAP-1")])
        assert report.per_issue[0].agent_ready is True
        assert report.per_issue[0].suggested_label == "spec-ready"

    def test_bad_issue_not_agent_ready(self) -> None:
        report = triage_issues([_bad_issue("TAP-3")])
        assert report.per_issue[0].agent_ready is False
        assert report.per_issue[0].suggested_label == "needs-spec"

    def test_current_agent_label_extracted(self) -> None:
        issue = _clean_issue("TAP-1")
        issue["labels"] = ["Bug", "spec-ready"]
        report = triage_issues([issue])
        assert report.per_issue[0].current_agent_label == "spec-ready"

    def test_current_agent_label_empty_when_none_set(self) -> None:
        issue = _clean_issue("TAP-1")
        issue["labels"] = ["Bug"]
        report = triage_issues([issue])
        assert report.per_issue[0].current_agent_label == ""


# ---------------------------------------------------------------------------
# Label proposals
# ---------------------------------------------------------------------------


class TestLabelProposals:
    def test_no_proposal_when_current_matches_suggested(self) -> None:
        issue = _clean_issue("TAP-1")
        issue["labels"] = ["spec-ready"]
        report = triage_issues([issue])
        assert report.label_proposals == []

    def test_proposal_when_current_differs(self) -> None:
        issue = _clean_issue("TAP-1")
        issue["labels"] = ["needs-spec"]  # Stale — should become spec-ready.
        report = triage_issues([issue])
        assert len(report.label_proposals) == 1
        p = report.label_proposals[0]
        assert p.from_label == "needs-spec"
        assert p.to_label == "spec-ready"

    def test_proposal_when_no_current_agent_label(self) -> None:
        issue = _clean_issue("TAP-1")
        issue["labels"] = ["Bug"]  # No agent label at all.
        report = triage_issues([issue])
        assert len(report.label_proposals) == 1
        assert report.label_proposals[0].from_label == ""
        assert report.label_proposals[0].to_label == "spec-ready"

    def test_bad_issue_proposes_needs_clarification_with_reason(self) -> None:
        report = triage_issues([_bad_issue("TAP-3")])
        assert len(report.label_proposals) == 1
        p = report.label_proposals[0]
        assert p.to_label == "needs-spec"
        assert "Missing" in p.reason


# ---------------------------------------------------------------------------
# Parent groupings
# ---------------------------------------------------------------------------


class TestParentGroupings:
    def test_two_issues_on_same_path_get_grouped(self) -> None:
        report = triage_issues(
            [
                _clean_issue("TAP-1", "packages/foo/upgrade.py"),
                _clean_issue("TAP-2", "packages/foo/upgrade.py"),
            ]
        )
        assert len(report.parent_groupings) == 1
        g = report.parent_groupings[0]
        assert g.shared_path == "packages/foo/upgrade.py"
        assert set(g.issue_ids) == {"TAP-1", "TAP-2"}
        assert "upgrade.py" in g.proposed_parent_title

    def test_singleton_path_not_grouped(self) -> None:
        report = triage_issues([_clean_issue("TAP-1", "packages/foo/only.py")])
        assert report.parent_groupings == []

    def test_multiple_clusters_sorted_by_size(self) -> None:
        issues = [
            _clean_issue("TAP-1", "packages/big/a.py"),
            _clean_issue("TAP-2", "packages/big/a.py"),
            _clean_issue("TAP-3", "packages/big/a.py"),
            _clean_issue("TAP-4", "packages/small/b.py"),
            _clean_issue("TAP-5", "packages/small/b.py"),
        ]
        report = triage_issues(issues)
        assert len(report.parent_groupings) == 2
        # Largest cluster first.
        assert report.parent_groupings[0].shared_path == "packages/big/a.py"
        assert len(report.parent_groupings[0].issue_ids) == 3


# ---------------------------------------------------------------------------
# Metadata gaps
# ---------------------------------------------------------------------------


class TestMetadataGaps:
    def test_no_priority_listed(self) -> None:
        issue = _clean_issue("TAP-1")
        issue["priority"] = None
        report = triage_issues([issue])
        assert "TAP-1" in report.metadata_gaps.no_priority

    def test_no_estimate_listed(self) -> None:
        issue = _clean_issue("TAP-1")
        issue["estimate"] = None
        report = triage_issues([issue])
        assert "TAP-1" in report.metadata_gaps.no_estimate

    def test_epic_estimate_gap_excluded(self) -> None:
        issue = _clean_issue("TAP-1")
        issue["estimate"] = None
        issue["is_epic"] = True
        report = triage_issues([issue])
        assert "TAP-1" not in report.metadata_gaps.no_estimate

    def test_priority_zero_treated_as_gap(self) -> None:
        issue = _clean_issue("TAP-1")
        issue["priority"] = 0  # Linear "None" priority.
        report = triage_issues([issue])
        assert "TAP-1" in report.metadata_gaps.no_priority


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


class TestSummary:
    def test_summary_counts_match(self) -> None:
        report = triage_issues(
            [_clean_issue("TAP-1"), _clean_issue("TAP-2"), _bad_issue("TAP-3")]
        )
        assert report.summary.total == 3
        assert report.summary.agent_ready == 2
        assert report.summary.needs_clarification == 1
        assert report.summary.agent_blocked == 0
        assert 0 < report.summary.avg_score < 100

    def test_empty_input(self) -> None:
        report = triage_issues([])
        assert report.summary.total == 0
        assert report.summary.avg_score == 0.0


# ---------------------------------------------------------------------------
# Return types
# ---------------------------------------------------------------------------


class TestReturnTypes:
    def test_returns_pydantic_report(self) -> None:
        report = triage_issues([_clean_issue("TAP-1")])
        assert isinstance(report, TriageReport)

    def test_proposals_are_pydantic(self) -> None:
        issue = _clean_issue("TAP-1")
        issue["labels"] = ["needs-spec"]
        report = triage_issues([issue])
        for p in report.label_proposals:
            assert isinstance(p, LabelProposal)

    def test_groupings_are_pydantic(self) -> None:
        issues = [
            _clean_issue("TAP-1", "a.py"),
            _clean_issue("TAP-2", "a.py"),
        ]
        report = triage_issues(issues)
        for g in report.parent_groupings:
            assert isinstance(g, ParentGrouping)

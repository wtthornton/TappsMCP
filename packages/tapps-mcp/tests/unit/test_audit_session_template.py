"""Tests for the audit_session_template module.

Covers:
  - DigestTicket: label defaults (TAP-2719)
  - DigestFinding: construction
  - render_digest_ticket: title, body structure, labels, edge cases
  - render_session_ticket: label defaults (audit-readonly)
  - render_campaign_epic: sanity check
"""

from __future__ import annotations

import re

import pytest

from tapps_mcp.tools.audit_session_template import (
    DigestFinding,
    DigestTicket,
    SessionTicket,
    _normalise_anchor,
    render_digest_ticket,
    render_session_ticket,
)

# ---------------------------------------------------------------------------
# _normalise_anchor
# ---------------------------------------------------------------------------


class TestNormaliseAnchor:
    def test_preserves_line_range(self) -> None:
        assert _normalise_anchor("src/foo.py:10-25") == "src/foo.py:10-25"

    def test_preserves_single_line(self) -> None:
        assert _normalise_anchor("src/foo.py:42") == "src/foo.py:42"

    def test_appends_one_to_bare_path(self) -> None:
        assert _normalise_anchor("src/foo.py") == "src/foo.py:1"

    def test_strips_whitespace(self) -> None:
        assert _normalise_anchor("  src/bar.py:5  ") == "src/bar.py:5"

    def test_bare_path_stripped_gets_suffix(self) -> None:
        assert _normalise_anchor("  src/baz.ts  ") == "src/baz.ts:1"


# ---------------------------------------------------------------------------
# SessionTicket — label defaults
# ---------------------------------------------------------------------------


class TestSessionTicketLabels:
    def test_default_label_is_audit_readonly(self) -> None:
        ticket = SessionTicket(title="audit: cluster #1", body="body")
        assert ticket.labels == ["audit-readonly"]

    def test_labels_list(self) -> None:
        ticket = SessionTicket(title="t", body="b")
        assert isinstance(ticket.labels, list)


# ---------------------------------------------------------------------------
# DigestTicket — label defaults (TAP-2719)
# ---------------------------------------------------------------------------


class TestDigestTicketLabels:
    def test_default_labels_contain_not_implementable(self) -> None:
        ticket = DigestTicket(title="audit-digest session #1: 2 P2/P3 findings", body="body")
        assert "not-implementable" in ticket.labels

    def test_default_labels_contain_audit_readonly(self) -> None:
        ticket = DigestTicket(title="t", body="b")
        assert "audit-readonly" in ticket.labels

    def test_default_labels_are_list(self) -> None:
        ticket = DigestTicket(title="t", body="b")
        assert isinstance(ticket.labels, list)

    def test_custom_labels_override_default(self) -> None:
        ticket = DigestTicket(title="t", body="b", labels=["custom"])
        assert ticket.labels == ["custom"]


# ---------------------------------------------------------------------------
# DigestFinding — construction
# ---------------------------------------------------------------------------


class TestDigestFinding:
    def test_basic_construction(self) -> None:
        f = DigestFinding(
            severity="P2",
            category="style",
            files=["src/utils.py:1-50"],
            evidence="unused import `os`",
            recommendation="remove unused import",
        )
        assert f.severity == "P2"
        assert f.category == "style"
        assert "src/utils.py:1-50" in f.files

    def test_p3_severity(self) -> None:
        f = DigestFinding(
            severity="P3",
            category="docs",
            files=["src/api.py:1"],
            evidence="public function missing docstring",
            recommendation="add docstring",
        )
        assert f.severity == "P3"


# ---------------------------------------------------------------------------
# render_digest_ticket — structure
# ---------------------------------------------------------------------------


_SAMPLE_FINDINGS = [
    DigestFinding(
        severity="P2",
        category="style",
        files=["packages/tapps-mcp/src/tapps_mcp/utils.py:10-30"],
        evidence="unused import `os` at line 10 (vulture)",
        recommendation="Remove unused import",
    ),
    DigestFinding(
        severity="P3",
        category="docs",
        files=["packages/tapps-mcp/src/tapps_mcp/utils.py:50-80"],
        evidence="public function `parse_config` has no docstring",
        recommendation="Add docstring describing parameters and return value",
    ),
]


class TestRenderDigestTicket:
    def setup_method(self) -> None:
        self.ticket = render_digest_ticket(
            session_index=3,
            parent_ref="TAP-2040",
            findings=_SAMPLE_FINDINGS,
        )

    def test_returns_digest_ticket(self) -> None:
        assert isinstance(self.ticket, DigestTicket)

    def test_title_contains_session_index(self) -> None:
        assert "3" in self.ticket.title

    def test_title_le_80_chars(self) -> None:
        assert len(self.ticket.title) <= 80

    def test_title_contains_finding_count(self) -> None:
        assert "2" in self.ticket.title

    def test_title_contains_digest_keyword(self) -> None:
        assert "audit-digest" in self.ticket.title.lower()

    def test_body_has_five_sections(self) -> None:
        for section in ("## What", "## Where", "## Why", "## Acceptance", "## Refs"):
            assert section in self.ticket.body

    def test_body_has_checkbox(self) -> None:
        assert "- [ ]" in self.ticket.body

    def test_body_contains_file_anchor(self) -> None:
        anchor_re = re.compile(r"[\w./\\-]+\.py:\d+(?:-\d+)?")
        assert anchor_re.search(self.ticket.body)

    def test_body_contains_parent_ref(self) -> None:
        assert "TAP-2040" in self.ticket.body

    def test_body_ends_with_newline(self) -> None:
        assert self.ticket.body.endswith("\n")

    def test_body_contains_evidence(self) -> None:
        assert "unused import" in self.ticket.body

    def test_body_contains_category(self) -> None:
        assert "style" in self.ticket.body

    def test_body_mentions_finding_to_story(self) -> None:
        assert "tapps_finding_to_story" in self.ticket.body


# ---------------------------------------------------------------------------
# render_digest_ticket — TAP-2719 label assertions
# ---------------------------------------------------------------------------


class TestRenderDigestTicketLabels:
    def test_not_implementable_label_present(self) -> None:
        """TAP-2719: digest tickets must carry the not-implementable label."""
        ticket = render_digest_ticket(
            session_index=1,
            parent_ref="TAP-2040",
            findings=_SAMPLE_FINDINGS,
        )
        assert "not-implementable" in ticket.labels

    def test_audit_readonly_label_present(self) -> None:
        ticket = render_digest_ticket(
            session_index=1,
            parent_ref="TAP-2040",
            findings=_SAMPLE_FINDINGS,
        )
        assert "audit-readonly" in ticket.labels

    def test_labels_are_list(self) -> None:
        ticket = render_digest_ticket(
            session_index=1,
            parent_ref="TAP-2040",
            findings=_SAMPLE_FINDINGS,
        )
        assert isinstance(ticket.labels, list)

    def test_labels_not_empty(self) -> None:
        ticket = render_digest_ticket(
            session_index=1,
            parent_ref="TAP-2040",
            findings=_SAMPLE_FINDINGS,
        )
        assert len(ticket.labels) >= 2


# ---------------------------------------------------------------------------
# render_digest_ticket — edge cases
# ---------------------------------------------------------------------------


class TestRenderDigestTicketEdgeCases:
    def test_raises_on_empty_findings(self) -> None:
        with pytest.raises(ValueError, match="findings"):
            render_digest_ticket(
                session_index=1,
                parent_ref="TAP-2040",
                findings=[],
            )

    def test_single_finding(self) -> None:
        ticket = render_digest_ticket(
            session_index=1,
            parent_ref="TAP-2040",
            findings=[_SAMPLE_FINDINGS[0]],
        )
        assert "## What" in ticket.body
        assert "1 finding" in ticket.body

    def test_bare_file_path_gets_anchor(self) -> None:
        finding = DigestFinding(
            severity="P2",
            category="style",
            files=["src/bare_module.py"],  # no :LINE
            evidence="issue here",
            recommendation="fix it",
        )
        ticket = render_digest_ticket(
            session_index=2,
            parent_ref="TAP-9000",
            findings=[finding],
        )
        # Must have a line-anchored reference
        assert "src/bare_module.py:1" in ticket.body

    def test_deduplicates_files_across_findings(self) -> None:
        shared_file = "src/shared.py:1-100"
        f1 = DigestFinding(
            severity="P2",
            category="style",
            files=[shared_file],
            evidence="ev1",
            recommendation="rec1",
        )
        f2 = DigestFinding(
            severity="P3",
            category="docs",
            files=[shared_file, "src/other.py:5"],
            evidence="ev2",
            recommendation="rec2",
        )
        ticket = render_digest_ticket(
            session_index=1,
            parent_ref="TAP-2040",
            findings=[f1, f2],
        )
        # shared_file should appear only once in ## Where
        where_section = ticket.body.split("## Why")[0]
        assert where_section.count(shared_file) == 1

    def test_long_finding_list_title_truncated(self) -> None:
        """Title must never exceed 80 chars even with large session indices."""
        ticket = render_digest_ticket(
            session_index=9999,
            parent_ref="TAP-1",
            findings=_SAMPLE_FINDINGS * 100,
        )
        assert len(ticket.title) <= 80

    def test_no_parent_ref_is_ok(self) -> None:
        ticket = render_digest_ticket(
            session_index=1,
            parent_ref="",
            findings=[_SAMPLE_FINDINGS[0]],
        )
        assert "## Acceptance" in ticket.body

    def test_multi_category_findings(self) -> None:
        findings = [
            DigestFinding(
                severity="P2",
                category="security",
                files=["src/a.py:1"],
                evidence="weak hash",
                recommendation="use sha256",
            ),
            DigestFinding(
                severity="P3",
                category="performance",
                files=["src/b.py:10"],
                evidence="quadratic loop",
                recommendation="use set lookup",
            ),
        ]
        ticket = render_digest_ticket(
            session_index=5,
            parent_ref="TAP-2040",
            findings=findings,
        )
        # Both categories should be mentioned in the refs
        assert "security" in ticket.body
        assert "performance" in ticket.body


# ---------------------------------------------------------------------------
# render_digest_ticket — validation against docs-mcp validator
# ---------------------------------------------------------------------------


class TestDigestTicketAgentReadyValidation:
    """Verify render_digest_ticket body is agent_ready by construction."""

    def test_body_passes_docs_validate(self) -> None:
        from docs_mcp.validators.linear_issue import validate_issue

        ticket = render_digest_ticket(
            session_index=2,
            parent_ref="TAP-2040",
            findings=_SAMPLE_FINDINGS,
        )
        report = validate_issue(title=ticket.title, description=ticket.body)
        assert report.agent_ready, (
            f"DigestTicket body is NOT agent_ready: {report.missing}"
        )


# ---------------------------------------------------------------------------
# render_session_ticket — Done-state instruction (TAP-2785)
# ---------------------------------------------------------------------------


def _make_chunk():  # type: ignore[return]
    from tapps_mcp.tools.audit_chunker import AuditChunk

    return AuditChunk(
        session_index=1,
        files=["packages/tapps-mcp/src/tapps_mcp/server.py"],
        modules=["tapps_mcp.server"],
        rationale="single-module cluster",
        intra_edges=0,
        boundary_edges=2,
    )


class TestRenderSessionTicketDoneInstruction:
    """Verify the session ticket body instructs agents to set state=Done (TAP-2785)."""

    def setup_method(self) -> None:
        chunk = _make_chunk()
        self.ticket = render_session_ticket(
            chunk,
            campaign_id="campaign-abc123",
            epic_ref="TAP-2036",
            commit_sha="deadbeef",
            categories=["quality"],
            file_line_counts={"packages/tapps-mcp/src/tapps_mcp/server.py": 200},
        )

    def test_acceptance_contains_done_state(self) -> None:
        """## Acceptance must instruct executor to set ticket state to Done."""
        assert "Done" in self.ticket.body

    def test_acceptance_contains_save_issue_call(self) -> None:
        """## Acceptance must include the save_issue mechanism."""
        assert "save_issue" in self.ticket.body

    def test_acceptance_warns_against_in_progress(self) -> None:
        """## Acceptance must warn about leaving ticket In Progress."""
        assert "In Progress" in self.ticket.body

    def test_constraints_contain_done_instruction(self) -> None:
        """### Constraints must spell out the Done transition."""
        constraints = self.ticket.body.split("### Constraints")[1]
        assert "Done" in constraints

    def test_constraints_warn_against_in_progress(self) -> None:
        """Constraints must mention the re-selection risk."""
        constraints = self.ticket.body.split("### Constraints")[1]
        assert "In Progress" in constraints

    def test_body_does_not_say_close_this_ticket(self) -> None:
        """The ambiguous 'close this ticket' phrase must not appear (TAP-2785)."""
        assert "close this ticket" not in self.ticket.body

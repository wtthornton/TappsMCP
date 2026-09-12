"""Acceptance tests for orchestration-prompt rules 8-12 (lane orch-prompt-rules, 2026-09-12).

Five rules were measured on a real nine-lane two-repo program and ported upstream from
a consuming project's local skill region so every consuming project — not just the one
that discovered them — gets the fix. Everything here is asserted against files
*generated into a tmp consumer root*, never against the source constants, per this
lane's brief: a generator that stops deploying its own text is the failure mode these
tests exist to catch.

Rule 10 (delete the blanket merge-gating tier row) has its own acceptance tests in
``test_orchestration_tiering_and_parallelization.py`` (``TestProofShapeTierTable`` /
``TestTemplateVerifierRows``) since that module already owns the proof-shape-table
fixtures; this module covers rules 8, 8b, 9, 11, and 12.
"""

from __future__ import annotations

import pytest

from tapps_mcp.pipeline.platform_skills import generate_skills

SKILL = "orchestration-prompt"


@pytest.fixture
def skill_dir(tmp_path):
    generate_skills(tmp_path, "claude")
    return tmp_path / ".claude" / "skills" / SKILL


@pytest.fixture
def full_surface(skill_dir):
    """The union of every reference file rules 8-12 could land in."""
    skill_md = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    references = "references"
    parts = [skill_md]
    for name in (
        "method-detail.md",
        "field-rules-and-rulings.md",
        "verification-routing.md",
        "guardrails-and-contracts.md",
    ):
        parts.append((skill_dir / references / name).read_text(encoding="utf-8"))
    return "\n".join(parts)


@pytest.fixture
def template(skill_dir):
    return (skill_dir / "assets" / "prompt-template.md").read_text(encoding="utf-8")


class TestRule8ContractFromBoxes:
    """Rule 8 — a VAL row is not the issue's acceptance criteria.

    Three sub-rules, all required to reach generated output.
    """

    def test_denominator_is_boxes_not_issues(self, full_surface):
        flat = " ".join(full_surface.split())
        assert "denominator is boxes, not issues" in flat

    def test_12_of_22_measurement_and_wrong_close_present(self, full_surface):
        flat = " ".join(full_surface.split())
        assert "12 of 22 acceptance checkboxes" in flat
        assert "marked Done on a green verification id" in flat

    def test_decision_boxes_get_their_own_decide_ticket(self, full_surface):
        assert "gets its own decide ticket at triage" in full_surface

    def test_template_validation_contract_built_from_boxes(self, template):
        contract = template.split("\n## Validation contract", 1)[1].split("\n## ", 1)[0]
        assert "Build this contract from the in-scope issues' `- [ ]` boxes" in contract
        assert "denominator in the coverage table is **boxes**, not issues" in contract

    def test_template_triage_sub_goal_carves_out_decision_boxes(self, template):
        sub_goals = template.split("\n## Sub-goals", 1)[1].split("\n## ", 1)[0]
        triage = sub_goals.split("Triage the queue before executing any of it.", 1)[1]
        triage = triage.split("\n2.", 1)[0]
        assert "gets its own decide ticket now" in triage


class TestRule8bBoxByBoxAudit:
    """Rule 8b — box-by-box audit before close, with a verdict vocabulary."""

    def test_verdict_vocabulary_present(self, full_surface):
        for verdict in ("`YES`", "`NO`", "`PARTIAL`", "`NOT-CODE`"):
            assert verdict in full_surface

    def test_per_yes_evidence_requirement_stated(self, full_surface):
        assert "each `YES` carrying a `file:line`" in full_surface or (
            "each `YES`" in full_surface and "file:line" in full_surface
        )

    def test_extends_rule_7_rather_than_duplicating(self, full_surface):
        """The honesty rule (unticked-and-silent) and the box audit both live under
        the same numbered rule 7 — this is an extension, not a competing rule."""
        rule_7 = full_surface.split(
            "**Never read tracker state as evidence that work happened.**", 1
        )[1].split("\n8. ", 1)[0]
        flat = " ".join(rule_7.split())
        assert "unticked-and-silent is the only version that is not honest" in flat
        assert "audit every box before any close" in flat

    def test_placed_as_a_done_when_clause_in_template(self, template):
        done_when = template.split("\n## Done-when", 1)[1].split("\n## ", 1)[0]
        assert "box-by-box close audit" in done_when
        assert "`YES` / `NO` / `PARTIAL` / `NOT-CODE`" in done_when


class TestRule9MeasureGateAtBase:
    """Rule 9 — every Done-when gate is measured at base before it is written down."""

    def test_distinguished_from_field_rule_3(self, full_surface):
        rule_3 = full_surface.split(
            "**The verifier's control is the pre-change tree, not the fix's own tests.**",
            1,
        )[1].split("\n4. ", 1)[0]
        assert "governs a fix's proof at verify time" in rule_3
        assert "governs\n   a Done-when gate at authoring time" in rule_3

    def test_typecheck_and_page_minimum_measurements_present(self, full_surface):
        assert "265 errors at base" in full_surface
        assert "`PAGE_MINIMUM = 30`" in full_surface
        assert "real value" in full_surface and "**15**" in full_surface

    def test_identity_diff_not_exit_zero(self, full_surface):
        assert "error-**identity** diff" in full_surface
        assert "counts are not identities" in full_surface


class TestRule11CarryForward:
    """Rule 11 — a fix round verifies the delta, not the whole lane again."""

    def test_extends_field_rule_9_rather_than_a_second_rule(self, full_surface):
        rule_9 = full_surface.split(
            "**Round-2 fix prompts gate on the delta and also sweep siblings by symbol.**",
            1,
        )[1].split("\n10. ", 1)[0]
        assert "states, explicitly, which rows are already verified" in rule_9
        assert "re-verifier is handed the same list" in rule_9

    def test_cost_measurement_present(self, full_surface):
        assert "$9.99 against $4.09" in full_surface


class TestRule12SelfGrepObligation:
    """Rule 12 — the author greps their own brief before dispatching."""

    def test_self_grep_obligation_stated(self, template):
        loop = template.split("\n## Loop", 1)[1].split("\n## ", 1)[0]
        verify = loop.split("- **Verify (independent):**", 1)[1].split("\n- ", 1)[0]
        assert "grep your own brief" in verify

    def test_measurement_present(self, template):
        loop = template.split("\n## Loop", 1)[1].split("\n## ", 1)[0]
        verify = loop.split("- **Verify (independent):**", 1)[1].split("\n- ", 1)[0]
        assert "36 of that verifier's 77 minutes" in verify
        assert "403 failures that were byte-identical at base" in verify

    def test_nlt_orchestrator_script_referenced_as_existing_only(self, template):
        loop = template.split("\n## Loop", 1)[1].split("\n## ", 1)[0]
        verify = loop.split("- **Verify (independent):**", 1)[1].split("\n- ", 1)[0]
        assert "scripts/check-orchestration-brief.js" in verify
        assert (
            "an existing implementation to point at, not something every runner can invoke"
            in verify
        )

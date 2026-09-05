"""Reference-file assertions for the orchestration-prompt skill: field rules and verifier-tier rulings (TAP-6858, TAP-6859).

TAP-7017 moved "## Field rules" and "## Rulings" out of the SKILL.md managed
block (which was pushing 19% of a 200k context before any work started) into
``references/field-rules-and-rulings.md``, reachable from SKILL.md by an
explicit pointer under "## Field rules, rulings, and verification routing".
These assertions now read the reference file the emitter produces, not the
managed block.

Split per topic rather than appended to ``test_platform_skills.py``: that module
already sits at the maintainability-index gate floor, and a single combined module
for this cluster reaches it too.
"""

from __future__ import annotations

import pytest

from tapps_mcp.pipeline.platform_skill_orchestration import (
    ORCHESTRATION_PROMPT_COMPANION_FILES as COMPANIONS,
)

_FIELD_RULES_AND_RULINGS = COMPANIONS["references/field-rules-and-rulings.md"]
_METHOD_DETAIL = COMPANIONS["references/method-detail.md"]


class TestFieldRulesTwelve:
    """TAP-6858 — twelve field rules absent from the method, verified by grep."""

    def _field_rules_section(self) -> str:
        body = _FIELD_RULES_AND_RULINGS
        section = body.split("## Field rules", 1)[1]
        return section.split("\n## Rulings", 1)[0]

    @pytest.mark.parametrize(
        "marker",
        [
            "known-bad and a known-positive",
            "Green-by-citation is distinct from green-by-suppression",
            "verifier's control is the pre-change tree",
            "reports the PR's own CI by name and state",
            "measured number is a floor until the instrument is proven",
            "Prove freshness per deployed layer and diff config per key hash",
            "blast-radius preflight before any state-touching verify step",
            "separates queried-and-got-zero from the-query-failed",
            "Round-2 fix prompts gate on the delta and also sweep siblings by symbol",
            "disposition disjunction with",
            "Agreement among artifacts is not corroboration",
            "structural limits are the author's problem",
        ],
    )
    def test_each_field_rule_present(self, marker: str) -> None:
        section = self._field_rules_section()
        assert marker in section, f"missing field rule marker {marker!r}"

    def test_field_rules_are_a_numbered_list_of_twelve(self) -> None:
        section = self._field_rules_section()
        for n in range(1, 13):
            assert f"\n{n}. " in section or section.startswith(f"{n}. ")


class TestVerifierTierAuthorityAndRulings:
    """TAP-6859 — the proof-shape table is authoritative; eight rulings pin edge cases."""

    def test_no_restatement_of_losing_verifier_tier_formulation(self) -> None:
        assert "inherit the runner at high effort" not in _METHOD_DETAIL

    def test_authority_statement_present(self) -> None:
        # "This table is authoritative" refers to the proof-shape tier table in
        # method §5 (the verifier-tiering discussion), which lives in
        # references/method-detail.md — not the field-rules-and-rulings file.
        body = _METHOD_DETAIL
        assert "This table is authoritative" in body
        assert "pin explicitly, for a named reason" in body
        assert "never" in body.split("This table is authoritative", 1)[1][:300]

    def _rulings_section(self) -> str:
        body = _FIELD_RULES_AND_RULINGS
        return body.split("## Rulings", 1)[1]

    @pytest.mark.parametrize(
        "marker",
        [
            "may author a narrow fix and stay on as re-verifier",
            "carve-out naming exactly two exception categories, data-loss and security",
            "Shared quota is a coupling the independence test",
            "Billing topology",
            "Content-diff freshness",
            "Cheap-tier transcription",
            "one named artifact handover to the operator",
            "reserved for the coordination-versus-execution distinction",
        ],
    )
    def test_each_ruling_present(self, marker: str) -> None:
        section = self._rulings_section()
        assert marker in section, f"missing ruling marker {marker!r}"

    def test_eight_rulings_numbered(self) -> None:
        section = self._rulings_section()
        for n in range(1, 9):
            assert f"\n{n}. " in section

    def test_scope_creep_carve_out_requires_loud_reporting(self) -> None:
        section = self._rulings_section()
        ruling_2 = section.split("2. ", 1)[1].split("\n3. ", 1)[0]
        assert "surfaced loudly in the same" in ruling_2
        assert "evidence block" in ruling_2
        assert "never filed and walked past" in ruling_2

    def test_scope_creep_carve_out_leaves_ordinary_problems_unchanged(self) -> None:
        section = self._rulings_section()
        ruling_2 = section.split("2. ", 1)[1].split("\n3. ", 1)[0]
        assert "ordinary adjacent problem" in ruling_2
        assert "separate item, with no change in behaviour" in ruling_2

    def test_scope_creep_carve_out_stops_at_the_two_categories(self) -> None:
        section = self._rulings_section()
        ruling_2 = section.split("2. ", 1)[1].split("\n3. ", 1)[0]
        assert "not a general licence to widen the diff" in ruling_2

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

import re

import pytest

from tapps_mcp.pipeline.platform_skill_orchestration import (
    ORCHESTRATION_PROMPT_COMPANION_FILES as COMPANIONS,
)
from tapps_mcp.pipeline.platform_skill_orchestration import (
    ORCHESTRATION_PROMPT_SKILL_BODY,
    SCOPE_CARVE_OUT_CATEGORIES,
)

_FIELD_RULES_AND_RULINGS = COMPANIONS["references/field-rules-and-rulings.md"]
_METHOD_DETAIL = COMPANIONS["references/method-detail.md"]
_GUARDRAILS_AND_CONTRACTS = COMPANIONS["references/guardrails-and-contracts.md"]
_PROMPT_TEMPLATE = COMPANIONS["assets/prompt-template.md"]
_CARVE_OUT_AND_TEXT = " and ".join(SCOPE_CARVE_OUT_CATEGORIES)


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

    def test_ruling_2_read_by_anchor_not_first_carve_out_hit(self) -> None:
        """TAP-6605 round 2: the SKILL.md summary sentence also contains the
        substring "carve-out" (it restates ruling 2 in one line) before the
        rulings section is ever reached in the raw body constant — a proof that
        greps the whole constant for the first "carve-out" hit lands on that
        restatement, not on ruling 2 itself. The rulings section must instead be
        located by its own anchor, "No-silent-scope-creep", which opens ruling 2
        and appears nowhere else in the file.
        """
        assert ORCHESTRATION_PROMPT_SKILL_BODY.count("carve-out") >= 1
        assert "No-silent-scope-creep" not in ORCHESTRATION_PROMPT_SKILL_BODY
        rulings = self._rulings_section()
        anchor_idx = rulings.index("No-silent-scope-creep")
        ruling_2 = rulings[anchor_idx:].split("\n3. ", 1)[0]
        assert f"exactly two exception categories, {_CARVE_OUT_AND_TEXT}" in ruling_2


def _carve_out_pair_sites() -> dict[str, str]:
    """The four rendered sites that must agree on the carve-out category pair."""
    return {
        "SKILL.md": ORCHESTRATION_PROMPT_SKILL_BODY,
        "references/field-rules-and-rulings.md": _FIELD_RULES_AND_RULINGS,
        "references/guardrails-and-contracts.md": _GUARDRAILS_AND_CONTRACTS,
        "assets/prompt-template.md": _PROMPT_TEMPLATE,
    }


def _sites_agreeing_on_exactly_the_pair(sites: dict[str, str]) -> list[str]:
    """Return the names of sites that do NOT contain the pair, or contain it with
    a third category tacked on via a leading/trailing " and <word>" — the shape a
    silent drift (a hand-added third exception) would take. A site missing the
    phrase entirely also disagrees.
    """
    disagreeing = []
    for name, text in sites.items():
        idx = text.find(_CARVE_OUT_AND_TEXT)
        if idx == -1:
            disagreeing.append(name)
            continue
        before, after = text[:idx], text[idx + len(_CARVE_OUT_AND_TEXT) :]
        if re.search(r"[a-zA-Z-]+ and $", before) or re.search(r"^ and [a-zA-Z-]+", after):
            disagreeing.append(name)
    return disagreeing


class TestScopeCreepCategoryAgreement:
    """TAP-6605 round 2 — one constant, four rendered sites, zero drift.

    The refutation found three answers in the emitted skill: ruling 2 (category
    test, two exceptions), the CARGO paragraph (severity test, no categories at
    all), and the prompt-template Guardrails line (flat "no scope creep", no
    carve-out). All four sites that name the pair now derive it from
    ``SCOPE_CARVE_OUT_CATEGORIES`` — this class proves they still agree, that a
    hand-added third category is actually caught (not just assumed to be), and
    that the CARGO paragraph now names both actors of the two real mechanisms.
    """

    def test_four_sites_agree_on_exactly_the_pair(self) -> None:
        disagreeing = _sites_agreeing_on_exactly_the_pair(_carve_out_pair_sites())
        assert disagreeing == [], f"sites disagree on the carve-out pair: {disagreeing}"

    def test_negative_control_third_category_fails_naming_the_site(self) -> None:
        """A third category silently added to ONE site must fail the agreement
        check and name exactly that site — proving the check actually reads the
        rendered text rather than trusting the shared constant blindly."""
        tampered = dict(_carve_out_pair_sites())
        key = "references/guardrails-and-contracts.md"
        tampered[key] = tampered[key].replace(
            f"in-flight {_CARVE_OUT_AND_TEXT} only",
            f"in-flight {_CARVE_OUT_AND_TEXT} and performance only",
        )
        disagreeing = _sites_agreeing_on_exactly_the_pair(tampered)
        assert disagreeing == [key]

    def test_cargo_names_both_actors_lane_and_driver(self) -> None:
        cargo = _GUARDRAILS_AND_CONTRACTS.split("## Engineering discipline", 1)[1]
        assert "LANE, immediate" in cargo
        assert "DRIVER, announced" in cargo
        assert "the lane does not fix it in flight" in cargo
        assert "FILED by the" in cargo and "ADMITTED by the driver" in cargo

    def test_cargo_resolves_the_verifiers_case(self) -> None:
        """The verifier's exact refuted case: an adjacent Urgent defect that is
        neither data-loss nor security. Ruling 2 → route to a separate item.
        The CARGO paragraph must now say the same thing the ruling says."""
        cargo = _GUARDRAILS_AND_CONTRACTS.split("## Engineering discipline", 1)[1]
        neither_nor = f"neither {SCOPE_CARVE_OUT_CATEGORIES[0]} nor {SCOPE_CARVE_OUT_CATEGORIES[1]}"
        assert f"is {neither_nor} is FILED by the" in cargo

    def test_prompt_template_guardrails_line_has_a_carve_out_not_flat_ban(self) -> None:
        line = [
            item
            for item in _PROMPT_TEMPLATE.splitlines()
            if item.startswith("- Discipline:")
        ]
        assert len(line) == 1
        assert "no silent scope creep" in line[0]
        assert _CARVE_OUT_AND_TEXT in line[0]
        assert "driver's announced call" in line[0]
        assert line[0].rstrip().endswith("call.")

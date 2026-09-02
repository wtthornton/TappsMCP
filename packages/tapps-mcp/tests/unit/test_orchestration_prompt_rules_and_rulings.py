"""Emitted-body assertions for the orchestration-prompt skill: field rules and verifier-tier rulings (TAP-6858, TAP-6859).

Split per topic rather than appended to ``test_platform_skills.py``: that module
already sits at the maintainability-index gate floor, and a single combined module
for this cluster reaches it too.
"""

from __future__ import annotations

import pytest

from tapps_mcp.pipeline.platform_skills import CLAUDE_SKILLS



class TestFieldRulesTwelve:
    """TAP-6858 — twelve field rules absent from the method, verified by grep."""

    def _field_rules_section(self) -> str:
        body = CLAUDE_SKILLS["orchestration-prompt"]
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
        body = CLAUDE_SKILLS["orchestration-prompt"]
        assert "inherit the runner at high effort" not in body

    def test_authority_statement_present(self) -> None:
        body = CLAUDE_SKILLS["orchestration-prompt"]
        assert "This table is authoritative" in body
        assert "pin explicitly, for a named reason" in body
        assert "never" in body.split("This table is authoritative", 1)[1][:300]

    def _rulings_section(self) -> str:
        body = CLAUDE_SKILLS["orchestration-prompt"]
        section = body.split("## Rulings", 1)[1]
        return section.split("\n## Guardrails", 1)[0]

    @pytest.mark.parametrize(
        "marker",
        [
            "may author a narrow fix and stay on as re-verifier",
            "data-loss carve-out",
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

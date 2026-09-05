"""Reference-file assertions for the orchestration-prompt skill: verification
routing and honest reporting (TAP-6948 Story 4).

These rules were working only in a consuming project's region below the END marker,
so they reached no other project. TAP-7017 promoted them into the managed skill and
then, once promoted, moved the section out of SKILL.md's managed block (which was
approaching 20% of a 200k context before any work started) into
``references/verification-routing.md`` — reachable from SKILL.md via an explicit
pointer under "## Field rules, rulings, and verification routing". These tests
now read that reference file, which the emitter regenerates on every
``tapps_upgrade`` exactly like the managed block.
"""

from __future__ import annotations

import pytest

from tapps_mcp.pipeline.platform_skill_orchestration import (
    ORCHESTRATION_PROMPT_COMPANION_FILES as COMPANIONS,
)

_VERIFICATION_ROUTING = COMPANIONS["references/verification-routing.md"]


def _section() -> str:
    body = _VERIFICATION_ROUTING
    return body.split("## Verification routing and honest reporting", 1)[1]


class TestPromotedVerificationRules:
    """TAP-6948 Story 4 — transferable local content merged into the managed block."""

    def test_section_precedes_the_guardrails_cargo(self) -> None:
        # The Guardrails-every-prompt section now lives in a separate reference
        # file (references/guardrails-and-contracts.md); this section's job is
        # simply to exist, in full, ahead of its own next content.
        body = _VERIFICATION_ROUTING
        assert "## Verification routing and honest reporting" in body

    @pytest.mark.parametrize(
        "marker",
        [
            "Route a verifier by the permission its proof needs",
            "Dry-run every string a verifier will execute",
            "Scope verification to the artifact, not to the diff",
            "Give every cross-cutting claim exactly one owner",
            '"Disjoint files" is measured, not argued',
            "Prose is the unguarded surface",
            "Never read tracker state as evidence that work happened",
            '"Blocked" is a first-class lane outcome',
            "Read the spec adversarially before you read the code",
            "Enforcement before remediation deadlocks",
        ],
    )
    def test_each_promoted_rule_present(self, marker: str) -> None:
        assert marker in _section(), f"missing promoted rule {marker!r}"

    def test_ten_rules_numbered(self) -> None:
        section = _section()
        for n in range(1, 11):
            assert f"\n{n}. " in section, f"missing numbered rule {n}"

    def test_identity_read_is_a_send_gate_not_a_merge_gate(self) -> None:
        section = _section()
        assert "The identity read is a SEND gate, not a merge gate" in section
        assert "immediately before the outward step it actually" in section
        assert "Fidelity and identity answer different questions" in section

    def test_explore_cannot_run_a_write_requiring_proof(self) -> None:
        section = _section()
        rule = section.split("Route a verifier by the permission its proof needs", 1)[1]
        assert "cannot run on `Explore`" in rule
        assert "`general-purpose`" in rule
        assert "non-answer" in rule

    def test_reminder_versus_mechanical_refusal(self) -> None:
        flat = " ".join(_section().split())
        assert "ask first whether the *dispatcher* could refuse the thing mechanically" in flat
        assert "an injected rule is still a reminder, and reminders lose to defaults" in flat

    def test_no_consumer_local_references_in_the_promoted_section(self) -> None:
        """Only transferable rules are promoted -- consumer-local paths stay local.

        Scoped to the promoted section: the managed block carries older
        consumer-local references (``scripts/measure.py``, ``scripts/gitfacts.sh``)
        that predate this promotion and are not in this change's scope.
        """
        section = _section()
        for local in (
            "nlt-orchestrator",
            "fleet.md",
            "fleet.paths.json",
            "scripts/measure.py",
            "scripts/gitfacts.sh",
            "check-learnings-sync",
            "WebStoreDNA",
            "agent-to-agent.md",
            "TAP-",
        ):
            assert local not in section, f"consumer-local reference {local!r} leaked upstream"

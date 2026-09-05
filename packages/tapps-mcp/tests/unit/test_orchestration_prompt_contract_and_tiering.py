"""Emitted-body assertions for the orchestration-prompt skill: terminal contract and cheapest-viable tiering (TAP-6946, TAP-6947).

Split per topic rather than appended to ``test_platform_skills.py``: that module
already sits at the maintainability-index gate floor, and a single combined module
for this cluster reaches it too.
"""

from __future__ import annotations

import pytest

from tapps_mcp.pipeline.platform_skill_orchestration import (
    ORCHESTRATION_PROMPT_COMPANION_FILES as COMPANIONS,
)
from tapps_mcp.pipeline.platform_skills import CLAUDE_SKILLS

# TAP-7017: most method elaboration, the Guardrails-every-prompt list, and the
# Autonomy/Failure-handling/Expected-fail/Engineering-discipline cargo sections
# moved out of the SKILL.md managed block into reference files, each reachable
# from SKILL.md by an explicit pointer. This flattens the whole disclosure
# surface back into one string, in the same relative order the managed block
# used to hold it in, so ordering assertions between (e.g.) "## Terminal
# contract" and "## Autonomy contract" still hold.
_FULL_SURFACE = "\n".join(
    [
        CLAUDE_SKILLS["orchestration-prompt"],
        COMPANIONS["references/method-detail.md"],
        COMPANIONS["references/field-rules-and-rulings.md"],
        COMPANIONS["references/verification-routing.md"],
        COMPANIONS["references/guardrails-and-contracts.md"],
        COMPANIONS["references/learnings-protocol.md"],
        COMPANIONS["references/multi-session-programs.md"],
    ]
)


class TestTerminalContract:
    """TAP-6946 — the skill authors prompts and must never implement the work."""

    def test_terminal_contract_precedes_the_autonomy_contract(self) -> None:
        body = _FULL_SURFACE
        assert "## Terminal contract" in body
        assert body.index("## Terminal contract") < body.index("## Autonomy contract")

    def test_states_it_authors_and_never_implements(self) -> None:
        body = _FULL_SURFACE
        section = body.split("## Terminal contract", 1)[1].split("\n## ", 1)[0]
        assert "AUTHORS a prompt" in section
        assert "never implements the work" in section

    def test_work_order_shaped_input_is_not_authorization_to_implement(self) -> None:
        body = _FULL_SURFACE
        section = body.split("## Terminal contract", 1)[1].split("\n## ", 1)[0]
        assert "work-order-shaped" in section
        assert "Autonomy is about not pausing, not about scope." in section

    def test_names_the_only_permitted_writes(self) -> None:
        body = _FULL_SURFACE
        section = body.split("## Terminal contract", 1)[1].split("\n## ", 1)[0]
        assert "The only writes you may perform" in section
        for allowed in ("`prompts/<slug>.md`", "`.claude/workflows/<slug>.js`", "`learnings.md`"):
            assert allowed in section

    def test_cargo_convention_is_explained_once(self) -> None:
        body = _FULL_SURFACE
        section = body.split("## Terminal contract", 1)[1].split("\n## ", 1)[0]
        assert "**Cargo convention.**" in section
        assert "> **CARGO" in section

    @pytest.mark.parametrize(
        "heading",
        [
            "## Guardrails every emitted prompt must carry",
            "## Autonomy contract (every emitted prompt carries this)",
            "## Failure handling (diagnose, don't repeat)",
            "## Expected-fail fix loop (Missions-inspired)",
            "## Engineering discipline (emit in every prompt's guardrails)",
        ],
    )
    def test_every_cargo_section_is_marked_as_cargo(self, heading: str) -> None:
        body = _FULL_SURFACE
        assert heading in body, f"missing cargo section {heading!r}"
        following = body.split(heading, 1)[1][:200]
        assert "> **CARGO" in following, f"{heading!r} is not marked as cargo"

    def test_completeness_check_asserts_no_stray_writes(self) -> None:
        body = _FULL_SURFACE
        output = body.split("## Output", 1)[1].split("\n## ", 1)[0]
        assert "assert no files were written outside" in output

    def test_output_has_a_required_final_launch_block_step(self) -> None:
        body = _FULL_SURFACE
        output = body.split("## Output", 1)[1].split("\n## ", 1)[0]
        step9 = output.split("\n9. ", 1)[1]
        assert "Launch block" in step9
        assert "/model sonnet" in step9
        assert "/effort medium" in step9
        assert "Read prompts/<slug>.md in full" in step9
        assert "Do not create a branch" in step9

    def test_template_how_to_run_carries_a_session_setup_line(self) -> None:
        template = COMPANIONS["assets/prompt-template.md"]
        section = template.split("\n## How to run (cold start", 1)[1].split("\n## ", 1)[0]
        assert "Session setup" in section
        assert "`/model <model>`" in section
        assert "`/effort <effort>`" in section


class TestCheapestViableTiering:
    """TAP-6947 — a stated floor, a visible SCORE line, and tracker discipline."""

    def test_tiering_states_a_floor_and_requires_a_stated_reason(self) -> None:
        body = _FULL_SURFACE
        assert "**Floor first; escalate only with a stated reason.**" in body
        section = body.split("**Floor first; escalate only with a stated reason.**", 1)[1][:1200]
        assert "one-clause reason in the same Plane-map row" in section
        assert "unpriced default" in section

    def test_emitted_runner_default_is_sonnet_medium(self) -> None:
        body = _FULL_SURFACE
        section = body.split("**Floor first; escalate only with a stated reason.**", 1)[1][:1200]
        assert "the emitted runner default is `sonnet` + `medium`" in section

    def test_escalation_criteria_are_named_not_assumed(self) -> None:
        body = _FULL_SURFACE
        section = body.split("**Floor first; escalate only with a stated reason.**", 1)[1][:1200]
        flat = " ".join(section.split())
        for criterion in ("gates a merge", "open judgement", "cheaper tier failed this step twice"):
            assert criterion in flat

    def test_proof_shape_table_still_governs_verifier_tiers(self) -> None:
        body = _FULL_SURFACE
        section = body.split("**Floor first; escalate only with a stated reason.**", 1)[1][:1600]
        assert "a change in posture, not in rigour" in section
        assert "never yields a cheap *verdict* on an irreversible" in section

    def test_template_plane_map_carries_the_floor(self) -> None:
        template = COMPANIONS["assets/prompt-template.md"]
        plane = template.split("\n## Plane map", 1)[1].split("\n## ", 1)[0]
        assert "**Floor and justify.**" in plane
        assert "`sonnet` + `medium`" in plane

    def test_full_suite_runs_are_deferred_to_program_end(self) -> None:
        body = _FULL_SURFACE
        guardrails = body.split("## Guardrails every emitted prompt must carry", 1)[1]
        guardrails = guardrails.split("\n## ", 1)[0]
        assert "no regression or full-suite run until the plan is complete" in guardrails
        assert "only the tests the change adds or touches" in guardrails
        assert "One\n  full **enumeration** per wave" in guardrails
        assert "exactly one regression run at program\n  end" in guardrails

    def test_score_line_carries_pct_with_denominator_and_elapsed(self) -> None:
        template = COMPANIONS["assets/prompt-template.md"]
        assert "pct <n>%" in template
        assert "elapsed <hh:mm>" in template
        score = template.split("- **Print every iteration:**", 1)[1].split("\n- ", 1)[0]
        assert "countable population" in score
        assert "never an estimate of effort remaining" in score
        assert "wall-clock since kickoff" in score

    def test_skill_body_requires_pct_and_elapsed_on_the_score_line(self) -> None:
        body = _FULL_SURFACE
        assert "`pct <n>%` and `elapsed`" in body

    def test_template_emits_a_queue_triage_subgoal_before_execution(self) -> None:
        template = COMPANIONS["assets/prompt-template.md"]
        subgoals = template.split("\n## Sub-goals", 1)[1].split("\n## ", 1)[0]
        triage = subgoals.split("Triage the queue before executing any of it.", 1)[1]
        assert "disposition" in triage
        assert "duplicate-of-<id>" in triage
        assert "every id is dispositioned, not merely read" in triage
        # It runs before the execution sub-goals.
        assert subgoals.index("Triage the queue") < subgoals.index("<narrow, verifiable execution>")

    def test_done_when_requires_every_touched_issue_to_end_terminal(self) -> None:
        template = COMPANIONS["assets/prompt-template.md"]
        done = template.split("\n## Done-when", 1)[1].split("\n## ", 1)[0]
        assert "every touched issue ends **terminal**" in done
        assert "Cancelled with a written reason" in done
        assert "The **driver** performs these writes" in done

    def test_scope_rule_permits_announced_admission_of_urgent_and_high(self) -> None:
        body = _FULL_SURFACE
        section = body.split("**Scope admission is announced, not forbidden.**", 1)[1][:1200]
        assert "walk past a live Urgent" in section
        assert "**Urgent or High**" in section
        assert "SCORE denominator" in section
        assert "What stays forbidden is the *silent* version" in section

    def test_flat_no_scope_creep_is_no_longer_the_last_word(self) -> None:
        body = _FULL_SURFACE
        assert "no silent scope creep." in body
        after = body.split("no silent scope creep.", 1)[1][:200]
        assert "announced, not forbidden" in after

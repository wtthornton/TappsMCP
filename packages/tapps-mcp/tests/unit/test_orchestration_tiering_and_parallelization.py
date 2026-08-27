"""Verifier tiering + parallelization contract for ``orchestration-prompt``.

TAP-6596 — the skill used to instruct that the independent verifier is *always*
frontier tier. Applied literally that produces eight ``opus`` verifiers re-reasoning
about proofs an exit code had already settled, while the two checks that needed real
judgement are billed the same and get no extra effort. The fix is a proof-shape tier
table (deterministic → ``haiku``/``low``, comparative → ``sonnet``/``medium``,
semantic → ``opus``/``high``+, irreversible-gating → ``opus`` regardless of shape),
four proof-shape verifier rows in the emitted Plane map, and verdict schemas that
carry ``observed_output`` (empty = FAIL) and ``green_by_suppression``.

TAP-6597 — the skill forbade fanning out *coupled code*, but defined coupling as
"editing related code". Two chunks with entirely disjoint file lists are still
coupled when one computes a set the other consumes, and that coupling fails silently
because each half is internally consistent. The fix is the read-what-the-other-writes
test in method §3 plus a ``## Parallelization plan`` section in the emitted template.

Everything is asserted against files *generated into a tmp consumer root*, never
against the source constants — a generator that stops deploying its own text is the
failure mode these tests exist to catch.

Division of labour between the two generated files (stated explicitly because a
requirement may be satisfied by their union):

* ``SKILL.md`` carries the *method prose* — the §5 tier table, the §5 verdict-schema
  rules, the §3 derived-state coupling test, and the Guardrails entries.
* ``assets/prompt-template.md`` carries the *emitted artifact structure* — the four
  verifier rows, the ``## Parallelization plan`` section, and the template Guardrails.
"""

from __future__ import annotations

import pytest

from tapps_mcp.pipeline.platform_skills import generate_skills

SKILL = "orchestration-prompt"


@pytest.fixture
def consumer_root(tmp_path):
    """A hermetic consumer root with the skill freshly generated into it."""
    generate_skills(tmp_path, "claude")
    return tmp_path


@pytest.fixture
def skill_dir(consumer_root):
    return consumer_root / ".claude" / "skills" / SKILL


@pytest.fixture
def body(skill_dir):
    return (skill_dir / "SKILL.md").read_text(encoding="utf-8")


@pytest.fixture
def template(skill_dir):
    return (skill_dir / "assets" / "prompt-template.md").read_text(encoding="utf-8")


def _verifier_rows(template: str) -> list[str]:
    return [ln for ln in template.splitlines() if ln.startswith("| <verify")]


class TestProofShapeTierTable:
    """TAP-6596 acceptance — method §5 of the generated SKILL.md body."""

    def test_uniform_frontier_instruction_is_gone(self, body):
        assert "always frontier" not in body

    def test_body_has_a_proof_shape_tier_table(self, body):
        assert "| Proof shape | What the verifier actually does | model | effort |" in body

    @pytest.mark.parametrize(
        ("shape", "model", "effort"),
        [
            ("**Deterministic**", "`haiku`", "`low`"),
            ("**Comparative**", "`sonnet`", "`medium`"),
            ("**Semantic**", "`opus`", "`high` or `xhigh`"),
            ("**Gates an irreversible step**", "`opus`", "`high`+"),
        ],
    )
    def test_each_proof_shape_maps_to_a_tier(self, body, shape, model, effort):
        row = next(
            (ln for ln in body.splitlines() if ln.startswith(f"| {shape} ")),
            None,
        )
        assert row is not None, f"no tier-table row for {shape}"
        assert f"| {model} | {effort} |" in row, row

    def test_consequence_overrides_shape(self, body):
        assert "Consequence overrides shape" in body

    def test_verifier_bullet_points_at_the_table(self, body):
        bullet = body.split("- After Execute, spawn a **verifier subagent**", 1)[1]
        bullet = bullet.split("\n- ", 1)[0]
        assert "frontier" not in bullet
        assert "proof-shape table" in bullet

    def test_method_three_stops_instructing_uniform_frontier(self, body):
        assert "tiered by **proof shape**" in body


class TestVerdictSchemaRules:
    """TAP-6596 acceptance — the two required verdict-schema fields."""

    def test_observed_output_is_required_and_empty_is_a_fail(self, body):
        assert "**`observed_output`**" in body
        assert "An empty `observed_output` is a FAIL" in body

    def test_green_by_suppression_is_required(self, body):
        assert "**`green_by_suppression`**" in body
        assert "removing\n  what it measures" in body

    def test_cheap_tiers_are_read_on_evidence_not_conclusion(self, body):
        assert "reads `observed_output` and never the" in body
        assert "conclusion sentence" in body

    def test_template_loop_carries_both_fields(self, template):
        verify = next(
            ln for ln in template.splitlines() if ln.startswith("- **Verify (independent):**")
        )
        assert "`observed_output`" in verify
        assert "an empty value is a FAIL" in verify
        assert "`green_by_suppression`" in verify
        assert "never the conclusion sentence" in verify


class TestTemplateVerifierRows:
    """TAP-6596 acceptance — four proof-shape rows, not one."""

    def test_there_are_exactly_four_verifier_rows(self, template):
        rows = _verifier_rows(template)
        assert len(rows) == 4, rows

    @pytest.mark.parametrize(
        ("label", "model"),
        [
            ("| <verify — deterministic proof> |", "`haiku`"),
            ("| <verify — closed check> |", "`sonnet`"),
            ("| <verify — open judgement> |", "`opus`"),
            ("| <verify — gates an irreversible step> |", "`opus`"),
        ],
    )
    def test_each_proof_shape_has_its_own_row(self, template, label, model):
        row = next((ln for ln in template.splitlines() if ln.startswith(label)), None)
        assert row is not None, f"missing verifier row {label}"
        assert model in row, row

    def test_the_single_generic_verify_row_is_gone(self, template):
        assert "| <verify proof> |" not in template

    def test_plane_map_states_the_tiering_rule(self, template):
        assert "**Verifier tiering follows the proof shape**" in template


class TestDerivedStateCoupling:
    """TAP-6597 acceptance — method §3 of the generated SKILL.md body."""

    def test_disjoint_file_lists_are_not_independence(self, body):
        assert "**Disjoint file lists are not evidence of independence.**" in body

    def test_body_explains_the_silent_failure_mode(self, body):
        assert "fails silently" in body
        assert "each half stays internally consistent" in body

    def test_body_gives_the_read_what_the_other_writes_test(self, body):
        assert (
            "**The test to apply before pairing two chunks in a wave: what set does each "
            "one read\nthat the other writes?**" in body
        )

    def test_body_requires_naming_producer_and_consumer(self, body):
        section = body.split("**The test to apply before pairing two chunks", 1)[1]
        section = section.split("\n### ", 1)[0]
        assert "producer" in section
        assert "consumer" in section
        assert "`order-forced-by`" in section


class TestTemplateParallelizationPlan:
    """TAP-6597 acceptance — the emitted template's new section."""

    def test_section_heading_is_present(self, template):
        assert "## Parallelization plan" in template

    def test_it_is_a_sibling_of_the_wave_schedule_not_a_replacement(self, template):
        # Ruling 4: PR #302's wave schedule must survive alongside the new section.
        assert "### Parallel wave schedule" in template
        assert template.index("### Parallel wave schedule") < template.index(
            "## Parallelization plan"
        )

    def test_plan_has_lanes_order_forced_by_and_never_fan_out(self, template):
        plan = template.split("## Parallelization plan", 1)[1].split("\n## ", 1)[0]
        assert "- **Lanes:**" in plan
        assert "- **order-forced-by:**" in plan
        assert "- **Never fan out:**" in plan

    def test_order_forced_by_names_the_shared_state(self, template):
        plan = template.split("## Parallelization plan", 1)[1].split("\n## ", 1)[0]
        forced = plan.split("- **order-forced-by:**", 1)[1].split("\n- ", 1)[0]
        assert "shared derived state" in forced
        assert "producer" in forced and "consumer" in forced

    def test_independent_lanes_dispatch_to_background_at_iteration_1(self, template):
        plan = template.split("## Parallelization plan", 1)[1].split("\n## ", 1)[0]
        assert "**Dispatch independent lanes to the background at iteration 1**" in plan
        assert "queueing behind" in plan

    def test_plan_warns_that_disjoint_file_lists_are_not_independence(self, template):
        plan = template.split("## Parallelization plan", 1)[1].split("\n## ", 1)[0]
        assert "Disjoint file lists are NOT evidence of independence" in plan

    def test_output_step_keeps_the_section(self, body):
        assert "**`## Parallelization plan`**" in body


class TestGuardrails:
    """TAP-6596 + TAP-6597 acceptance — both Guardrails lists."""

    def test_body_guardrails_carry_parallel_where_independent(self, body):
        guardrails = body.split("## Guardrails every emitted prompt must carry", 1)[1]
        guardrails = guardrails.split("\n## ", 1)[0]
        assert "**Parallel where independent, serial where coupled**" in guardrails
        assert "`order-forced-by`" in guardrails

    def test_body_guardrails_tier_the_verifier_by_proof_shape(self, body):
        guardrails = body.split("## Guardrails every emitted prompt must carry", 1)[1]
        guardrails = guardrails.split("\n## ", 1)[0]
        assert "**proof-shape table**" in guardrails
        assert "`observed_output` (empty = FAIL)" in guardrails
        assert "`green_by_suppression`" in guardrails

    def test_template_guardrails_carry_both_entries(self, template):
        guardrails = template.split("\n## Guardrails\n", 1)[1].split("\n## ", 1)[0]
        assert "**Parallel where independent, serial where coupled**" in guardrails
        assert "**Verifier tier follows the proof shape**" in guardrails


class TestRulingFourCoexistence:
    """PR #302's surface must survive this change untouched (binding ruling 4)."""

    @pytest.mark.parametrize(
        "fragment",
        [
            "## Driver discipline — dispatch, don't execute",
            "### Parallel wave schedule",
            "| Step | Owner | Plane | Mechanism | agentType | model | effort | Notes |",
            "**The driver MAY:**",
            "**The driver MUST NOT:**",
            "orch-spend <n>%",
            "in the `agentType` column is orchestrator work",
        ],
    )
    def test_pr_302_template_surface_intact(self, template, fragment):
        assert fragment in template

    def test_pr_302_kept_both_original_verifier_rows(self, template):
        rows = _verifier_rows(template)
        assert any(r.startswith("| <verify — open judgement>") for r in rows)
        assert any(r.startswith("| <verify — closed check>") for r in rows)

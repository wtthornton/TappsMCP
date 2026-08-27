"""Driver-discipline contract for the ``orchestration-prompt`` skill (TAP-6594, TAP-6595).

TAP-6594 and TAP-6595 describe one constraint under two names ("Driver discipline"
and "Orchestrator discipline"). They are reconciled here as a **single** required
template section, ``## Driver discipline — dispatch, don't execute``, carrying both
issues' payloads: the five driver jobs and the context ceiling (6594) plus the
MAY / MUST NOT lists, the ``orch-spend %`` SCORE field, the under-15% token-share
target, and the two mechanical detectors (6595).

Everything is asserted against files *generated into a tmp consumer root*, never
against the source constants — a generator that stops deploying its own text is the
failure mode these tests exist to catch.
"""

from __future__ import annotations

import pytest

from tapps_mcp.distribution.doctor import check_orchestration_prompt_skill_current
from tapps_mcp.pipeline.platform_skills import generate_skills

SKILL = "orchestration-prompt"

# The structurally-required headings the template carried BEFORE this change.
# Frozen on purpose: backward compatibility means a prompt written against the old
# template still parses, so the new required list must be a superset of this one.
OLD_REQUIRED_SECTIONS = frozenset(
    {
        "## How to run (cold start)",
        "## Done-when",
        "## Loop",
        "## Guardrails",
        "## Autonomy",
        "## Standing constraints",
    }
)

DRIVER_HEADING = "## Driver discipline"


@pytest.fixture
def consumer_root(tmp_path):
    """A hermetic consumer root with the skill freshly generated into it."""
    generate_skills(tmp_path, "claude")
    return tmp_path


@pytest.fixture
def skill_dir(consumer_root):
    return consumer_root / ".claude" / "skills" / SKILL


@pytest.fixture
def template(skill_dir):
    return (skill_dir / "assets" / "prompt-template.md").read_text(encoding="utf-8")


@pytest.fixture
def body(skill_dir):
    return (skill_dir / "SKILL.md").read_text(encoding="utf-8")


class TestTemplateDriverDiscipline:
    """TAP-6594 acceptance, asserted on the generated template."""

    def test_single_reconciled_heading(self, template):
        # The binding ruling: ONE section, not a Driver/Orchestrator pair.
        assert "## Driver discipline — dispatch, don't execute" in template
        assert "## Orchestrator discipline" not in template

    def test_names_the_five_driver_jobs(self, template):
        for job in (
            "decide what to dispatch next",
            "adjudicate verifier verdicts",
            "checkpoint",
        ):
            assert job in template
        assert "The driver does exactly five things" in template

    def test_carries_a_context_ceiling(self, template):
        assert "Driver context ceiling" in template

    def test_may_and_must_not_lists(self, template):
        assert "**The driver MAY:**" in template
        assert "**The driver MUST NOT:**" in template

    def test_orch_spend_in_score_line(self, template):
        assert "orch-spend <n>%" in template
        assert "SCORE: " in template
        score_line = next(
            line
            for line in template.splitlines()
            if line.startswith("- **Print every iteration:**")
        )
        assert "orch-spend" in score_line

    def test_token_share_target(self, template):
        assert "under 15%" in template

    def test_two_mechanical_detectors(self, template):
        assert "in the `agentType` column is orchestrator work" in template
        assert "effort` column means effort control was surrendered" in template
        assert "Workflow-only" in template

    def test_driver_discipline_is_structurally_required(self, template):
        header = template.split("\n## Driver discipline — dispatch", 1)[0]
        assert "Structurally required" in header
        assert "`## Driver discipline`" in header


class TestPlaneMapOwnerColumn:
    def test_owner_column_header(self, template):
        assert (
            "| Step | Owner | Plane | Mechanism | agentType | model | effort | Notes |" in template
        )

    def test_worked_row_for_each_owner_value(self, template):
        rows = [ln for ln in template.splitlines() if ln.startswith("| <") and ln.count("|") >= 8]
        owners = [ln.split("|")[2].strip().strip("*") for ln in rows]
        for value in ("driver", "delegate", "operator"):
            assert owners.count(value) >= 1, f"no worked {value} row in {owners}"

    def test_verifier_row_is_split_by_proof_shape(self, template):
        assert "| <verify — open judgement> |" in template
        assert "| <verify — closed check> |" in template
        open_row = next(
            ln for ln in template.splitlines() if ln.startswith("| <verify — open judgement>")
        )
        closed_row = next(
            ln for ln in template.splitlines() if ln.startswith("| <verify — closed check>")
        )
        assert "`opus`" in open_row
        assert "`sonnet`" in closed_row

    def test_delegated_rows_cover_the_leaked_driver_work(self, template):
        # The three shapes a real prompt shipped inline (TAP-6594's motivating case).
        assert "| <preflight probes> | delegate |" in template
        assert "| <per-iteration state gather> | delegate |" in template
        assert "| <lane log tail / progress poll> | delegate |" in template

    def test_parallel_wave_schedule_block(self, template):
        assert "### Parallel wave schedule" in template
        wave_block = template.split("### Parallel wave schedule", 1)[1]
        assert "WAVE 1" in wave_block
        assert "WAVE 2" in wave_block


class TestTemplateGuardrails:
    def test_guardrails_carry_the_three_new_rules(self, template):
        guardrails = template.split("\n## Guardrails\n", 1)[1].split("\n## ", 1)[0]
        assert "**Driver discipline:**" in guardrails
        assert "**Every dispatch carries a return schema**" in guardrails
        assert "**Tier by question shape, not importance**" in guardrails
        assert "**Dispatch each wave in full before polling it**" in guardrails


class TestSkillBodyOrchestratorDiscipline:
    """TAP-6595 acceptance, asserted on the generated SKILL.md body."""

    def test_method_section_3_constrains_the_top_session(self, body):
        assert (
            "The top session dispatches, reads verdicts, and checkpoints — it does not do the work."
            in body
        )
        for forbidden in ("edit files", "run\nbuilds", "trawl logs", "read large files"):
            assert forbidden in body

    def test_body_names_token_share_and_score_field(self, body):
        assert "under 15%" in body
        assert "orch-spend <n>%" in body

    def test_body_carries_both_detectors(self, body):
        assert "in the `agentType` column is orchestrator work" in body
        assert "effort` column means effort control was surrendered" in body

    def test_guardrails_list_has_an_orchestrator_discipline_entry(self, body):
        guardrails = body.split("## Guardrails every emitted prompt must carry", 1)[1]
        guardrails = guardrails.split("\n## ", 1)[0]
        assert "Orchestrator-discipline guardrail" in guardrails
        assert "Every dispatch carries a return schema" in guardrails
        assert "Tier by question shape, not importance" in guardrails
        assert "Dispatch each wave in full before polling it" in guardrails

    def test_output_step_keeps_the_section(self, body):
        assert "**`## Driver discipline`**" in body
        assert "**`### Parallel wave schedule`**" in body


class TestBackwardCompatibility:
    def test_old_required_sections_are_a_subset_of_new(self, template):
        header = template.split("\n## ", 1)[0]
        missing = sorted(s for s in OLD_REQUIRED_SECTIONS if f"`{s}`" not in header)
        assert not missing, f"old structurally-required headings dropped: {missing}"

    def test_old_headings_still_present_in_the_body_of_the_template(self, template):
        # Headings carry parentheticals ("## Done-when (Goal condition …)"), so the
        # required-list label is a prefix of the real heading line, not the whole of it.
        heading_lines = [ln for ln in template.splitlines() if ln.startswith("## ")]
        for heading in sorted(OLD_REQUIRED_SECTIONS):
            # "## How to run (cold start)" is written in the required list with its
            # parenthetical closed; the real heading continues it ("… — paste into a
            # NEW session)"). Drop the trailing paren so the label is a true prefix.
            stem = heading.rstrip(")")
            assert any(ln.startswith(stem) for ln in heading_lines), (
                f"{heading} no longer emitted; saw {heading_lines}"
            )

    def test_doctor_freshness_check_still_passes(self, consumer_root):
        result = check_orchestration_prompt_skill_current(consumer_root)
        assert result.ok, result.message

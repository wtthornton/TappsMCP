"""TAP-6496: context recycling is a first-class loop step, not advice.

A long run loses to its own context twice — cost (every turn re-pays for the
whole transcript) and quality (superseded reads degrade the next decision). The
sub-goal boundary is already a valid context boundary; these assertions keep the
emitted prompt from quietly dropping it, since a missing boundary is invisible.
"""

from __future__ import annotations

from tapps_mcp.pipeline.platform_skills import generate_skills

SKILL = "orchestration-prompt"


def _skill_dir(root, host="claude"):
    return root / f".{host}" / "skills" / SKILL


class TestContextRecycling:
    def test_body_has_the_four_step_cycle(self, tmp_path):
        """Acceptance 1 — handoff → re-verify → clear → continue, per sub-goal."""
        generate_skills(tmp_path, "claude")
        content = (_skill_dir(tmp_path) / "SKILL.md").read_text()
        assert "Context lifecycle — recycle at every sub-goal boundary" in content
        assert "handoff → re-verify → clear → continue" in content
        for step in ("/tapps-handoff-session", "/tapps-continue-session"):
            assert step in content

    def test_body_names_clear_as_uninvokable_and_maps_run_shapes(self, tmp_path):
        """Acceptance 2 — /clear is a CLI built-in; name what replaces it."""
        generate_skills(tmp_path, "claude")
        content = (_skill_dir(tmp_path) / "SKILL.md").read_text()
        assert "built-in CLI command the model cannot invoke" in content
        assert "Attended operator" in content
        assert "One `claude -p` invocation per sub-goal" in content
        assert "Workflow / subagents" in content

    def test_body_specifies_the_mandatory_reverify_gate(self, tmp_path):
        """Acceptance 3 — sha, tracker, metric. All three, before the clear."""
        generate_skills(tmp_path, "claude")
        content = (_skill_dir(tmp_path) / "SKILL.md").read_text()
        assert "mandatory re-verify\ngate" in content or "mandatory re-verify gate" in content
        assert "`git log -1`" in content
        assert "git log --oneline <handoff-sha>..HEAD" in content
        assert "re-read from the tracker" in content
        assert "re-read from its newest artifact" in content
        assert "correct the handoff *before* clearing" in content

    def test_body_names_when_not_to_recycle(self, tmp_path):
        """Acceptance 6 — the cycle has a cost; say when it is not worth paying."""
        generate_skills(tmp_path, "claude")
        content = (_skill_dir(tmp_path) / "SKILL.md").read_text()
        assert "When *not* to recycle" in content
        assert "tightly-coupled sub-goal" in content
        assert "smaller than the cycle's overhead" in content

    def test_body_warns_about_two_runners_on_one_handoff(self, tmp_path):
        """Acceptance 7 — concurrent runners silently overwrite each other."""
        generate_skills(tmp_path, "claude")
        content = (_skill_dir(tmp_path) / "SKILL.md").read_text()
        assert "One runner per handoff file" in content
        assert "silently overwrite each other" in content

    def test_body_guardrail_restates_context_lifecycle(self, tmp_path):
        generate_skills(tmp_path, "claude")
        content = (_skill_dir(tmp_path) / "SKILL.md").read_text()
        guardrails = content.split("## Guardrails every emitted prompt must carry", 1)[1]
        assert "**Context lifecycle**" in guardrails
        assert "Never clear on an unverified handoff" in guardrails
        assert (
            "One\n  runner per handoff file" in guardrails
            or "One runner per handoff file" in guardrails
        )

    def test_output_self_check_verifies_the_lifecycle_line(self, tmp_path):
        """Acceptance 5 — a guardrail nothing checks is the skill's own anti-pattern."""
        generate_skills(tmp_path, "claude")
        content = (_skill_dir(tmp_path) / "SKILL.md").read_text()
        check = content.split("**Completeness self-check**", 1)[1]
        assert "Context lifecycle is checked explicitly" in check
        assert "one `claude -p` per sub-goal" in check
        assert "the one guardrail whose failure" in check

    def test_template_loop_carries_the_recycle_step(self, tmp_path):
        """Acceptance 4a — Recycle is a Loop bullet, not a footnote."""
        generate_skills(tmp_path, "claude")
        tpl = (_skill_dir(tmp_path) / "assets" / "prompt-template.md").read_text()
        loop = tpl.split("## Loop", 1)[1].split("## Checkpoint protocol", 1)[0]
        assert "**Recycle (context boundary" in loop
        assert "The re-verify gate is mandatory" in loop
        assert "git log -1" in loop
        assert "One runner per handoff file" in loop

    def test_template_subgoals_carry_the_context_boundary_note(self, tmp_path):
        """Acceptance 4b."""
        generate_skills(tmp_path, "claude")
        tpl = (_skill_dir(tmp_path) / "assets" / "prompt-template.md").read_text()
        subgoals = tpl.split("## Sub-goals", 1)[1].split("## Plane map", 1)[0]
        assert "**Context boundary between sub-goals**" in subgoals
        assert "one `claude -p` per sub-goal" in subgoals

    def test_template_guardrails_carry_the_lifecycle_line(self, tmp_path):
        """Acceptance 4c."""
        generate_skills(tmp_path, "claude")
        tpl = (_skill_dir(tmp_path) / "assets" / "prompt-template.md").read_text()
        guardrails = tpl.split("\n## Guardrails\n", 1)[1].split("\n## Autonomy\n", 1)[0]
        assert "Context lifecycle — recycle at each sub-goal boundary" in guardrails
        assert "never clear on an unverified handoff" in guardrails

    def test_template_run_as_offers_the_chained_claude_p_option(self, tmp_path):
        """Acceptance 4d."""
        generate_skills(tmp_path, "claude")
        tpl = (_skill_dir(tmp_path) / "assets" / "prompt-template.md").read_text()
        run_as = tpl.split("## Run-as", 1)[1]
        assert "Chained (autonomous, context-recycling)" in run_as
        assert "one `claude -p` per sub-goal" in run_as
        assert "one runner at a time" in run_as.lower()

    def test_companion_carries_the_reverify_gate_table(self, tmp_path):
        generate_skills(tmp_path, "claude")
        ref = (_skill_dir(tmp_path) / "references" / "cold-start-and-verify.md").read_text()
        assert "The re-verify gate (mandatory, both sides of the boundary)" in ref
        for row in ("Commit drift", "Tracker state", "Metrics"):
            assert row in ref
        assert "claim in both directions" in ref
        assert "One runner per handoff file" in ref

    def test_lessons_pass_survives_alongside_recycling(self, tmp_path):
        """TAP-6578 guard: the terminal lessons pass must not be edited away."""
        generate_skills(tmp_path, "claude")
        content = (_skill_dir(tmp_path) / "SKILL.md").read_text()
        tpl = (_skill_dir(tmp_path) / "assets" / "prompt-template.md").read_text()
        assert "**Terminal lessons-learned pass**" in content
        assert "Lessons learned (REQUIRED" in tpl
        assert "the one sub-goal that survives" in tpl.lower() + content.lower()

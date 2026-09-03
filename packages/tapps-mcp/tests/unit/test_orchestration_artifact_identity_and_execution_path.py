"""Artifact-identity + execution-path guardrails for ``orchestration-prompt``.

TAP-6602 — emitted prompts verify that an artifact is *valid* and never that it is
the *right thing*. Gates check form (schema, exit code, geometry, provenance,
signature) and will happily pass an artifact that is the wrong product entirely. The
fix is a Guardrails bullet requiring one delegated, open-judgement step —
``agentType`` + ``model=opus`` — that opens the artifact and answers *is this the
thing that was asked for*, in words, whenever the loop produces something a human or
customer will look at.

TAP-6603 — emitted prompts treat "merged to main" as equivalent to "the consumer runs
the fix". The fix is a Guardrails bullet requiring the file, the checkout it resolves
from, and the revision the consumer loads to be named, proved by a marker check
against that exact file (never a merge SHA or branch name), forbidding delegates from
locating the tool by filesystem search.

Both bullets are conditional per binding ruling 7: "conditional" means an instruction
in the SKILL.md body's Output step to drop the bullet when not applicable, plus a
placeholder in the static ``assets/prompt-template.md`` text — nothing more (no
templating engine, no Jinja layer, no runtime if/render abstraction).

Everything is asserted against files *generated into a tmp consumer root*, never
against the source constants — a generator that stops deploying its own text is the
failure mode these tests exist to catch.

Division of labour between the two generated files (a requirement may be satisfied by
their union):

* ``SKILL.md`` carries the *method prose* — the Guardrails-every-prompt-must-carry
  list entries and the Output step's "drop when N/A" instructions.
* ``assets/prompt-template.md`` carries the *emitted artifact structure* — the
  template Guardrails bullets with their placeholders.
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
    """TAP-7017: the Guardrails-every-prompt list (which carries both the

    artifact-identity and execution-path-proof bullets) and method §3/§5
    (which carry the proof-shape table and the derived-state coupling test)
    moved out of SKILL.md's managed block into reference files, reachable
    from SKILL.md by an explicit pointer.
    """
    skill_md = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    method = (skill_dir / "references" / "method-detail.md").read_text(encoding="utf-8")
    guardrails = (skill_dir / "references" / "guardrails-and-contracts.md").read_text(
        encoding="utf-8"
    )
    return "\n".join((skill_md, method, guardrails))


@pytest.fixture
def template(skill_dir):
    return (skill_dir / "assets" / "prompt-template.md").read_text(encoding="utf-8")


def _body_guardrails(body: str) -> str:
    section = body.split("## Guardrails every emitted prompt must carry", 1)[1]
    return section.split("\n## ", 1)[0]


def _template_guardrails(template: str) -> str:
    return template.split("\n## Guardrails\n", 1)[1].split("\n## ", 1)[0]


class TestArtifactIdentityBodyGuardrail:
    """TAP-6602 acceptance — the SKILL.md body's Guardrails-every-prompt list."""

    def test_bullet_is_present(self, body):
        guardrails = _body_guardrails(body)
        assert "**Artifact identity, not just validity**" in guardrails

    def test_stated_as_distinct_from_validity(self, body):
        guardrails = _body_guardrails(body)
        bullet = guardrails.split("**Artifact identity, not just validity**", 1)[1]
        bullet = bullet.split("\n- ", 1)[0]
        assert "gates check form only" in bullet

    def test_names_form_only_checks(self, body):
        guardrails = _body_guardrails(body)
        bullet = guardrails.split("**Artifact identity, not just validity**", 1)[1]
        bullet = bullet.split("\n- ", 1)[0]
        for term in ("schema", "exit code", "geometry", "provenance", "signature"):
            assert term in bullet, f"missing {term!r} in artifact-identity bullet"

    def test_delegated_step_names_agent_type_and_opus_and_is_open_judgement(self, body):
        guardrails = _body_guardrails(body)
        bullet = guardrails.split("**Artifact identity, not just validity**", 1)[1]
        bullet = bullet.split("\n- ", 1)[0]
        assert "`agentType`" in bullet
        assert "`model=opus`" in bullet
        assert "open judgement" in bullet
        assert "closed check" in bullet

    def test_answers_is_this_the_thing_that_was_asked_for(self, body):
        guardrails = _body_guardrails(body)
        bullet = guardrails.split("**Artifact identity, not just validity**", 1)[1]
        bullet = bullet.split("\n- ", 1)[0]
        assert "is this the thing that was asked for" in bullet

    def test_conditional_drop_stated_for_no_human_facing_artifact(self, body):
        guardrails = _body_guardrails(body)
        bullet = guardrails.split("**Artifact identity, not just validity**", 1)[1]
        bullet = bullet.split("\n- ", 1)[0]
        assert "Drop this guardrail" in bullet
        assert "only when the loop produces no artifact a human or customer will look at" in bullet


class TestArtifactIdentityOutputStep:
    """TAP-6602 acceptance — the Output step's conditional-emission instruction."""

    def test_output_step_drops_bullet_when_no_human_facing_artifact(self, body):
        output = body.split("## Output", 1)[1].split("\n## ", 1)[0]
        assert "artifact-identity" in output
        assert "no artifact a" in output
        assert "human or customer will look at" in output


class TestArtifactIdentityTemplate:
    """TAP-6602 acceptance — assets/prompt-template.md's emitted Guardrails text."""

    def test_template_guardrail_present(self, template):
        guardrails = _template_guardrails(template)
        assert "**Artifact identity, not just validity**" in guardrails

    def test_template_names_form_only_checks(self, template):
        guardrails = _template_guardrails(template)
        bullet = guardrails.split("**Artifact identity, not just validity**", 1)[1]
        bullet = bullet.split("\n- ", 1)[0]
        for term in ("schema", "exit code", "geometry", "provenance", "signature"):
            assert term in bullet

    def test_template_carries_agent_type_and_opus_and_open_judgement(self, template):
        guardrails = _template_guardrails(template)
        bullet = guardrails.split("**Artifact identity, not just validity**", 1)[1]
        bullet = bullet.split("\n- ", 1)[0]
        assert "`agentType`" in bullet
        assert "`model=opus`" in bullet
        assert "open judgement" in bullet
        assert "closed check" in bullet

    def test_template_has_a_name_the_artifacts_placeholder(self, template):
        guardrails = _template_guardrails(template)
        bullet = guardrails.split("**Artifact identity, not just validity**", 1)[1]
        bullet = bullet.split("\n- ", 1)[0]
        assert "<name the artifacts>" in bullet


class TestExecutionPathBodyGuardrail:
    """TAP-6603 acceptance — the SKILL.md body's Guardrails-every-prompt list."""

    def test_bullet_is_present(self, body):
        guardrails = _body_guardrails(body)
        assert '**Execution-path proof before "this change takes effect"**' in guardrails

    def test_requires_file_checkout_revision_and_marker_check(self, body):
        guardrails = _body_guardrails(body)
        bullet = guardrails.split('**Execution-path proof before "this change takes effect"**', 1)[
            1
        ]
        bullet = bullet.split("\n- ", 1)[0]
        assert "name the file" in bullet
        assert "checkout it resolves from" in bullet
        assert "the revision the consumer loads" in bullet
        assert "marker check against that exact file" in bullet

    def test_proof_is_not_a_merge_sha_or_branch_name(self, body):
        guardrails = _body_guardrails(body)
        bullet = guardrails.split('**Execution-path proof before "this change takes effect"**', 1)[
            1
        ]
        bullet = bullet.split("\n- ", 1)[0]
        assert "never a merge SHA or a branch name" in bullet

    def test_forbids_filesystem_search_and_requires_pinned_path_hard_stop(self, body):
        guardrails = _body_guardrails(body)
        bullet = guardrails.split('**Execution-path proof before "this change takes effect"**', 1)[
            1
        ]
        bullet = bullet.split("\n- ", 1)[0]
        assert "Forbid delegates from locating the tool by filesystem search" in bullet
        assert "pin the path and\n  hard-stop on mismatch" in bullet

    def test_states_merge_is_not_consumer_seeing_it(self, body):
        guardrails = _body_guardrails(body)
        bullet = guardrails.split('**Execution-path proof before "this change takes effect"**', 1)[
            1
        ]
        bullet = bullet.split("\n- ", 1)[0]
        assert "Merging to a default branch is not the same as the consumer seeing it" in bullet

    def test_conditional_drop_stated_for_producer_equals_consumer(self, body):
        guardrails = _body_guardrails(body)
        bullet = guardrails.split('**Execution-path proof before "this change takes effect"**', 1)[
            1
        ]
        bullet = bullet.split("\n- ", 1)[0]
        assert (
            "Drop this guardrail only when the change's producer and\n  consumer are "
            "the same checkout" in bullet
        )


class TestExecutionPathOutputStep:
    """TAP-6603 acceptance — the Output step's conditional-emission instruction."""

    def test_output_step_drops_bullet_when_producer_equals_consumer(self, body):
        output = body.split("## Output", 1)[1].split("\n## ", 1)[0]
        assert "execution-path proof" in output
        assert "producer and consumer are the same checkout" in output


class TestExecutionPathTemplate:
    """TAP-6603 acceptance — assets/prompt-template.md's emitted Guardrails text."""

    def test_template_guardrail_present(self, template):
        guardrails = _template_guardrails(template)
        assert '**Execution-path proof before "this change takes effect"**' in guardrails

    def test_template_requires_file_checkout_revision_and_marker_check(self, template):
        guardrails = _template_guardrails(template)
        bullet = guardrails.split('**Execution-path proof before "this change takes effect"**', 1)[
            1
        ]
        bullet = bullet.split("\n- ", 1)[0]
        assert "the checkout it resolves from" in bullet
        assert "the revision the consumer loads" in bullet
        assert "marker check against that exact file" in bullet

    def test_template_forbids_filesystem_search(self, template):
        guardrails = _template_guardrails(template)
        bullet = guardrails.split('**Execution-path proof before "this change takes effect"**', 1)[
            1
        ]
        bullet = bullet.split("\n- ", 1)[0]
        assert "Forbid locating the tool by filesystem search" in bullet
        assert "pin the path and hard-stop on mismatch" in bullet

    def test_template_states_merge_is_not_consumer_seeing_it(self, template):
        guardrails = _template_guardrails(template)
        bullet = guardrails.split('**Execution-path proof before "this change takes effect"**', 1)[
            1
        ]
        bullet = bullet.split("\n- ", 1)[0]
        assert "merging to a default branch is not the consumer seeing it" in bullet

    def test_template_has_a_name_file_checkout_revision_placeholder(self, template):
        guardrails = _template_guardrails(template)
        bullet = guardrails.split('**Execution-path proof before "this change takes effect"**', 1)[
            1
        ]
        bullet = bullet.split("\n- ", 1)[0]
        assert "<name file / checkout / revision>" in bullet


class TestNoTemplatingEngineIntroduced:
    """Binding ruling 7 — conditional emission must NOT become a rendering engine."""

    def test_no_jinja_or_templating_markers_in_generated_files(self, body, template):
        for text, name in ((body, "SKILL.md"), (template, "prompt-template.md")):
            assert "{{" not in text, f"{name} contains Jinja-style interpolation"
            assert "{%" not in text, f"{name} contains Jinja-style control flow"

    def test_generator_source_has_no_conditional_render_helper(self):
        import inspect

        from tapps_mcp.pipeline import platform_skill_orchestration as mod

        source = inspect.getsource(mod)
        assert "def render(" not in source
        assert "import jinja2" not in source


class TestRulingFourCoexistence:
    """PR #302 + the W2 PR's surface must survive this change untouched."""

    @pytest.mark.parametrize(
        "fragment",
        [
            "## Driver discipline — dispatch, don't execute",
            "### Parallel wave schedule",
            "## Parallelization plan",
        ],
    )
    def test_prior_template_surface_intact(self, template, fragment):
        assert fragment in template

    def test_prior_body_surface_intact(self, body):
        assert "| Proof shape | What the verifier actually does | model | effort |" in body
        assert "**Disjoint file lists are not evidence of independence.**" in body

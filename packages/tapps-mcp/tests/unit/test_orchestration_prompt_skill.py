"""Tests for the multi-file, smart-merged ``orchestration-prompt`` platform skill.

Covers three concerns:
- ``generate_skills`` scaffolds SKILL.md + companion files + seed learnings.
- ``skill_managed_block.install_or_refresh_skill`` refreshes the managed block
  while preserving project customizations (and migrates legacy unmarked copies).
- companion docs refresh on upgrade but ``learnings.md`` is never overwritten.
- the doctor check reports current / stale / partial correctly.
"""

from __future__ import annotations

import pytest

from tapps_mcp.distribution.doctor import check_orchestration_prompt_skill_current
from tapps_mcp.pipeline.platform_skill_orchestration import (
    ORCHESTRATION_PROMPT_SKILL_BODY,
)
from tapps_mcp.pipeline.platform_skills import generate_skills
from tapps_mcp.pipeline.skill_asset_policy import policy_header
from tapps_mcp.pipeline.skill_managed_block import (
    MARKER_BEGIN_PREFIX,
    MARKER_END,
    extract_block,
    install_or_refresh_skill,
    wrap_with_markers,
)

SKILL = "orchestration-prompt"


def _skill_dir(root, host="claude"):
    return root / f".{host}" / "skills" / SKILL


class TestScaffold:
    def test_creates_skill_and_companions(self, tmp_path):
        generate_skills(tmp_path, "claude")
        d = _skill_dir(tmp_path)
        assert (d / "SKILL.md").exists()
        assert (d / "assets" / "prompt-template.md").exists()
        assert (d / "references" / "claude-feature-map.md").exists()
        assert (d / "learnings.md").exists()

    def test_skill_md_has_managed_marker(self, tmp_path):
        generate_skills(tmp_path, "claude")
        content = (_skill_dir(tmp_path) / "SKILL.md").read_text()
        assert f"{MARKER_BEGIN_PREFIX} {SKILL} v" in content
        assert MARKER_END in content
        assert "name: orchestration-prompt" in content

    def test_managed_block_warns_directly_after_begin(self, tmp_path):
        """TAP-6598: an editor working inside the block sees why it's lost."""
        generate_skills(tmp_path, "claude")
        content = (_skill_dir(tmp_path) / "SKILL.md").read_text()
        begin_idx = content.index(f"{MARKER_BEGIN_PREFIX} {SKILL} v")
        end_idx = content.index(MARKER_END)
        warning = policy_header("managed_block")
        warning_idx = content.index(warning)
        assert begin_idx < warning_idx < end_idx
        begin_line_end = content.index("\n", begin_idx) + 1
        assert content[begin_line_end:].startswith(warning)

    def test_body_carries_the_four_enhancements(self, tmp_path):
        """TAP-7017 moved most method elaboration to references/method-detail.md,
        reachable from SKILL.md by an explicit pointer; the disclosure surface
        (managed block + reference) is what carries these phrases now."""
        generate_skills(tmp_path, "claude")
        d = _skill_dir(tmp_path)
        content = (d / "SKILL.md").read_text().lower()
        method = (d / "references" / "method-detail.md").read_text().lower()
        surface = content + "\n" + method
        # 1. independent adversarial verifier
        assert "verifier subagent" in surface
        assert "refute" in surface
        # 2. model / effort tiering
        assert "model tier" in surface
        # 3. ground-truth over LLM-judge
        assert "ground truth" in surface or "ground-truth" in surface
        # 4. context hygiene
        assert "context hygiene" in surface

    def test_body_and_template_carry_missions_contract_loop(self, tmp_path):
        """TAP-5552 / ADR-0034: validation contract + expected-fail fix loop."""
        generate_skills(tmp_path, "claude")
        d = _skill_dir(tmp_path)
        content = (d / "SKILL.md").read_text().lower()
        tpl = (d / "assets" / "prompt-template.md").read_text().lower()
        ref = (d / "references" / "claude-feature-map.md").read_text().lower()
        assert "validation contract" in content
        assert "expected-fail" in content
        assert "creator ≠ verifier" in content or "creator != verifier" in content
        assert "validation contract" in tpl
        assert "expected-fail" in tpl
        assert "structured handoff" in tpl
        assert "missions → orchestration-prompt" in ref or "missions" in ref

    def test_body_and_template_carry_wayfind_fog_gate(self, tmp_path):
        """TAP-5495: fog preflight, decide-vs-execute taxonomy, wayfind resume.

        TAP-7017: SKILL.md carries the condensed index (fog preflight refusal +
        the /tapps-wayfind redirect); the full elaboration — the "do not invent
        a Goal" statement, the taxonomy subheading, the cold-start resume detail
        — lives in references/method-detail.md, pointed at from SKILL.md.
        """
        generate_skills(tmp_path, "claude")
        d = _skill_dir(tmp_path)
        content = (d / "SKILL.md").read_text().lower()
        method = (d / "references" / "method-detail.md").read_text().lower()
        tpl = (d / "assets" / "prompt-template.md").read_text().lower()
        ref = (d / "references" / "claude-feature-map.md").read_text().lower()
        # method §0 fog preflight + redirect — condensed index, in SKILL.md itself
        assert "wayfind fog preflight" in content
        assert "/tapps-wayfind" in content
        # full elaboration — references/method-detail.md
        assert "do not invent a goal while the route is still foggy" in method
        # decide-vs-execute taxonomy
        assert "decide-vs-execute chunk taxonomy" in method
        assert "research-to-decide" in method
        # cold-start resume
        assert "memory_group=wayfind" in method
        # companion Prerequisites / Wayfind gate
        assert "prerequisites / wayfind gate" in tpl
        assert "memory_group=wayfind" in tpl
        assert "/tapps-wayfind" in tpl
        # anti-pattern in feature map
        assert "inventing a goal under fog" in ref

    def test_template_has_verifier_and_tier_columns(self, tmp_path):
        generate_skills(tmp_path, "claude")
        tpl = (_skill_dir(tmp_path) / "assets" / "prompt-template.md").read_text().lower()
        assert "agenttype" in tpl
        assert "model" in tpl
        assert "verifier subagent" in tpl

    def test_body_and_template_carry_harness_compatibility(self, tmp_path):
        """TAP-7017: method §6's harness-preflight rule and the Guardrails'
        adopt-or-override phrasing both moved to reference files — full
        elaboration in method-detail.md, the Guardrails restatement in
        guardrails-and-contracts.md — reachable from SKILL.md by pointer."""
        generate_skills(tmp_path, "claude")
        d = _skill_dir(tmp_path)
        method = (d / "references" / "method-detail.md").read_text().lower()
        guardrails = (d / "references" / "guardrails-and-contracts.md").read_text().lower()
        assert "harness preflight" in method
        assert "adopt or override" in method or "adopted or overridden" in method
        assert "adopt or override" in guardrails or "adopted or overridden" in guardrails
        ref = (d / "references" / "cold-start-and-verify.md").read_text().lower()
        assert "harness-compatibility sweep" in ref
        tpl = (d / "assets" / "prompt-template.md").read_text().lower()
        assert "harness compatibility" in tpl

    def test_capability_preflight_is_carried(self, tmp_path):
        """A granted tool that silently refuses is the AgentForge cornhole failure:
        the loop degrades into a confident wrong answer that reads as success.

        TAP-7017: the rule lives in references/method-detail.md now, alongside
        the rest of method §3's elaboration."""
        generate_skills(tmp_path, "claude")
        d = _skill_dir(tmp_path)
        method = (d / "references" / "method-detail.md").read_text().lower()
        assert "preflight the mechanism before you commit" in method
        ref = (d / "references" / "cold-start-and-verify.md").read_text().lower()
        assert "a grant is not a capability" in ref

    def test_feature_map_mirrors_all_eight_loops_anti_patterns(self, tmp_path):
        """TAP-5759: the canonical loops.md smell-list ships with the skill."""
        generate_skills(tmp_path, "claude")
        ref = (_skill_dir(tmp_path) / "references" / "claude-feature-map.md").read_text().lower()
        for canonical in (
            "vacuous verify",
            "prose judge",
            "gate outside the harness",
            "self-declared convergence",
            "goal-less workflow",
            "unreachable bar",
            "fan-out on ambiguity",
            "critic grades the tool, not the artifact",
        ):
            assert canonical in ref, f"missing loops.md anti-pattern: {canonical}"

    def test_body_carries_shift_boundaries_and_host_map(self, tmp_path):
        """v3.12.74: §7 shift boundaries + host-feature-map companion.

        TAP-7017: method §7's full elaboration moved to references/method-detail.md;
        SKILL.md keeps only the one-line index item ("Context lifecycle — recycle
        at every sub-goal boundary"), and Output (kept in full) still requires the
        prompt to name the boundary explicitly.
        """
        generate_skills(tmp_path, "claude")
        d = _skill_dir(tmp_path)
        method = (d / "references" / "method-detail.md").read_text().lower()
        assert "checkpoint the context window" in method or "shift boundary" in method
        assert "handoff-session" in method
        host = d / "references" / "host-feature-map.md"
        assert host.exists()
        assert "claude code" in host.read_text().lower()
        assert "cursor" in host.read_text().lower()
        cold = (d / "references" / "cold-start-and-verify.md").read_text().lower()
        assert "shift-boundary checkpoints" in cold
        assert "tapps session bootstrap" in cold

    def test_cursor_host_also_gets_skill(self, tmp_path):
        generate_skills(tmp_path, "cursor")
        assert (_skill_dir(tmp_path, "cursor") / "SKILL.md").exists()
        assert (_skill_dir(tmp_path, "cursor") / "references" / "claude-feature-map.md").exists()

    def test_run_as_names_both_execution_homes(self, tmp_path):
        """TAP-6589: an emitted Run-as naming only one home leaves the other
        implicit and the runner defaults to whichever one it's sitting in."""
        generate_skills(tmp_path, "claude")
        tpl = (_skill_dir(tmp_path) / "assets" / "prompt-template.md").read_text()
        run_as = tpl.split("## Run-as", 1)[1].split("\n## ", 1)[0]
        assert "in-session runner" in run_as.lower()
        assert "dispatch lane" in run_as.lower()
        assert "LINEAR EVIDENCE" in run_as
        assert "verify, merge" in run_as.lower() or (
            "verify" in run_as.lower() and "merge" in run_as.lower()
        )

    def test_skill_body_refuses_a_single_home_run_as(self, tmp_path):
        generate_skills(tmp_path, "claude")
        content = (_skill_dir(tmp_path) / "SKILL.md").read_text()
        assert "Refuse to emit a prompt whose Run-as names only one execution home" in content

    def test_claude_and_cursor_run_as_mirrors_are_byte_identical(self, tmp_path):
        generate_skills(tmp_path, "claude")
        generate_skills(tmp_path, "cursor")
        claude_tpl = (_skill_dir(tmp_path, "claude") / "assets" / "prompt-template.md").read_text()
        cursor_tpl = (_skill_dir(tmp_path, "cursor") / "assets" / "prompt-template.md").read_text()
        assert claude_tpl == cursor_tpl

    def test_multi_session_and_cost_discipline_sections_ship_in_a_regenerated_reference(
        self, tmp_path
    ):
        """TAP-6885: these two sections used to survive only in one repo below the

        SKILL.md END marker, where upgrade never touches them. The fix was to ship
        them from the platform emitter so a refresh actually propagates them.

        TAP-7017: SKILL.md's managed block was pushing 19% of a 200k context before
        any work started, so the section moved out of the block into
        ``references/multi-session-programs.md`` — a companion doc that
        ``generate_skills(..., overwrite=True)`` regenerates on every upgrade
        exactly like the managed block does (see TestSmartMerge.
        test_companion_docs_refresh_on_upgrade). Being *regenerated on upgrade* was
        the actual property TAP-6885 needed; the managed block was one way to get
        it, not the only one. SKILL.md carries an explicit pointer to the file.
        """
        generate_skills(tmp_path, "claude")
        d = _skill_dir(tmp_path)
        skill_md = (d / "SKILL.md").read_text()
        multi_session = (d / "references" / "multi-session-programs.md").read_text()

        assert "references/multi-session-programs.md" in skill_md, (
            "SKILL.md must point at the moved section explicitly"
        )
        assert "## Multi-session programs" in multi_session
        assert "### Cost discipline" in multi_session

        # References the standalone rule rather than restating its protocol.
        assert ".claude/rules/agent-to-agent.md" in multi_session
        assert "nine bad probes were nearly all" not in multi_session
        assert "All-pairs is N(N-1)/2" not in multi_session
        assert "the other three were never asked" not in multi_session

        # The reference regenerates on upgrade, same as any other companion doc.
        ref_path = d / "references" / "multi-session-programs.md"
        ref_path.write_text("stale\n", encoding="utf-8")
        generate_skills(tmp_path, "claude", overwrite=True)
        assert "## Multi-session programs" in ref_path.read_text()

    def test_multi_session_sections_are_absent_from_the_nlt_orchestrator_source(self, tmp_path):
        """The platform template must never carry the source repo's identity."""
        generate_skills(tmp_path, "claude")
        d = _skill_dir(tmp_path)
        content = (d / "SKILL.md").read_text()
        content += (d / "references" / "multi-session-programs.md").read_text()
        assert "nlt-orchestrator" not in content


class TestSmartMerge:
    def test_upgrade_preserves_project_region(self, tmp_path):
        generate_skills(tmp_path, "claude")
        skill_md = _skill_dir(tmp_path) / "SKILL.md"
        # Simulate a consumer appending a project region below the managed block.
        marker = "## Project: fleet wiring\n\nSee `fleet.md` for repo ids."
        skill_md.write_text(skill_md.read_text() + "\n\n" + marker, encoding="utf-8")

        generate_skills(tmp_path, "claude", overwrite=True)  # upgrade path
        after = skill_md.read_text()
        assert marker in after  # customization survived
        assert MARKER_END in after

    def test_learnings_not_overwritten_on_upgrade(self, tmp_path):
        generate_skills(tmp_path, "claude")
        learnings = _skill_dir(tmp_path) / "learnings.md"
        learnings.write_text("- my project lesson\n", encoding="utf-8")
        generate_skills(tmp_path, "claude", overwrite=True)
        assert learnings.read_text() == "- my project lesson\n"

    def test_companion_docs_refresh_on_upgrade(self, tmp_path):
        generate_skills(tmp_path, "claude")
        ref = _skill_dir(tmp_path) / "references" / "claude-feature-map.md"
        ref.write_text("stale\n", encoding="utf-8")
        generate_skills(tmp_path, "claude", overwrite=True)
        assert "feature map" in ref.read_text().lower()  # canonical content restored


class TestManagedBlockUnit:
    def test_created_then_unchanged(self, tmp_path):
        path = tmp_path / "SKILL.md"
        assert install_or_refresh_skill(path, "body v1", SKILL) == "created"
        assert install_or_refresh_skill(path, "body v1", SKILL) == "unchanged"

    def test_refreshed_on_body_change(self, tmp_path):
        path = tmp_path / "SKILL.md"
        install_or_refresh_skill(path, "body v1", SKILL)
        assert install_or_refresh_skill(path, "body v2", SKILL) == "refreshed"
        assert "body v2" in path.read_text()

    def test_legacy_migration_preserves_old_body(self, tmp_path):
        path = tmp_path / "SKILL.md"
        path.write_text("# hand-authored\n\nfleet-specific stuff\n", encoding="utf-8")
        assert install_or_refresh_skill(path, "platform body", SKILL) == "migrated"
        after = path.read_text()
        assert "platform body" in after  # managed block installed
        assert "fleet-specific stuff" in after  # old content preserved
        assert after.index(MARKER_BEGIN_PREFIX) < after.index("fleet-specific")

    def test_wrap_roundtrip_stamps_version(self, tmp_path):
        wrapped = wrap_with_markers("x", SKILL, version="9.9.9")
        assert f"{MARKER_BEGIN_PREFIX} {SKILL} v9.9.9 -->" in wrapped
        assert wrapped.endswith(MARKER_END)


class TestDoctorCheck:
    def test_fails_full_tier_when_missing(self, tmp_path):
        (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
        (tmp_path / ".tapps-mcp.yaml").write_text("skill_tier: full\n", encoding="utf-8")
        result = check_orchestration_prompt_skill_current(tmp_path)
        assert not result.ok
        assert "missing" in result.message

    def test_ok_core_tier_when_missing(self, tmp_path):
        (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
        (tmp_path / ".tapps-mcp.yaml").write_text("skill_tier: core\n", encoding="utf-8")
        result = check_orchestration_prompt_skill_current(tmp_path)
        assert result.ok
        assert "not required" in result.message

    def test_ok_when_fully_deployed(self, tmp_path):
        (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
        generate_skills(tmp_path, "claude")
        result = check_orchestration_prompt_skill_current(tmp_path)
        assert result.ok
        assert "current" in result.message

    def test_ok_when_fully_deployed_both_hosts(self, tmp_path):
        """TAP-6589: the .claude and .cursor scaffolded copies must both stay
        current — ``_tapps_skill_bases`` validates every host with a deployed
        MCP config or skills dir, so deploying both must pass for both."""
        (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
        (tmp_path / ".cursor" / "mcp.json").parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / ".cursor" / "mcp.json").write_text("{}", encoding="utf-8")
        generate_skills(tmp_path, "claude")
        generate_skills(tmp_path, "cursor")
        result = check_orchestration_prompt_skill_current(tmp_path)
        assert result.ok
        assert "current" in result.message

    def test_flags_missing_companion(self, tmp_path):
        (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
        generate_skills(tmp_path, "claude")
        (_skill_dir(tmp_path) / "references" / "claude-feature-map.md").unlink()
        result = check_orchestration_prompt_skill_current(tmp_path)
        assert not result.ok

    def test_flags_stale_unmarked_skill(self, tmp_path):
        (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
        d = _skill_dir(tmp_path)
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("# legacy hand-authored, no marker\n", encoding="utf-8")
        result = check_orchestration_prompt_skill_current(tmp_path)
        assert not result.ok
        assert "stale" in result.message

    def test_flags_stale_pre_missions_content(self, tmp_path):
        """Deployed skill without validation-contract markers fails doctor."""
        (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
        generate_skills(tmp_path, "claude")
        tpl = _skill_dir(tmp_path) / "assets" / "prompt-template.md"
        # Strip Missions fingerprints while keeping file present.
        tpl.write_text("# stale template without missions markers\n", encoding="utf-8")
        skill_md = _skill_dir(tmp_path) / "SKILL.md"
        # Also strip from managed body so combined check fails.
        text = skill_md.read_text()
        skill_md.write_text(
            text.replace("validation contract", "plan checklist")
            .replace("Expected-fail", "Retry")
            .replace("expected-fail", "retry"),
            encoding="utf-8",
        )
        result = check_orchestration_prompt_skill_current(tmp_path)
        assert not result.ok
        assert "stale content" in result.message


class TestManagedBlockLineCeiling:
    """TAP-7017 — the managed block must stay under 400 lines.

    Before TAP-7017 the emitted managed block was 1,097 lines (148,723 B,
    ~37,000 tokens in nlt-orchestrator) — roughly 19% of a 200k context spent
    before any work started. Progressive disclosure moved the bulk into
    ``references/``; this is the negative control that keeps it from creeping
    back: it demonstrates the assertion actually *fails* on an oversized
    block, not just that today's block happens to pass.
    """

    LINE_CEILING = 400

    @staticmethod
    def _managed_block_line_count(skill_md_text: str) -> int:
        block = extract_block(skill_md_text)
        assert block is not None, "no managed block found in SKILL.md"
        return len(block.splitlines())

    def test_emitted_managed_block_is_under_the_ceiling(self, tmp_path) -> None:
        generate_skills(tmp_path, "claude")
        skill_md = (_skill_dir(tmp_path) / "SKILL.md").read_text(encoding="utf-8")
        count = self._managed_block_line_count(skill_md)
        assert count < self.LINE_CEILING, (
            f"managed block grew to {count} lines (ceiling {self.LINE_CEILING}) — "
            "move the new content behind an explicit references/ pointer instead "
            "of inlining it in SKILL.md"
        )

    def test_the_ceiling_assertion_actually_fails_on_an_oversized_block(self) -> None:
        """Negative control: prove the check discriminates, not just that it's green.

        A padded copy of the real block, well past the ceiling, must fail the
        same assertion the previous test makes — otherwise the "ceiling" is a
        rubber stamp that would never catch a regression.
        """
        padding = "\nfiller line for the negative control\n" * self.LINE_CEILING
        oversized_body = ORCHESTRATION_PROMPT_SKILL_BODY + padding
        oversized_skill_md = wrap_with_markers(oversized_body, SKILL, version="9.9.9")

        count = self._managed_block_line_count(oversized_skill_md)
        assert count >= self.LINE_CEILING, "test setup failed to actually exceed the ceiling"

        with pytest.raises(AssertionError):
            assert count < self.LINE_CEILING

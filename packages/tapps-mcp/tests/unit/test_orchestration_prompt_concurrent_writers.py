"""Guardrails for a loop that assumes it is the only writer (TAP-6604, absorbs TAP-6740).

A loop authored by this skill runs for a long time in a shared filesystem — other
sessions, other lanes, or an operator can edit scripts/, git config, or temp
directories mid-run. Nothing in the emitted Guardrails said so, and nothing gated a
corrective git command on a fresh observation rather than a stale snapshot.

TAP-6740 (duplicate, closed into this issue) absorbed two more boxes: a phrase-level
superset check against nlt-orchestrator's own deployed template (read-only reference,
never edited from this worktree), and an upgrade --dry-run unknown-skip-token check —
the latter is reported in the lane's evidence block as `deferred`, since fixing it
requires editing a sibling repo's ``.tapps-mcp.yaml``, which is out of this lane's
scope (see ``.claude/rules/agent-scope.md``).
"""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.pipeline.platform_skill_orchestration import (
    ORCHESTRATION_PROMPT_COMPANION_FILES as COMPANIONS,
)

_GUARDRAILS = COMPANIONS["references/guardrails-and-contracts.md"]

_NLT_ORCHESTRATOR_REFERENCE_TEMPLATE = Path(
    "/home/wtthornton/code/nlt-orchestrator/.claude/skills/orchestration-prompt"
    "/assets/prompt-template.md"
)


def _guardrails_section() -> str:
    body = _GUARDRAILS
    return body.split("## Guardrails every emitted prompt must carry", 1)[1].split("\n## ", 1)[0]


class TestConcurrentWritersGuardrail:
    """TAP-6604 boxes 1-5 — the loop is never the only writer."""

    def test_states_shared_paths_may_change_under_a_running_loop(self) -> None:
        section = _guardrails_section()
        flat = " ".join(section.split())
        assert "Concurrent writers" in flat
        assert "never the only writer" in flat
        assert "Shared scripts, git config, and temp directories may change" in flat

    def test_requires_recording_the_shared_tool_version_actually_used(self) -> None:
        section = _guardrails_section()
        concurrent = " ".join(
            section.split("**Concurrent writers", 1)[1].split("\n- **", 1)[0].split()
        )
        assert "version of any shared tool actually" in concurrent
        assert "rather than inferring it from documentation" in concurrent

    def test_requires_copying_lane_logs_out_of_temp_on_completion(self) -> None:
        section = _guardrails_section()
        concurrent = " ".join(
            section.split("**Concurrent writers", 1)[1].split("\n- **", 1)[0].split()
        )
        assert "copies its own log out of the temp directory on completion" in concurrent

    def test_corrective_git_gated_on_reobservation_not_a_snapshot(self) -> None:
        section = _guardrails_section()
        concurrent = " ".join(
            section.split("**Concurrent writers", 1)[1].split("\n- **", 1)[0].split()
        )
        assert "never on a single status snapshot" in concurrent

    def test_triage_order_is_files_head_pushed_recovery_then_reobserve(self) -> None:
        section = _guardrails_section()
        concurrent = " ".join(
            section.split("**Concurrent writers", 1)[1].split("\n- **", 1)[0].split()
        )
        assert "files still on disk match what the" in concurrent
        assert "HEAD is still the commit" in concurrent
        assert "nothing was pushed out" in concurrent
        assert "recovery is a" in concurrent and "single command" in concurrent
        assert "observe again immediately before acting" in concurrent


class TestNltOrchestratorTemplateSuperset:
    """TAP-6740 boxes 3 — the regenerated template is a phrase-level superset of the
    deployed nlt-orchestrator copy, checked by section heading, not a line diff."""

    def _reference_headings(self) -> list[str]:
        if not _NLT_ORCHESTRATOR_REFERENCE_TEMPLATE.is_file():
            return []
        text = _NLT_ORCHESTRATOR_REFERENCE_TEMPLATE.read_text(encoding="utf-8")
        begin = text.index("<!-- BEGIN: tapps-skill-asset")
        end = text.index("<!-- END: tapps-skill-asset")
        managed = text[begin:end]
        headings = []
        for line in managed.splitlines():
            if line.startswith("## ") or line.startswith("### "):
                core = line.lstrip("#").strip()
                # Drop a trailing parenthetical annotation — e.g. "(REQUIRED — ...)" —
                # so an unrelated wording tweak to the annotation doesn't fail this.
                core = core.split("  (", 1)[0].split(" (", 1)[0]
                headings.append(core)
        return headings

    def test_reference_file_is_readable(self) -> None:
        assert _NLT_ORCHESTRATOR_REFERENCE_TEMPLATE.is_file(), (
            "nlt-orchestrator reference template not found at the pinned read-only "
            "path — cannot verify the superset relationship"
        )

    def test_every_reference_section_heading_survives_in_the_regenerated_template(
        self,
    ) -> None:
        headings = self._reference_headings()
        assert headings, "no managed-block headings parsed from the reference file"
        template = COMPANIONS["assets/prompt-template.md"]
        missing = [h for h in headings if h not in template]
        assert not missing, f"reference headings missing from regenerated template: {missing}"

    def test_run_as_bullets_from_the_reference_survive_under_the_new_dual_home_section(
        self,
    ) -> None:
        """The reference's (pre-TAP-6589) single-home Run-as bullets must still be
        present verbatim under the new in-session-runner sub-heading — TAP-6589 added
        a second home, it did not drop the first."""
        template = COMPANIONS["assets/prompt-template.md"]
        run_as = template.split("\n## Run-as", 1)[1].split("\n## ", 1)[0]
        for bullet in (
            '`/goal <condition>` — only if this file is already in context.',
            "invoke the Workflow tool with `.claude/workflows/<script>.js` (fan-out only).",
            "Routine: schedule `<cadence>` with this prompt, push=draft-PR.",
        ):
            assert bullet in run_as, f"pre-existing Run-as bullet dropped: {bullet!r}"

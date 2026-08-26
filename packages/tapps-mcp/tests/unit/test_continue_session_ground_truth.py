"""TAP-6498: ``tapps-continue-session`` verifies the handoff against ground truth.

Age is the weak staleness signal — a handoff goes wrong the moment work lands
after it was written, which is usually minutes, not days. The emitted skill has
to instruct three ground-truth probes (commit drift, tracker state, named PR
merge state) and rank their verdict above the 7-day warning.

The deliverable is template text, so these are emitted-text assertions against
both host variants and against the scaffolded output of ``generate_skills``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.pipeline.platform_skills import (
    CLAUDE_SKILLS,
    CURSOR_SKILLS,
    generate_skills,
)


class TestContinueSessionGroundTruthGate:
    """The gate must survive template regeneration, on both hosts.

    Age is the weak staleness signal: a handoff goes wrong the moment work lands
    after it was written. The emitted skill has to instruct three ground-truth
    probes and rank their verdict above the 7-day warning.
    """

    @staticmethod
    def _body(host_skills: dict[str, str]) -> str:
        return host_skills["tapps-continue-session"].split("---", 2)[-1]

    @pytest.fixture(params=["claude", "cursor"])
    def body(self, request: pytest.FixtureRequest) -> str:
        skills = CLAUDE_SKILLS if request.param == "claude" else CURSOR_SKILLS
        return self._body(skills)

    def test_gate_runs_before_the_continue_block(self, body: str) -> None:
        assert "Ground-truth gate" in body
        assert body.index("Ground-truth gate") < body.index("Emit continue block")

    def test_commit_drift_is_checked_against_git_log(self, body: str) -> None:
        """Acceptance 1 — compare the handoff sha to HEAD and name what landed."""
        assert "git log -1 --format=%h" in body
        assert "git log --oneline <handoff-sha>..HEAD" in body
        assert "every Open item as unverified" in body

    def test_benign_self_commit_case_is_named(self, body: str) -> None:
        """The handoff records HEAD at write time, then joins the next commit."""
        assert "stale by construction" in body

    def test_p0_status_is_reread_from_the_tracker(self, body: str) -> None:
        """Acceptance 2 — flag a P0 that is already Done or Canceled."""
        assert "get_issue" in body
        assert "**Done** or **Canceled**" in body

    def test_done_status_is_a_claim_in_both_directions(self, body: str) -> None:
        """Acceptance 7 — Done proves neither that work exists nor that it does not."""
        assert "claim in both directions" in body
        assert "auto-closed by a commit reference" in body

    def test_named_pr_merge_state_is_reread(self, body: str) -> None:
        """Acceptance 3 — never offer a PR as next action without re-reading it."""
        assert "gh pr view <N> --json state,mergedAt" in body
        assert "before offering it as a next action" in body

    def test_open_items_are_tagged_with_a_verdict(self, body: str) -> None:
        """Acceptance 4 — verified / corrected / unverified, per item."""
        assert "**verified**, **corrected**, or **unverified**" in body
        assert "Never restate an Open item as fact" in body

    def test_age_warning_is_kept_but_demoted(self, body: str) -> None:
        """Acceptance 5 — the 7-day signal survives, ranked below the drift line."""
        assert ">7 days old or missing" in body
        assert "*below* the drift line" in body
        assert body.index("**Drift**") < body.index("**Stale warning**")

    def test_conflict_corrects_the_handoff_before_proceeding(self, body: str) -> None:
        """Acceptance 6 — never leave a known-wrong artifact behind."""
        assert "correct `.tapps-mcp/session-handoff.md` before proceeding" in body
        assert "known-wrong artifact" in body

    def test_steps_are_renumbered_without_collision(self, body: str) -> None:
        for step in ("3. **Ground-truth gate", "4. **Linear context", "5. **Emit continue block"):
            assert body.count(step) == 1, step
        assert "7. **Proceed on P0.**" in body

    def test_generated_skill_carries_the_gate(self, tmp_path: Path) -> None:
        for host in ("claude", "cursor"):
            generate_skills(tmp_path, host)
            content = (
                tmp_path / f".{host}" / "skills" / "tapps-continue-session" / "SKILL.md"
            ).read_text()
            assert "Ground-truth gate" in content
            assert "git log -1 --format=%h" in content

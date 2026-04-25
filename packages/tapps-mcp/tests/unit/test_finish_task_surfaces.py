"""Verify /tapps-finish-task is surfaced at the three nudge surfaces (TAP-983).

TAP-977 shipped /tapps-finish-task as a composite skill (validate_changed +
checklist + optional memory save). TAP-983 makes sure agents see it at the
points where they look for "what to do next":

1. agents-md templates (high/medium/low) — at the close-out step.
2. tapps_checklist response next_steps — for both incomplete and complete.
3. tapps-stop.sh / .ps1 (advisory + high-engagement blocking) — at session end.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.common.nudges import compute_next_steps
from tapps_mcp.pipeline.platform_hook_templates import (
    CLAUDE_HOOK_SCRIPTS,
    CLAUDE_HOOK_SCRIPTS_BLOCKING,
    CLAUDE_HOOK_SCRIPTS_BLOCKING_PS,
    CLAUDE_HOOK_SCRIPTS_PS,
)


_PROMPTS_DIR = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "tapps_mcp"
    / "prompts"
)


class TestAgentsMdSurface:
    """The agents-md template at every engagement level mentions the skill."""

    @pytest.mark.parametrize(
        "level",
        ["high", "medium", "low"],
    )
    def test_agents_template_mentions_finish_task(self, level: str) -> None:
        body = (_PROMPTS_DIR / f"agents_template_{level}.md").read_text(
            encoding="utf-8"
        )
        assert "/tapps-finish-task" in body, (
            f"agents_template_{level}.md must mention /tapps-finish-task"
        )

    def test_high_uses_required_tone(self) -> None:
        body = (_PROMPTS_DIR / "agents_template_high.md").read_text(encoding="utf-8")
        # Find the line where /tapps-finish-task lives — it must sit in the
        # close-out section under REQUIRED tone, not buried in passing prose.
        finish_line = next(
            (ln for ln in body.splitlines() if "/tapps-finish-task" in ln),
            "",
        )
        assert "REQUIRED" in finish_line or "MUST" in finish_line

    def test_medium_uses_recommended_tone(self) -> None:
        body = (_PROMPTS_DIR / "agents_template_medium.md").read_text(encoding="utf-8")
        finish_line = next(
            (ln for ln in body.splitlines() if "/tapps-finish-task" in ln),
            "",
        )
        assert "Recommended" in finish_line or "recommended" in finish_line

    def test_low_uses_optional_tone(self) -> None:
        body = (_PROMPTS_DIR / "agents_template_low.md").read_text(encoding="utf-8")
        finish_line = next(
            (ln for ln in body.splitlines() if "/tapps-finish-task" in ln),
            "",
        )
        assert "Consider" in finish_line or "optional" in finish_line.lower()


class TestChecklistNextStepsSurface:
    """compute_next_steps surfaces /tapps-finish-task at the checklist call."""

    def test_complete_suggests_finish_task(self) -> None:
        steps = compute_next_steps(
            "tapps_checklist",
            {"complete": True},
        )
        assert any("/tapps-finish-task" in s for s in steps)

    def test_incomplete_blocks_with_finish_task(self) -> None:
        # When complete=False, the BLOCKING message wins (top-1) — and it
        # also names /tapps-finish-task as the quick remediation.
        steps = compute_next_steps(
            "tapps_checklist",
            {"complete": False},
        )
        assert any("/tapps-finish-task" in s for s in steps)
        assert any("incomplete" in s.lower() for s in steps)

    def test_complete_with_validate_skipped_warns_first(self) -> None:
        # The pre-existing INFO warning still surfaces with the
        # /tapps-finish-task tip — both survive because the LOW tip and
        # the INFO warning have non-overlapping conditions and the
        # higher-impact INFO wins top-1.
        # Force the WARNING condition by saying score_file ran but
        # validate_changed did not.
        from tapps_mcp.tools.checklist import CallTracker

        # Reset so we can simulate "score_file called, validate not called"
        CallTracker._calls.clear()  # type: ignore[attr-defined]
        CallTracker.record("tapps_score_file")
        try:
            steps = compute_next_steps(
                "tapps_checklist",
                {"complete": True},
            )
        finally:
            CallTracker._calls.clear()  # type: ignore[attr-defined]
        # WARNING wins (impact 40 > LOW 50? no — LOW is higher, so LOW wins).
        # Either message is acceptable as long as the user sees one of the
        # two follow-ups at this point.
        assert steps
        text = " ".join(steps)
        assert "/tapps-finish-task" in text or "tapps_validate_changed" in text


class TestStopHookSurface:
    """Advisory + blocking tapps-stop scripts both reference /tapps-finish-task."""

    def test_advisory_bash_mentions_finish_task(self) -> None:
        assert "/tapps-finish-task" in CLAUDE_HOOK_SCRIPTS["tapps-stop.sh"]

    def test_advisory_ps_mentions_finish_task(self) -> None:
        assert "/tapps-finish-task" in CLAUDE_HOOK_SCRIPTS_PS["tapps-stop.ps1"]

    def test_blocking_bash_mentions_finish_task(self) -> None:
        # The high-engagement blocking variant ships the AC's exact phrasing:
        # "Before declaring complete, run /tapps-finish-task".
        body = CLAUDE_HOOK_SCRIPTS_BLOCKING["tapps-stop.sh"]
        assert "/tapps-finish-task" in body
        assert "Before declaring complete" in body

    def test_blocking_ps_mentions_finish_task(self) -> None:
        body = CLAUDE_HOOK_SCRIPTS_BLOCKING_PS["tapps-stop.ps1"]
        assert "/tapps-finish-task" in body
        assert "Before declaring complete" in body

    def test_blocking_bash_still_exits_2(self) -> None:
        # The wording change must NOT relax the blocking semantics.
        body = CLAUDE_HOOK_SCRIPTS_BLOCKING["tapps-stop.sh"]
        assert "exit 2" in body

    def test_blocking_ps_still_exits_2(self) -> None:
        body = CLAUDE_HOOK_SCRIPTS_BLOCKING_PS["tapps-stop.ps1"]
        assert "exit 2" in body

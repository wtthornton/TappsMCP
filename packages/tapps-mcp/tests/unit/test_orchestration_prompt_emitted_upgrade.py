"""End-to-end assertion that ``generate_skills`` actually emits the TAP-6854 cluster.

The sibling modules assert against the in-memory constants. This one writes the skill
the way ``tapps_init`` / ``tapps_upgrade`` do and reads the files back, so a section
that exists in the constant but never reaches a consumer's disk still fails.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.pipeline.platform_skills import generate_skills

SKILL_SECTIONS = [
    "### 0c. Research preflight before design choices",  # TAP-6855
    "workspace directory list is the scope",  # TAP-6856
    "## Field rules",  # TAP-6858
    "## Rulings",  # TAP-6859
    "**This table is authoritative.**",  # TAP-6859
    "## Terminal contract (hard stop",  # TAP-6946
    "> **CARGO",  # TAP-6946
    "**Floor first; escalate only with a stated reason.**",  # TAP-6947
    "**Scope admission is announced, not forbidden.**",  # TAP-6947
    "## Verification routing and honest reporting",  # TAP-6948 Story 4
]

TEMPLATE_SECTIONS = [
    "- **Session setup (paste these two lines first):**",  # TAP-6946
    "**Floor and justify.**",  # TAP-6947
    "pct <n>%",  # TAP-6947
    "elapsed <hh:mm>",  # TAP-6947
    "Triage the queue before executing any of it.",  # TAP-6947
    "every touched issue ends **terminal**",  # TAP-6947
]


@pytest.fixture(scope="module")
def emitted(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    """Generate the skill onto disk once and hand back the files as text."""
    root = tmp_path_factory.mktemp("emitted-skills")
    generate_skills(root, "claude")
    skill_dir = root / ".claude" / "skills" / "orchestration-prompt"
    return {
        "skill": (skill_dir / "SKILL.md").read_text(encoding="utf-8"),
        "template": (skill_dir / "assets" / "prompt-template.md").read_text(encoding="utf-8"),
    }


class TestEmittedOrchestrationSkill:
    """TAP-6854 — every cluster section survives the emit path, not just the constant."""

    @pytest.mark.parametrize("marker", SKILL_SECTIONS)
    def test_skill_body_carries_section(self, emitted: dict[str, str], marker: str) -> None:
        assert marker in emitted["skill"], f"{marker!r} missing from the emitted SKILL.md"

    @pytest.mark.parametrize("marker", TEMPLATE_SECTIONS)
    def test_template_carries_section(self, emitted: dict[str, str], marker: str) -> None:
        assert marker in emitted["template"], f"{marker!r} missing from the emitted template"

    def test_every_section_lands_inside_the_managed_block(self, emitted: dict[str, str]) -> None:
        """A section below the END marker would be a consumer's region, not ours."""
        skill = emitted["skill"]
        end = skill.index("<!-- END: tapps-skill -->")
        for marker in SKILL_SECTIONS:
            assert skill.index(marker) < end, f"{marker!r} landed outside the managed block"

    @pytest.mark.parametrize(
        ("host_dir", "platform"),
        [(".claude", "claude"), (".cursor", "cursor")],
    )
    def test_repo_checked_in_copy_matches_the_emitter(
        self, host_dir: str, platform: str
    ) -> None:
        """The tracked copy under .claude/ AND .cursor/ is regenerated, never hand-edited.

        TAP-6854 round 2: the original version of this test asserted only the
        .claude copy, so a .cursor mirror could go stale (regenerated content
        never reaching a consumer's disk on that host) without this test
        noticing — exactly what happened to the orchestration-prompt skill's
        .cursor copy. Both hosts share the same section markers because
        CLAUDE_SKILLS and CURSOR_SKILLS both point at
        ORCHESTRATION_PROMPT_SKILL_BODY (platform_skills.py), so the same
        marker list applies regardless of which host emitted the file.
        """
        repo_root = Path(__file__).resolve().parents[4]
        tracked = repo_root / host_dir / "skills" / "orchestration-prompt" / "SKILL.md"
        if not tracked.exists():  # pragma: no cover - consumer checkouts have no copy
            pytest.skip(f"this checkout does not track an emitted {platform} copy of the skill")
        body = tracked.read_text(encoding="utf-8")
        for marker in SKILL_SECTIONS:
            assert marker in body, (
                f"{marker!r} missing from the tracked emitted {platform} copy"
            )

"""End-to-end assertion that ``generate_skills`` actually emits the TAP-6854 cluster.

The sibling modules assert against the in-memory constants. This one writes the skill
the way ``tapps_init`` / ``tapps_upgrade`` do and reads the files back, so a section
that exists in the constant but never reaches a consumer's disk still fails.

TAP-7017 moved most of these sections out of SKILL.md's managed block (pushing 19%
of a 200k context before any work started) into reference files under
``references/``, each reachable from SKILL.md by an explicit pointer. Two of the
original ten markers stay inside the managed block (Terminal contract, and the
cargo marker it explains); the rest now live in a named reference file and are
checked there instead — still regenerated on every ``tapps_upgrade``, just no
longer inside the BEGIN/END span.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.pipeline.platform_skills import generate_skills

# Markers that stay inside the SKILL.md managed block itself.
SKILL_SECTIONS = [
    "## Terminal contract (hard stop",  # TAP-6946
    "> **CARGO",  # TAP-6946
]

# Markers moved to references/method-detail.md (TAP-7017).
METHOD_DETAIL_SECTIONS = [
    "### 0c. Research preflight before design choices",  # TAP-6855
    "**This table is authoritative.**",  # TAP-6859
    "**Floor first; escalate only with a stated reason.**",  # TAP-6947
]

# Markers moved to references/field-rules-and-rulings.md (TAP-7017).
FIELD_RULES_AND_RULINGS_SECTIONS = [
    "## Field rules",  # TAP-6858
    "## Rulings",  # TAP-6859
]

# Markers moved to references/verification-routing.md (TAP-7017).
VERIFICATION_ROUTING_SECTIONS = [
    "## Verification routing and honest reporting",  # TAP-6948 Story 4
]

# Markers moved to references/guardrails-and-contracts.md (TAP-7017).
GUARDRAILS_AND_CONTRACTS_SECTIONS = [
    "workspace directory list is the scope",  # TAP-6856
    "**Two mechanisms, two actors — do not conflate them.**",  # TAP-6605 round 2
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
    refs = skill_dir / "references"
    return {
        "skill": (skill_dir / "SKILL.md").read_text(encoding="utf-8"),
        "template": (skill_dir / "assets" / "prompt-template.md").read_text(encoding="utf-8"),
        "method-detail": (refs / "method-detail.md").read_text(encoding="utf-8"),
        "field-rules-and-rulings": (refs / "field-rules-and-rulings.md").read_text(
            encoding="utf-8"
        ),
        "verification-routing": (refs / "verification-routing.md").read_text(encoding="utf-8"),
        "guardrails-and-contracts": (refs / "guardrails-and-contracts.md").read_text(
            encoding="utf-8"
        ),
        "references-dir": str(refs),
    }


class TestEmittedOrchestrationSkill:
    """TAP-6854 — every cluster section survives the emit path, not just the constant."""

    @pytest.mark.parametrize("marker", SKILL_SECTIONS)
    def test_skill_body_carries_section(self, emitted: dict[str, str], marker: str) -> None:
        assert marker in emitted["skill"], f"{marker!r} missing from the emitted SKILL.md"

    @pytest.mark.parametrize("marker", METHOD_DETAIL_SECTIONS)
    def test_method_detail_carries_section(self, emitted: dict[str, str], marker: str) -> None:
        assert marker in emitted["method-detail"], (
            f"{marker!r} missing from the emitted references/method-detail.md"
        )

    @pytest.mark.parametrize("marker", FIELD_RULES_AND_RULINGS_SECTIONS)
    def test_field_rules_and_rulings_carries_section(
        self, emitted: dict[str, str], marker: str
    ) -> None:
        assert marker in emitted["field-rules-and-rulings"], (
            f"{marker!r} missing from the emitted references/field-rules-and-rulings.md"
        )

    @pytest.mark.parametrize("marker", VERIFICATION_ROUTING_SECTIONS)
    def test_verification_routing_carries_section(
        self, emitted: dict[str, str], marker: str
    ) -> None:
        assert marker in emitted["verification-routing"], (
            f"{marker!r} missing from the emitted references/verification-routing.md"
        )

    @pytest.mark.parametrize("marker", GUARDRAILS_AND_CONTRACTS_SECTIONS)
    def test_guardrails_and_contracts_carries_section(
        self, emitted: dict[str, str], marker: str
    ) -> None:
        assert marker in emitted["guardrails-and-contracts"], (
            f"{marker!r} missing from the emitted references/guardrails-and-contracts.md"
        )

    @pytest.mark.parametrize("marker", TEMPLATE_SECTIONS)
    def test_template_carries_section(self, emitted: dict[str, str], marker: str) -> None:
        assert marker in emitted["template"], f"{marker!r} missing from the emitted template"

    def test_every_skill_section_lands_inside_the_managed_block(
        self, emitted: dict[str, str]
    ) -> None:
        """A section below the END marker would be a consumer's region, not ours."""
        skill = emitted["skill"]
        end = skill.index("<!-- END: tapps-skill -->")
        for marker in SKILL_SECTIONS:
            assert skill.index(marker) < end, f"{marker!r} landed outside the managed block"

    def test_skill_points_at_every_reference_file_it_moved_content_into(
        self, emitted: dict[str, str]
    ) -> None:
        """Progressive disclosure only works if the pointer is loud (TAP-7017).

        Derived from the actual ``references/`` directory the emitter writes, not a
        hardcoded list — a hardcoded subset structurally cannot notice a file that
        the emitter later adds without a pointer.
        """
        skill = emitted["skill"]
        refs_dir = Path(emitted["references-dir"])
        names = sorted(p.name for p in refs_dir.glob("*.md"))
        assert names, "no reference files were emitted"
        for name in names:
            ref = f"references/{name}"
            assert ref in skill, f"SKILL.md carries no pointer to {ref!r}"

    @pytest.mark.parametrize(
        ("host_dir", "platform"),
        [(".claude", "claude"), (".cursor", "cursor")],
    )
    def test_repo_checked_in_copy_matches_the_emitter(self, host_dir: str, platform: str) -> None:
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
        skill_dir = repo_root / host_dir / "skills" / "orchestration-prompt"
        tracked = skill_dir / "SKILL.md"
        if not tracked.exists():  # pragma: no cover - consumer checkouts have no copy
            pytest.skip(f"this checkout does not track an emitted {platform} copy of the skill")
        body = tracked.read_text(encoding="utf-8")
        for marker in SKILL_SECTIONS:
            assert marker in body, f"{marker!r} missing from the tracked emitted {platform} copy"
        refs = skill_dir / "references"
        for markers, filename in (
            (METHOD_DETAIL_SECTIONS, "method-detail.md"),
            (FIELD_RULES_AND_RULINGS_SECTIONS, "field-rules-and-rulings.md"),
            (VERIFICATION_ROUTING_SECTIONS, "verification-routing.md"),
            (GUARDRAILS_AND_CONTRACTS_SECTIONS, "guardrails-and-contracts.md"),
        ):
            ref_text = (refs / filename).read_text(encoding="utf-8")
            for marker in markers:
                assert marker in ref_text, (
                    f"{marker!r} missing from the tracked emitted {platform} {filename}"
                )

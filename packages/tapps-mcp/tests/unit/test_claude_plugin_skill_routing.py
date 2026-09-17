"""The Claude plugin bundle must not route to a skill it does not ship.

TAP-7753 round 3. Round 2 filtered ``linear-issue`` out of the bundle and left
six shipped references still pointing at it -- including a mandatory "Linear
writes only via `linear-issue`" in tapps-wayfind. That is the same defect class
part (e) of ``scripts/validate-claude-plugin.sh`` exists to prevent (an
instruction naming something unreachable), one layer up: part (e) scans
``mcp__*`` TOOL prefixes and is structurally blind to skill-to-skill routing.

Kept in its own module rather than appended to test_claude_plugin_bundle.py so
this class reads as the one property it holds, alongside its own negative and
precision controls.
"""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.pipeline.platform_generators import (
    generate_claude_plugin_bundle,
)


class TestBundleRoutesOnlyToSkillsItShips:
    """Both sides are derived — the shipped set from the generated bundle, the
    reference universe from ``CLAUDE_SKILLS``, the required note text from
    ``excluded_skill_note_marker`` — so nothing here drifts out of sync with
    the bundler by being retyped."""

    @staticmethod
    def _referenced(text: str, universe: set[str]) -> set[str]:
        """Skill names *text* routes to: a backticked `name` or a /name
        slash-command. Matches what the bundler's annotator looks for."""
        return {n for n in universe if f"`{n}`" in text or f"/{n}" in text}

    def _offenders(self, skills_dir: Path, missing: set[str]) -> list[str]:
        from tapps_mcp.pipeline.claude_plugin_skill_exclusions import excluded_skill_note_marker

        out = []
        for path in sorted(skills_dir.rglob("SKILL.md")):
            text = path.read_text(encoding="utf-8")
            for name in sorted(self._referenced(text, missing)):
                if excluded_skill_note_marker(name) not in text:
                    out.append(f"{path.parent.name} -> {name}")
        return out

    def test_every_reference_to_an_unshipped_skill_is_qualified(self, tmp_path):
        from tapps_mcp.pipeline.platform_skills import CLAUDE_SKILLS

        generate_claude_plugin_bundle(tmp_path)
        skills_dir = tmp_path / "skills"
        shipped = {p.name for p in skills_dir.iterdir() if p.is_dir()}
        missing = set(CLAUDE_SKILLS) - shipped
        # Guard the guard: with nothing missing this assertion is vacuous.
        assert missing, "bundle ships every registered skill — check is vacuous"

        assert self._offenders(skills_dir, missing) == []

    def test_negative_control_unqualified_reference_is_caught(self, tmp_path):
        """Strip the note from one generated file and the SAME predicate must
        report it. Without this, a check that never saw the failing state
        would be indistinguishable from one that cannot see it."""
        from tapps_mcp.pipeline.claude_plugin_skill_exclusions import excluded_skill_note_marker
        from tapps_mcp.pipeline.platform_skills import CLAUDE_SKILLS

        generate_claude_plugin_bundle(tmp_path)
        skills_dir = tmp_path / "skills"
        shipped = {p.name for p in skills_dir.iterdir() if p.is_dir()}
        missing = set(CLAUDE_SKILLS) - shipped
        assert self._offenders(skills_dir, missing) == []

        victim = skills_dir / "tapps-wayfind" / "SKILL.md"
        text = victim.read_text(encoding="utf-8")
        marker = excluded_skill_note_marker("linear-issue")
        assert marker in text and "`linear-issue`" in text
        victim.write_text(text.replace(marker, "REMOVED"), encoding="utf-8")

        assert self._offenders(skills_dir, missing) == ["tapps-wayfind -> linear-issue"]

    def test_precision_note_only_where_a_reference_exists(self, tmp_path):
        """The annotation is not sprayed over every skill — a file that never
        routes to an excluded skill must not carry the note. A blanket
        annotation would make the positive check above pass by construction."""
        from tapps_mcp.pipeline.claude_plugin_skill_exclusions import excluded_skill_note_marker
        from tapps_mcp.pipeline.platform_skills import CLAUDE_SKILLS

        generate_claude_plugin_bundle(tmp_path)
        skills_dir = tmp_path / "skills"
        shipped = {p.name for p in skills_dir.iterdir() if p.is_dir()}
        missing = set(CLAUDE_SKILLS) - shipped
        marker = excluded_skill_note_marker("linear-issue")

        annotated = set()
        referencing = set()
        for path in sorted(skills_dir.rglob("SKILL.md")):
            text = path.read_text(encoding="utf-8")
            if marker in text:
                annotated.add(path.parent.name)
            if self._referenced(text, missing):
                referencing.add(path.parent.name)

        assert annotated == referencing
        assert 0 < len(annotated) < len(shipped)

    def test_the_known_round_2_dangling_references_are_covered(self, tmp_path):
        """Name the three files the round-2 refutation found, so a silent loss
        of the annotation on any of them is visible as more than a count."""
        from tapps_mcp.pipeline.claude_plugin_skill_exclusions import excluded_skill_note_marker

        generate_claude_plugin_bundle(tmp_path)
        marker = excluded_skill_note_marker("linear-issue")
        for name in ("tapps-wayfind", "linear-read", "tapps-validation-contract"):
            text = (tmp_path / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
            assert "`linear-issue`" in text, name
            assert marker in text, name

"""Tests for the contradiction detector (TAP-6863) and promote guard (TAP-6864).

Both live in ``skill_managed_block`` alongside the marker/span mechanics they
reuse (``_find_block_span``). See ``skill_managed_block.py`` module docstring
for the two-region model: content inside ``BEGIN``/``END`` is platform-owned
and regenerated on ``tapps_upgrade``; content outside it is project-owned and
survives.
"""

from __future__ import annotations

from tapps_mcp.pipeline.skill_managed_block import (
    MARKER_BEGIN_PREFIX,
    MARKER_END,
    UPGRADE_POLICY_OVERWRITE_MARKER,
    Contradiction,
    find_contradictions,
    promote_rule,
)

GENERATOR_FILE = "pipeline/platform_skills.py"


def _skill_file(managed_bullets: str, project_bullets: str) -> str:
    return (
        "---\nname: demo\ndescription: A demo skill.\n---\n\n"
        f"{MARKER_BEGIN_PREFIX} demo v1.0.0 -->\n"
        "policy header\n\n"
        f"{managed_bullets}\n"
        f"{MARKER_END}\n\n"
        f"{project_bullets}\n"
    )


# --- TAP-6863: contradiction detection -------------------------------------


class TestFindContradictions:
    def test_verifier_tier_regression_fixture_is_flagged(self):
        """Real incident (TAP-6863): a stale project-region line silently won
        over the managed block's proof-shape tiering, so 8 verifiers ran at
        opus on proofs an exit code had already settled."""
        content = _skill_file(
            managed_bullets=(
                "- Verifiers are tiered by proof shape — deterministic proofs "
                "run haiku, comparative proofs run sonnet, semantic proofs run opus."
            ),
            project_bullets=(
                "- Verifiers inherit the runner's tier at high effort, regardless of proof shape."
            ),
        )

        findings = find_contradictions(content)

        assert len(findings) == 1
        finding = findings[0]
        assert isinstance(finding, Contradiction)
        assert finding.kind == "contradiction"
        assert "tiered by proof shape" in finding.managed_text
        assert "inherit the runner's tier" in finding.project_text
        assert finding.managed_line > 0
        assert finding.project_line > 0

    def test_finding_kind_is_distinct_from_near_duplicate(self):
        finding = Contradiction(
            managed_text="a",
            managed_line=1,
            project_text="b",
            project_line=2,
        )
        assert finding.kind == "contradiction"
        assert finding.kind != "near_duplicate"

    def test_unrelated_project_addition_does_not_flag(self):
        """A legitimate customization that adds a new rule, restating nothing
        from the managed block, must not be flagged (acceptance criterion 3)."""
        content = _skill_file(
            managed_bullets=(
                "- Verifiers are tiered by proof shape — deterministic proofs "
                "run haiku, comparative proofs run sonnet, semantic proofs run opus."
            ),
            project_bullets="- Fleet manifest refs live in .tapps-mcp.yaml under fleet_repos.",
        )

        assert find_contradictions(content) == []

    def test_near_identical_restatement_is_not_a_contradiction(self):
        """Same claim, reworded — agreement, not conflict."""
        content = _skill_file(
            managed_bullets="- Verifiers are tiered by proof shape.",
            project_bullets="- Verifiers are tiered by proof shape.",
        )

        assert find_contradictions(content) == []

    def test_no_managed_block_returns_no_findings(self):
        assert find_contradictions("# Just a heading\n\n- some bullet\n") == []

    def test_never_auto_resolves_reports_both_anchors(self):
        """The check must report both sides, never pick a winner."""
        content = _skill_file(
            managed_bullets=(
                "- Verifiers are tiered by proof shape — deterministic proofs "
                "run haiku, comparative proofs run sonnet, semantic proofs run opus."
            ),
            project_bullets=(
                "- Verifiers inherit the runner's tier at high effort, regardless of proof shape."
            ),
        )
        finding = find_contradictions(content)[0]
        assert finding.managed_text and finding.project_text

    def test_deterministic_and_reproducible_from_bytes(self):
        """No model call: identical bytes in, identical findings out."""
        content = _skill_file(
            managed_bullets=(
                "- Verifiers are tiered by proof shape — deterministic proofs "
                "run haiku, comparative proofs run sonnet, semantic proofs run opus."
            ),
            project_bullets=(
                "- Verifiers inherit the runner's tier at high effort, regardless of proof shape."
            ),
        )
        assert find_contradictions(content) == find_contradictions(content)


# --- TAP-6864: promote + destination guard ----------------------------------


class TestPromoteRule:
    def test_promotion_inside_managed_block_is_refused(self):
        content = _skill_file(
            managed_bullets="- Existing rule.",
            project_bullets="- Project rule.",
        )
        inside_offset = content.index("Existing rule.")

        outcome = promote_rule(content, inside_offset, generator_file=GENERATOR_FILE)

        assert outcome.accepted is False
        assert outcome.region == "managed_block"
        assert "erased" in outcome.reason or "erase" in outcome.reason
        assert "tapps_upgrade" in outcome.reason
        assert outcome.generator_file == GENERATOR_FILE

    def test_promotion_below_end_marker_succeeds(self):
        content = _skill_file(
            managed_bullets="- Existing rule.",
            project_bullets="- Project rule.",
        )
        below_offset = content.index("Project rule.")

        outcome = promote_rule(content, below_offset, generator_file=GENERATOR_FILE)

        assert outcome.accepted is True
        assert outcome.region == "project_region"

    def test_promotion_into_overwrite_policy_file_is_refused_regardless_of_position(self):
        content = (
            f"<!-- {UPGRADE_POLICY_OVERWRITE_MARKER}. Whole file replaced on upgrade. -->\n"
            "---\nname: demo\ndescription: overwrite-managed skill.\n---\n\n"
            "- Some rule, no managed block markers at all.\n"
        )
        below_offset = content.index("Some rule")

        outcome = promote_rule(content, below_offset, generator_file=GENERATOR_FILE)

        assert outcome.accepted is False
        assert UPGRADE_POLICY_OVERWRITE_MARKER in outcome.reason

    def test_promotion_into_overwrite_policy_file_refused_even_inside_a_block(self):
        content = _skill_file(
            managed_bullets=f"- Some rule.\n<!-- {UPGRADE_POLICY_OVERWRITE_MARKER} -->",
            project_bullets="- Project rule.",
        )
        inside_offset = content.index("Some rule.")

        outcome = promote_rule(content, inside_offset, generator_file=GENERATOR_FILE)

        assert outcome.accepted is False
        assert UPGRADE_POLICY_OVERWRITE_MARKER in outcome.reason

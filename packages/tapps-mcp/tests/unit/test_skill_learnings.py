"""Tests for the skill-learnings audit / verify / trim pipeline (TAP-6862,
TAP-6865, TAP-6866).

Fixtures are synthetic, not real skill files — each test builds the smallest
``SKILL.md`` / ``learnings.md`` pair needed to exercise one finding class or
outcome, per the acceptance criteria on each issue.
"""

from __future__ import annotations

from tapps_mcp.pipeline.skill_learnings import (
    LEARNINGS_CEILING_BYTES,
    TrimInstruction,
    apply_trim,
    audit,
    bullet_content_hash,
    verify_single_home,
)
from tapps_mcp.pipeline.skill_managed_block import MARKER_BEGIN_PREFIX, MARKER_END

SKILL_MD = (
    "---\nname: demo\ndescription: A demo skill.\n---\n\n"
    f"{MARKER_BEGIN_PREFIX} demo v1.0.0 -->\n"
    "policy header\n\n"
    "## Method\n"
    "- Verifiers are tiered by proof shape — deterministic proofs run haiku, "
    "comparative proofs run sonnet, semantic proofs run opus.\n"
    f"{MARKER_END}\n\n"
    "## Project customizations\n"
    "- Fleet manifest refs live in .tapps-mcp.yaml under fleet_repos.\n"
)


# --- TAP-6862: audit ---------------------------------------------------------


class TestAudit:
    def test_size_finding_reports_bytes_and_bullet_count(self):
        learnings = "- one bullet\n- two bullet\n"
        report = audit(SKILL_MD, learnings)

        assert report.size.bytes == len(learnings.encode("utf-8"))
        assert report.size.bullet_count == 2
        assert report.size.ceiling_bytes == LEARNINGS_CEILING_BYTES
        assert report.size.over_ceiling is False

    def test_size_finding_flags_over_ceiling(self):
        learnings = "- padding bullet that repeats itself needlessly\n" * 2000
        report = audit(SKILL_MD, learnings)

        assert report.size.over_ceiling is True
        assert report.size.bytes > LEARNINGS_CEILING_BYTES

    def test_already_covered_bullet_carries_covering_anchor(self):
        learnings = (
            "- Verifiers are tiered by proof shape, deterministic runs haiku, "
            "comparative runs sonnet, semantic runs opus.\n"
        )
        report = audit(SKILL_MD, learnings)

        assert len(report.already_covered) == 1
        finding = report.already_covered[0]
        assert finding.kind == "already_covered"
        assert finding.covering_anchor == "Method"
        assert "tiered by proof shape" in finding.skill_text

    def test_unrelated_learnings_bullet_is_not_already_covered(self):
        learnings = "- Retry the flaky network call up to three times.\n"
        report = audit(SKILL_MD, learnings)

        assert report.already_covered == ()

    def test_near_duplicate_pair_forms_one_cluster_with_a_survivor(self):
        learnings = (
            "- Run tapps_quick_check after every Python file edit.\n"
            "- Always run tapps_quick_check after every Python file edit.\n"
            "- Completely unrelated bullet about something else entirely.\n"
        )
        report = audit(SKILL_MD, learnings)

        assert len(report.near_duplicate) == 1
        cluster = report.near_duplicate[0]
        assert cluster.kind == "near_duplicate"
        assert len(cluster.members) == 2
        assert cluster.suggested_survivor_line in {1, 2}

    def test_region_finding_tags_managed_and_project_bullets(self):
        report = audit(SKILL_MD, "- some learnings bullet\n")

        regions = {f.region for f in report.region}
        assert regions == {"managed_block", "project_region"}

    def test_contradiction_is_reported_as_distinct_class(self):
        skill_with_contradiction = (
            "---\nname: demo\ndescription: A demo skill.\n---\n\n"
            f"{MARKER_BEGIN_PREFIX} demo v1.0.0 -->\n"
            "policy header\n\n"
            "- Verifiers are tiered by proof shape — deterministic proofs run "
            "haiku, comparative proofs run sonnet, semantic proofs run opus.\n"
            f"{MARKER_END}\n\n"
            "- Verifiers inherit the runner's tier at high effort, regardless "
            "of proof shape.\n"
        )
        report = audit(skill_with_contradiction, "- unrelated learnings bullet\n")

        assert len(report.contradictions) == 1
        assert report.contradictions[0].kind == "contradiction"

    def test_audit_performs_no_writes(self, tmp_path):
        skill_path = tmp_path / "SKILL.md"
        learnings_path = tmp_path / "learnings.md"
        skill_path.write_text(SKILL_MD, encoding="utf-8")
        learnings_path.write_text("- a bullet\n", encoding="utf-8")
        before_skill = skill_path.read_bytes()
        before_learnings = learnings_path.read_bytes()

        audit(skill_path.read_text(encoding="utf-8"), learnings_path.read_text(encoding="utf-8"))

        assert skill_path.read_bytes() == before_skill
        assert learnings_path.read_bytes() == before_learnings

    def test_deterministic_and_reproducible_from_bytes(self):
        learnings = "- Verifiers are tiered by proof shape, deterministic runs haiku.\n"
        assert audit(SKILL_MD, learnings) == audit(SKILL_MD, learnings)


# --- TAP-6865: single-home verify -------------------------------------------


class TestVerifySingleHome:
    def test_rule_present_in_both_files_fails(self):
        rule = "Retry the flaky network call up to three times."
        skill_md = f"# Skill\n\n- {rule}\n"
        learnings_md = f"- {rule}\n"

        results = verify_single_home([rule], skill_md, learnings_md)

        assert results[0].status == "present_in_both"
        assert results[0].skill_anchors and results[0].learnings_anchors

    def test_rule_present_in_neither_file_is_a_distinct_failure(self):
        rule = "Retry the flaky network call up to three times."
        results = verify_single_home([rule], "# Skill\n\n- unrelated\n", "- also unrelated\n")

        assert results[0].status == "present_in_neither"
        assert results[0].skill_anchors == ()
        assert results[0].learnings_anchors == ()

    def test_rule_present_only_in_skill_is_ok(self):
        rule = "Retry the flaky network call up to three times."
        skill_md = f"# Skill\n\n- {rule}\n"
        learnings_md = "- Fleet manifest refs live in .tapps-mcp.yaml.\n"

        results = verify_single_home([rule], skill_md, learnings_md)

        assert results[0].status == "ok"

    def test_pointer_line_in_learnings_is_exempt_not_a_second_copy(self):
        rule = "Retry the flaky network call up to three times."
        skill_md = f"# Skill\n\n- {rule}\n"
        learnings_md = "- See SKILL.md §Retries for the current rule.\n"

        results = verify_single_home([rule], skill_md, learnings_md)

        assert results[0].status == "ok"
        assert results[0].learnings_anchors == ()

    def test_both_anchors_reported_when_present_in_both(self):
        rule = "Retry the flaky network call up to three times."
        skill_md = f"# Skill\n\nline one\n\n- {rule}\n"
        learnings_md = f"- {rule}\n"

        result = verify_single_home([rule], skill_md, learnings_md)[0]

        assert result.skill_anchors[0] > 0
        assert result.learnings_anchors[0] > 0


# --- TAP-6866: safe trim ------------------------------------------------------


class TestApplyTrim:
    def test_delete_by_hash_removes_exactly_that_bullet(self):
        learnings = "- keep this one\n- delete this one\n- keep this too\n"
        target_hash = bullet_content_hash("- delete this one\n")

        outcome = apply_trim(
            learnings, [TrimInstruction(content_hash=target_hash, action="delete")]
        )

        assert outcome.applied is True
        assert "delete this one" not in outcome.updated_text
        assert "keep this one" in outcome.updated_text
        assert "keep this too" in outcome.updated_text
        assert outcome.before_bullet_count == 3
        assert outcome.after_bullet_count == 2

    def test_keep_verbatim_bullet_is_byte_identical_after_apply(self):
        learnings = "- keep this one verbatim\n- delete this one\n"
        keep_hash = bullet_content_hash("- keep this one verbatim\n")
        delete_hash = bullet_content_hash("- delete this one\n")

        outcome = apply_trim(
            learnings,
            [
                TrimInstruction(content_hash=keep_hash, action="keep_verbatim"),
                TrimInstruction(content_hash=delete_hash, action="delete"),
            ],
        )

        assert outcome.applied is True
        assert "- keep this one verbatim\n" in outcome.updated_text

    def test_unresolvable_hash_refuses_whole_apply(self):
        learnings = "- only bullet\n"

        outcome = apply_trim(learnings, [TrimInstruction(content_hash="0" * 64, action="delete")])

        assert outcome.applied is False
        assert outcome.updated_text is None
        assert "did not resolve" in outcome.reason

    def test_ambiguous_hash_refuses_whole_apply(self):
        learnings = "- duplicate text\n- duplicate text\n"
        dup_hash = bullet_content_hash("- duplicate text\n")

        outcome = apply_trim(learnings, [TrimInstruction(content_hash=dup_hash, action="delete")])

        assert outcome.applied is False
        assert "more than one" in outcome.reason

    def test_partial_apply_is_impossible_nothing_written_on_refusal(self):
        learnings = "- fine bullet\n- duplicate\n- duplicate\n"
        fine_hash = bullet_content_hash("- fine bullet\n")
        dup_hash = bullet_content_hash("- duplicate\n")

        outcome = apply_trim(
            learnings,
            [
                TrimInstruction(content_hash=fine_hash, action="delete"),
                TrimInstruction(content_hash=dup_hash, action="delete"),
            ],
        )

        assert outcome.applied is False
        assert outcome.before_bytes == outcome.after_bytes
        assert outcome.before_bullet_count == outcome.after_bullet_count

    def test_response_reports_before_and_after_counts(self):
        learnings = "- a\n- b\n- c\n"
        b_hash = bullet_content_hash("- b\n")

        outcome = apply_trim(learnings, [TrimInstruction(content_hash=b_hash, action="delete")])

        assert outcome.before_bullet_count == 3
        assert outcome.after_bullet_count == 2
        assert outcome.before_bytes == len(learnings.encode("utf-8"))
        assert outcome.after_bytes == len(outcome.updated_text.encode("utf-8"))

    def test_line_numbers_never_appear_in_the_apply_path(self):
        """The plan addresses bullets purely by content hash (TAP-6866)."""
        learnings = "- a\n- b\n- c\n"
        b_hash = bullet_content_hash("- b\n")
        instruction = TrimInstruction(content_hash=b_hash, action="delete")

        assert not hasattr(instruction, "line")
        assert not hasattr(instruction, "line_number")

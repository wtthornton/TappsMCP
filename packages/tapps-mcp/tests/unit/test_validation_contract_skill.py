"""Tests for the smart-merged ``tapps-validation-contract`` platform skill (TAP-5541)."""

from __future__ import annotations

from tapps_mcp.distribution.doctor import check_validation_contract_skill_current
from tapps_mcp.pipeline.platform_skill_validation_contract import (
    VALIDATION_CONTRACT_COMPANION_FILES,
    VALIDATION_CONTRACT_SKILL_BODY,
)
from tapps_mcp.pipeline.platform_skills import (
    SMART_MERGE_SKILL_NAMES,
    generate_skills,
)
from tapps_mcp.pipeline.skill_managed_block import (
    MARKER_BEGIN_PREFIX,
    MARKER_END,
    install_or_refresh_skill,
)

SKILL = "tapps-validation-contract"


def _skill_dir(root, host="claude"):
    return root / f".{host}" / "skills" / SKILL


class TestModuleShape:
    def test_body_requires_assertions_before_implementation(self):
        lower = VALIDATION_CONTRACT_SKILL_BODY.lower()
        assert "before" in lower and "implementation" in lower
        assert "post-hoc" in lower
        assert "val-" in lower

    def test_frontmatter_disables_model_invocation(self):
        assert "disable-model-invocation: true" in VALIDATION_CONTRACT_SKILL_BODY
        assert f"name: {SKILL}" in VALIDATION_CONTRACT_SKILL_BODY

    def test_companions_include_required_refs(self):
        assert "assets/contract-template.md" in VALIDATION_CONTRACT_COMPANION_FILES
        assert "references/assertion-schema.md" in VALIDATION_CONTRACT_COMPANION_FILES
        assert "references/when-to-use.md" in VALIDATION_CONTRACT_COMPANION_FILES

    def test_registered_as_smart_merge(self):
        assert SKILL in SMART_MERGE_SKILL_NAMES


class TestScaffold:
    def test_creates_skill_and_companions(self, tmp_path):
        generate_skills(tmp_path, "claude")
        d = _skill_dir(tmp_path)
        assert (d / "SKILL.md").exists()
        assert (d / "assets" / "contract-template.md").exists()
        assert (d / "references" / "assertion-schema.md").exists()
        assert (d / "references" / "when-to-use.md").exists()

    def test_skill_md_has_managed_marker(self, tmp_path):
        generate_skills(tmp_path, "claude")
        content = (_skill_dir(tmp_path) / "SKILL.md").read_text()
        assert f"{MARKER_BEGIN_PREFIX} {SKILL} v" in content
        assert MARKER_END in content

    def test_body_carries_pipeline_mark_and_ids(self, tmp_path):
        generate_skills(tmp_path, "claude")
        content = (_skill_dir(tmp_path) / "SKILL.md").read_text().lower()
        assert "pipeline-mark contract-verified" in content
        assert "val-" in content
        assert "creator" in content or "verifier" in content

    def test_contract_template_has_coverage_table(self, tmp_path):
        generate_skills(tmp_path, "claude")
        tpl = (_skill_dir(tmp_path) / "assets" / "contract-template.md").read_text().lower()
        assert "## assertions" in tpl
        assert "## coverage" in tpl or "fulfills" in tpl

    def test_cursor_host_also_gets_skill(self, tmp_path):
        generate_skills(tmp_path, "cursor")
        assert (_skill_dir(tmp_path, "cursor") / "SKILL.md").exists()

    def test_full_tier_deploys_core_tier_skips(self, tmp_path):
        full = generate_skills(tmp_path / "full", "claude", skill_tier="full")
        core = generate_skills(tmp_path / "core", "claude", skill_tier="core")
        assert SKILL in full["created"] or (_skill_dir(tmp_path / "full") / "SKILL.md").exists()
        assert SKILL in core["skipped_tier"]
        assert not (_skill_dir(tmp_path / "core") / "SKILL.md").exists()


class TestSmartMerge:
    def test_upgrade_preserves_project_region(self, tmp_path):
        generate_skills(tmp_path, "claude")
        skill_md = _skill_dir(tmp_path) / "SKILL.md"
        marker = "## Project: contract conventions\n\nUse project prefix VAL-NLT-."
        skill_md.write_text(skill_md.read_text() + "\n\n" + marker, encoding="utf-8")
        generate_skills(tmp_path, "claude", overwrite=True)
        after = skill_md.read_text()
        assert marker in after
        assert MARKER_END in after

    def test_companion_docs_refresh_on_upgrade(self, tmp_path):
        generate_skills(tmp_path, "claude")
        ref = _skill_dir(tmp_path) / "references" / "assertion-schema.md"
        ref.write_text("stale\n", encoding="utf-8")
        generate_skills(tmp_path, "claude", overwrite=True)
        assert "val-" in ref.read_text().lower()


class TestFinishAndReviewSurfaces:
    def test_finish_task_mentions_creator_verifier(self, tmp_path):
        generate_skills(tmp_path, "claude")
        body = (tmp_path / ".claude" / "skills" / "tapps-finish-task" / "SKILL.md").read_text()
        assert "creator-verifier" in body.lower() or "creator ≠ verifier" in body.lower()
        assert "pipeline-mark creator-verifier" in body.lower()

    def test_review_pipeline_mentions_creator_neq_verifier(self, tmp_path):
        generate_skills(tmp_path, "claude")
        body = (tmp_path / ".claude" / "skills" / "tapps-review-pipeline" / "SKILL.md").read_text()
        assert "creator" in body.lower() and "verifier" in body.lower()
        assert "pipeline-mark creator-verifier" in body.lower()


class TestDoctorCheck:
    def test_fails_full_tier_when_missing(self, tmp_path):
        (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
        (tmp_path / ".tapps-mcp.yaml").write_text("skill_tier: full\n", encoding="utf-8")
        result = check_validation_contract_skill_current(tmp_path)
        assert not result.ok
        assert "missing" in result.message

    def test_ok_core_tier_when_missing(self, tmp_path):
        (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
        (tmp_path / ".tapps-mcp.yaml").write_text("skill_tier: core\n", encoding="utf-8")
        result = check_validation_contract_skill_current(tmp_path)
        assert result.ok

    def test_ok_when_fully_deployed(self, tmp_path):
        (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
        generate_skills(tmp_path, "claude")
        result = check_validation_contract_skill_current(tmp_path)
        assert result.ok
        assert "current" in result.message

    def test_flags_missing_companion(self, tmp_path):
        (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
        generate_skills(tmp_path, "claude")
        (_skill_dir(tmp_path) / "references" / "assertion-schema.md").unlink()
        result = check_validation_contract_skill_current(tmp_path)
        assert not result.ok

    def test_flags_stale_unmarked_skill(self, tmp_path):
        (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
        d = _skill_dir(tmp_path)
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("# legacy hand-authored, no marker\n", encoding="utf-8")
        result = check_validation_contract_skill_current(tmp_path)
        assert not result.ok
        assert "stale" in result.message


class TestManagedBlockUnit:
    def test_created_then_unchanged(self, tmp_path):
        path = tmp_path / "SKILL.md"
        assert install_or_refresh_skill(path, "body v1", SKILL) == "created"
        assert install_or_refresh_skill(path, "body v1", SKILL) == "unchanged"

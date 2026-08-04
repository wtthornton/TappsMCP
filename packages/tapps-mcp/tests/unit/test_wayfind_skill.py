"""Tests for the multi-file, smart-merged ``tapps-wayfind`` platform skill.

Mirrors ``test_orchestration_prompt_skill`` deploy shape:
- ``generate_skills`` scaffolds SKILL.md + companions
- smart-merge preserves project customizations
- companions refresh on upgrade
- frontmatter gates auto-invocation (``disable-model-invocation``)
- full tier deploys; core tier skips
"""

from __future__ import annotations

from tapps_mcp.pipeline.platform_skill_wayfind import (
    WAYFIND_COMPANION_FILES,
    WAYFIND_SKILL_BODY,
)
from tapps_mcp.pipeline.platform_skills import (
    SMART_MERGE_SKILL_NAMES,
    generate_skills,
)
from tapps_mcp.pipeline.skill_managed_block import (
    MARKER_BEGIN_PREFIX,
    MARKER_END,
    install_or_refresh_skill,
    wrap_with_markers,
)

SKILL = "tapps-wayfind"


def _skill_dir(root, host="claude"):
    return root / f".{host}" / "skills" / SKILL


class TestModuleShape:
    def test_body_has_chart_and_work_modes(self):
        lower = WAYFIND_SKILL_BODY.lower()
        assert "### chart the map" in lower
        assert "### work through the map" in lower

    def test_frontmatter_disables_model_invocation(self):
        assert "disable-model-invocation: true" in WAYFIND_SKILL_BODY
        assert "name: tapps-wayfind" in WAYFIND_SKILL_BODY

    def test_companions_include_required_refs(self):
        assert "assets/map-template.md" in WAYFIND_COMPANION_FILES
        assert "references/ticket-types.md" in WAYFIND_COMPANION_FILES
        assert "references/linear-ops.md" in WAYFIND_COMPANION_FILES

    def test_registered_as_smart_merge(self):
        assert SKILL in SMART_MERGE_SKILL_NAMES


class TestScaffold:
    def test_creates_skill_and_companions(self, tmp_path):
        generate_skills(tmp_path, "claude")
        d = _skill_dir(tmp_path)
        assert (d / "SKILL.md").exists()
        assert (d / "assets" / "map-template.md").exists()
        assert (d / "references" / "ticket-types.md").exists()
        assert (d / "references" / "linear-ops.md").exists()

    def test_skill_md_has_managed_marker(self, tmp_path):
        generate_skills(tmp_path, "claude")
        content = (_skill_dir(tmp_path) / "SKILL.md").read_text()
        assert f"{MARKER_BEGIN_PREFIX} {SKILL} v" in content
        assert MARKER_END in content
        assert "name: tapps-wayfind" in content
        assert "disable-model-invocation: true" in content

    def test_body_carries_fog_and_handoff_to_orchestration(self, tmp_path):
        generate_skills(tmp_path, "claude")
        content = (_skill_dir(tmp_path) / "SKILL.md").read_text().lower()
        assert "fog" in content
        assert "orchestration-prompt" in content
        assert "linear is sot" in content

    def test_map_template_has_destination_sections(self, tmp_path):
        generate_skills(tmp_path, "claude")
        tpl = (_skill_dir(tmp_path) / "assets" / "map-template.md").read_text().lower()
        assert "## destination" in tpl
        assert "## decisions so far" in tpl
        assert "## not yet specified" in tpl
        assert "## question" in tpl

    def test_ticket_types_and_linear_ops_companions(self, tmp_path):
        generate_skills(tmp_path, "claude")
        d = _skill_dir(tmp_path)
        types = (d / "references" / "ticket-types.md").read_text().lower()
        ops = (d / "references" / "linear-ops.md").read_text().lower()
        assert "research" in types
        assert "grilling" in types
        assert "linear-issue" in ops
        assert "linear-read" in ops

    def test_cursor_host_also_gets_skill(self, tmp_path):
        generate_skills(tmp_path, "cursor")
        assert (_skill_dir(tmp_path, "cursor") / "SKILL.md").exists()
        assert (_skill_dir(tmp_path, "cursor") / "references" / "linear-ops.md").exists()

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
        marker = "## Project: map conventions\n\nUse project label `wayfind`."
        skill_md.write_text(skill_md.read_text() + "\n\n" + marker, encoding="utf-8")

        generate_skills(tmp_path, "claude", overwrite=True)
        after = skill_md.read_text()
        assert marker in after
        assert MARKER_END in after

    def test_companion_docs_refresh_on_upgrade(self, tmp_path):
        generate_skills(tmp_path, "claude")
        ref = _skill_dir(tmp_path) / "references" / "ticket-types.md"
        ref.write_text("stale\n", encoding="utf-8")
        generate_skills(tmp_path, "claude", overwrite=True)
        assert "ticket types" in ref.read_text().lower()


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
        path.write_text("# hand-authored\n\nproject map notes\n", encoding="utf-8")
        assert install_or_refresh_skill(path, "platform body", SKILL) == "migrated"
        after = path.read_text()
        assert "platform body" in after
        assert "project map notes" in after
        assert after.index(MARKER_BEGIN_PREFIX) < after.index("project map notes")

    def test_wrap_roundtrip_stamps_version(self, tmp_path):
        wrapped = wrap_with_markers("x", SKILL, version="9.9.9")
        assert f"{MARKER_BEGIN_PREFIX} {SKILL} v9.9.9 -->" in wrapped
        assert wrapped.endswith(MARKER_END)

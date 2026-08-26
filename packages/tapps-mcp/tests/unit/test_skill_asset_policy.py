"""TAP-6497: scaffolded skill files declare and honor one upgrade policy each.

Before this, a skill directory held three undocumented policies: ``SKILL.md``
preserved everything outside its managed block, ``assets/prompt-template.md``
was overwritten wholesale, and ``learnings.md`` was never touched. Only the
first was discoverable from inside a file, so an operator who customized an
asset had no way to know it would vanish.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.distribution.doctor_skills import check_skill_asset_drift
from tapps_mcp.pipeline.platform_skills import (
    SKILL_COMPANION_FILES,
    SKILL_CREATE_ONLY_FILES,
    SMART_MERGE_SKILL_NAMES,
    generate_skills,
)
from tapps_mcp.pipeline.skill_asset_policy import (
    ASSET_MARKER_BEGIN_PREFIX,
    ASSET_MARKER_END,
    ASSET_PROJECT_REGION_HEADING,
    POLICY_NOTES,
    has_asset_customization,
    install_or_refresh_asset,
    is_delimitable,
    plan_overwrite_report,
    policy_for,
    policy_header,
    strip_asset_scaffolding,
    wrap_asset,
)

SKILL = "orchestration-prompt"
ASSET = "assets/prompt-template.md"


def _skill_dir(root: Path, skill: str = SKILL) -> Path:
    return root / ".claude" / "skills" / skill


class TestPolicyVocabulary:
    def test_markdown_gets_a_managed_block(self) -> None:
        assert is_delimitable(ASSET)
        assert policy_for(ASSET) == "managed_block"

    def test_non_delimitable_format_falls_back_to_overwrite(self) -> None:
        assert not is_delimitable("assets/config.json")
        assert policy_for("assets/config.json") == "overwrite"

    def test_create_only_wins_over_format(self) -> None:
        assert policy_for("learnings.md", create_only=True) == "create_only"

    def test_every_policy_has_an_in_file_note(self) -> None:
        """Acceptance item 4: the policies are enumerated in exactly one place."""
        for policy, note in POLICY_NOTES.items():
            assert note.startswith("upgrade-policy: ")
            assert policy_header(policy).startswith("<!-- upgrade-policy: ")


class TestAssetManagedBlock:
    def test_created_file_carries_header_and_markers(self, tmp_path: Path) -> None:
        target = tmp_path / "a.md"
        assert install_or_refresh_asset(target, "canonical body", SKILL, ASSET) == "created"
        text = target.read_text(encoding="utf-8")
        assert policy_header("managed_block") in text
        assert f"{ASSET_MARKER_BEGIN_PREFIX} {SKILL}/{ASSET} v" in text
        assert ASSET_MARKER_END in text
        assert "canonical body" in text

    def test_project_text_outside_the_block_survives_refresh(self, tmp_path: Path) -> None:
        """The core acceptance: customize without pinning, keep the fix."""
        target = tmp_path / "a.md"
        install_or_refresh_asset(target, "v1 body", SKILL, ASSET)
        target.write_text(
            target.read_text(encoding="utf-8") + "\n## My project section\nkeep me\n",
            encoding="utf-8",
        )

        assert install_or_refresh_asset(target, "v2 body", SKILL, ASSET) == "refreshed"
        text = target.read_text(encoding="utf-8")
        assert "## My project section" in text
        assert "keep me" in text
        assert "v2 body" in text
        assert "v1 body" not in text

    def test_unchanged_when_body_and_version_match(self, tmp_path: Path) -> None:
        target = tmp_path / "a.md"
        install_or_refresh_asset(target, "body", SKILL, ASSET)
        assert install_or_refresh_asset(target, "body", SKILL, ASSET) == "unchanged"

    def test_pristine_pre_marker_copy_adopts_markers_without_duplicating(
        self, tmp_path: Path
    ) -> None:
        target = tmp_path / "a.md"
        target.write_text("body\n", encoding="utf-8")
        assert install_or_refresh_asset(target, "body", SKILL, ASSET) == "refreshed"
        text = target.read_text(encoding="utf-8")
        assert text.count("body") == 1
        assert ASSET_PROJECT_REGION_HEADING not in text

    def test_edited_pre_marker_copy_is_migrated_not_discarded(self, tmp_path: Path) -> None:
        target = tmp_path / "a.md"
        target.write_text("body\nhand-edited line\n", encoding="utf-8")
        assert install_or_refresh_asset(target, "body", SKILL, ASSET) == "migrated"
        text = target.read_text(encoding="utf-8")
        assert ASSET_PROJECT_REGION_HEADING in text
        assert "hand-edited line" in text

    def test_dry_run_writes_nothing(self, tmp_path: Path) -> None:
        target = tmp_path / "a.md"
        assert install_or_refresh_asset(target, "body", SKILL, ASSET, dry_run=True) == "created"
        assert not target.exists()

    def test_strip_scaffolding_recovers_the_body(self, tmp_path: Path) -> None:
        wrapped = wrap_asset("canonical body", SKILL, ASSET)
        assert strip_asset_scaffolding(wrapped) == "canonical body"

    def test_customization_detection(self) -> None:
        clean = wrap_asset("body", SKILL, ASSET)
        assert not has_asset_customization(clean)
        assert has_asset_customization(clean + "\nmine\n")


class TestOverwriteReport:
    def test_no_report_for_absent_or_canonical_file(self, tmp_path: Path) -> None:
        target = tmp_path / "a.json"
        assert plan_overwrite_report(target, "{}") is None
        target.write_text(f"{policy_header('overwrite')}\n{{}}", encoding="utf-8")
        assert plan_overwrite_report(target, "{}") is None

    def test_customized_non_delimitable_file_is_named_before_overwrite(
        self, tmp_path: Path
    ) -> None:
        """Acceptance item 2: no silent wholesale overwrite of edited content."""
        target = tmp_path / "a.json"
        target.write_text('{"mine": true}', encoding="utf-8")
        report = plan_overwrite_report(target, "{}")
        assert report is not None
        assert str(target) in report
        assert "overwrites it wholesale" in report


class TestGeneratorIntegration:
    def test_companions_are_scaffolded_with_managed_blocks(self, tmp_path: Path) -> None:
        result = generate_skills(tmp_path, "claude")
        for rel in SKILL_COMPANION_FILES[SKILL]:
            text = (_skill_dir(tmp_path) / rel).read_text(encoding="utf-8")
            assert ASSET_MARKER_BEGIN_PREFIX in text, rel
            assert policy_header("managed_block") in text, rel
        assert result["assets"][SKILL][ASSET] == "created"

    def test_create_only_file_states_its_policy_and_is_never_rewritten(
        self, tmp_path: Path
    ) -> None:
        generate_skills(tmp_path, "claude")
        rel = next(iter(SKILL_CREATE_ONLY_FILES[SKILL]))
        target = _skill_dir(tmp_path) / rel
        assert policy_header("create_only") in target.read_text(encoding="utf-8")

        target.write_text("only mine\n", encoding="utf-8")
        result = generate_skills(tmp_path, "claude", overwrite=True)
        assert target.read_text(encoding="utf-8") == "only mine\n"
        assert result["assets"][SKILL][rel] == "preserved (create-only)"

    def test_asset_customization_survives_a_second_generate(self, tmp_path: Path) -> None:
        """End-to-end of the reported defect, at generator level."""
        generate_skills(tmp_path, "claude")
        target = _skill_dir(tmp_path) / ASSET
        target.write_text(
            target.read_text(encoding="utf-8") + "\n## Project addendum\nsurvive\n",
            encoding="utf-8",
        )

        generate_skills(tmp_path, "claude", overwrite=True)
        after = target.read_text(encoding="utf-8")
        assert "## Project addendum" in after
        assert "survive" in after

    def test_every_scaffolded_skill_file_states_a_policy(self, tmp_path: Path) -> None:
        """Acceptance item 3: no file leaves the operator guessing."""
        generate_skills(tmp_path, "claude")
        headers = {policy_header(p) for p in POLICY_NOTES}
        for path in sorted((tmp_path / ".claude" / "skills").rglob("*.md")):
            text = path.read_text(encoding="utf-8")
            assert any(h in text for h in headers), path

    def test_smart_merge_skills_declare_the_managed_block_policy(self, tmp_path: Path) -> None:
        generate_skills(tmp_path, "claude")
        for skill in SMART_MERGE_SKILL_NAMES:
            text = (_skill_dir(tmp_path, skill) / "SKILL.md").read_text(encoding="utf-8")
            assert text.startswith("---"), skill
            assert policy_header("managed_block") in text, skill


class TestDoctorDriftCheck:
    def test_clean_scaffold_reports_one_shared_policy(self, tmp_path: Path) -> None:
        generate_skills(tmp_path, "claude")
        check = check_skill_asset_drift(tmp_path)
        assert check.ok, check.message

    def test_customized_skill_md_with_unmarked_asset_is_flagged(self, tmp_path: Path) -> None:
        """Acceptance item 5: the two halves of a skill dir must agree."""
        generate_skills(tmp_path, "claude")
        skill_dir = _skill_dir(tmp_path)
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            skill_md.read_text(encoding="utf-8") + "\n## Project notes\nmine\n",
            encoding="utf-8",
        )
        # Roll the asset back to its pre-TAP-6497 shape: no marker, no header.
        (skill_dir / ASSET).write_text("legacy body\n", encoding="utf-8")

        check = check_skill_asset_drift(tmp_path)
        assert not check.ok
        assert check.severity == "warn"
        assert ASSET in check.message

    def test_uncustomized_skill_md_is_not_flagged(self, tmp_path: Path) -> None:
        generate_skills(tmp_path, "claude")
        (_skill_dir(tmp_path) / ASSET).write_text("legacy body\n", encoding="utf-8")
        assert check_skill_asset_drift(tmp_path).ok

    def test_no_skills_installed_is_quiet(self, tmp_path: Path) -> None:
        check = check_skill_asset_drift(tmp_path)
        assert check.ok
        assert "no managed skills" in check.message

    def test_check_is_registered_in_the_doctor_run(self) -> None:
        from tapps_mcp.distribution.doctor_runner import _collect_checks

        assert "Skill asset drift" in _collect_checks.__code__.co_consts


class TestUpgradeSurfacesOverwrites:
    def test_overwrite_warnings_reach_the_top_level_result(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A non-delimitable companion's overwrite is named in upgrade output."""
        from tapps_mcp.pipeline import platform_skills

        monkeypatch.setitem(
            platform_skills.SKILL_COMPANION_FILES,
            SKILL,
            {**SKILL_COMPANION_FILES[SKILL], "assets/settings.json": "{}\n"},
        )
        generate_skills(tmp_path, "claude")
        (_skill_dir(tmp_path) / "assets" / "settings.json").write_text(
            '{"mine": true}', encoding="utf-8"
        )

        result = generate_skills(tmp_path, "claude", overwrite=True)
        warnings = result["asset_overwrite_warnings"]
        assert any("settings.json" in w for w in warnings)

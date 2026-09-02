"""TAP-6497: scaffolded skill files declare and honor one upgrade policy each.

Before this, a skill directory held three undocumented policies: ``SKILL.md``
preserved everything outside its managed block, ``assets/prompt-template.md``
was overwritten wholesale, and ``learnings.md`` was never touched. Only the
first was discoverable from inside a file, so an operator who customized an
asset had no way to know it would vanish.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from tapps_mcp import __version__
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
    asset_block,
    has_asset_customization,
    install_or_refresh_asset,
    is_delimitable,
    plan_overwrite_report,
    policy_for,
    policy_header,
    strip_asset_scaffolding,
    wrap_asset,
    write_project_script,
)

SKILL = "orchestration-prompt"
ASSET = "assets/prompt-template.md"


def _skill_dir(root: Path, skill: str = SKILL) -> Path:
    return root / ".claude" / "skills" / skill


def _check_sh_syntax(path: Path) -> None:
    bash = shutil.which("bash")
    assert bash is not None, "bash not found on PATH"
    result = subprocess.run([bash, "-n", str(path)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def _check_py_syntax(path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(path)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


def _check_js_syntax(path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not available on this host -- .js syntax not checked")
    result = subprocess.run([node, "--check", str(path)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


#: Dispatch table for the migrated x non-Markdown regression test below --
#: one syntax checker per suffix, each with a single assert, so the test
#: itself carries no per-suffix branching.
_MIGRATED_SYNTAX_CHECKS: dict[str, Callable[[Path], None]] = {
    "sh": _check_sh_syntax,
    "py": _check_py_syntax,
    "js": _check_js_syntax,
}


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


class TestExistingSuffixesUnchanged:
    """Evidence item 5 (TAP-6884): the three original suffixes must keep

    emitting the exact html-comment marker shape captured from origin/master
    at a739ca14, byte for byte — a regression here silently rewrites every
    consuming project's skill assets.
    """

    @pytest.mark.parametrize("rel_path", [ASSET, "SKILL.md", "notes.markdown", "page.html"])
    def test_asset_block_is_still_html_comments(self, rel_path: str) -> None:
        assert asset_block("canonical body", SKILL, rel_path) == (
            f"<!-- BEGIN: tapps-skill-asset {SKILL}/{rel_path} v{__version__} -->\n"
            "canonical body\n"
            "<!-- END: tapps-skill-asset -->"
        )

    @pytest.mark.parametrize("rel_path", [ASSET, "SKILL.md", "notes.markdown", "page.html", ""])
    def test_policy_header_is_still_html_comments(self, rel_path: str) -> None:
        for policy, note in POLICY_NOTES.items():
            assert policy_header(policy, rel_path) == f"<!-- {note} -->"

    def test_wrap_asset_matches_captured_baseline(self) -> None:
        # Captured 2026-09-01 from origin/master @ a739ca14 by calling
        # wrap_asset("canonical body", SKILL, ASSET) against the pre-lane module.
        expected = (
            f"<!-- {POLICY_NOTES['managed_block']} -->\n"
            f"<!-- BEGIN: tapps-skill-asset {SKILL}/{ASSET} v{__version__} -->\n"
            "canonical body\n"
            "<!-- END: tapps-skill-asset -->\n"
        )
        assert wrap_asset("canonical body", SKILL, ASSET) == expected
        assert ASSET_MARKER_BEGIN_PREFIX == "<!-- BEGIN: tapps-skill-asset"
        assert ASSET_MARKER_END == "<!-- END: tapps-skill-asset -->"


class TestSyntaxAwareMarkers:
    """Evidence items 1-4 (TAP-6884): .sh/.py/.js get a comment syntax that

    parses in their own language, and the managed-block mechanism (outside
    survives, inside is replaced, round-trip strips exactly) still holds.
    """

    @pytest.mark.parametrize(
        "rel_path,open_tok,close_tok",
        [
            ("scripts/canary.sh", "#", ""),
            ("scripts/canary.py", "#", ""),
            ("workflows/canary.js", "//", ""),
        ],
    )
    def test_new_suffixes_get_a_line_comment_marker(
        self, rel_path: str, open_tok: str, close_tok: str
    ) -> None:
        assert is_delimitable(rel_path)
        assert policy_for(rel_path) == "managed_block"
        block = asset_block("echo hi", SKILL, rel_path)
        assert (
            block.splitlines()[0]
            == f"{open_tok} BEGIN: tapps-skill-asset {SKILL}/{rel_path} v{__version__}"
        )
        assert block.splitlines()[-1] == f"{open_tok} END: tapps-skill-asset"
        assert "<!--" not in block
        assert "-->" not in block
        header = policy_header("managed_block", rel_path)
        assert header.startswith(f"{open_tok} upgrade-policy: managed-block")
        assert not header.endswith("-->")

    def test_naive_suffix_widening_without_syntax_change_would_break_bash_parsing(
        self, tmp_path: Path
    ) -> None:
        """Regression guard for the exact defect this lane exists to fix.

        Simulates "suffix added, marker still html-comments" — the naive
        change called out in the goal doc — by wrapping a .sh body in the
        html marker shape directly, then asserting that shape does NOT
        parse as bash. The real writer (below) must not produce this.
        """
        naive_sh = (
            "<!-- upgrade-policy: managed-block ... -->\n"
            f"<!-- BEGIN: tapps-skill-asset {SKILL}/scripts/canary.sh v0 -->\n"
            "echo hi\n"
            "<!-- END: tapps-skill-asset -->\n"
        )
        target = tmp_path / "naive-canary.sh"
        target.write_text(naive_sh, encoding="utf-8")
        result = subprocess.run(
            ["bash", "-n", str(target)], capture_output=True, text=True, timeout=10
        )
        assert result.returncode != 0, "planted defect should fail bash -n but did not"

    def test_scaffolded_sh_lands_executable_and_parses_as_bash(self, tmp_path: Path) -> None:
        action = write_project_script(tmp_path, "scripts/canary.sh", "echo 'tapps canary'\n", SKILL)
        target = tmp_path / "scripts" / "canary.sh"
        assert action == "created"
        assert target.stat().st_mode & 0o111
        result = subprocess.run(
            ["bash", "-n", str(target)], capture_output=True, text=True, timeout=10
        )
        assert result.returncode == 0, result.stderr

    def test_scaffolded_py_lands_executable_and_compiles(self, tmp_path: Path) -> None:
        action = write_project_script(
            tmp_path, "scripts/canary.py", 'print("tapps canary")\n', SKILL
        )
        target = tmp_path / "scripts" / "canary.py"
        assert action == "created"
        assert target.stat().st_mode & 0o111
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(target)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr

    def test_edit_outside_markers_survives_refresh_for_sh(self, tmp_path: Path) -> None:
        """Evidence item 2, for the new hash-comment class — byte-for-byte."""
        write_project_script(tmp_path, "scripts/canary.sh", "echo v1\n", SKILL)
        target = tmp_path / "scripts" / "canary.sh"
        addendum = "\n# project addendum: keep me\n"
        target.write_text(target.read_text(encoding="utf-8") + addendum, encoding="utf-8")

        action = write_project_script(tmp_path, "scripts/canary.sh", "echo v2\n", SKILL)
        text = target.read_text(encoding="utf-8")
        assert action == "refreshed"
        expected = wrap_asset("echo v2", SKILL, "scripts/canary.sh") + addendum
        assert text == expected, f"outside-marker edit not preserved byte-for-byte:\n{text!r}"

    def test_edit_inside_markers_is_replaced_on_refresh_for_py(self, tmp_path: Path) -> None:
        """Evidence item 3, for the new hash-comment class — byte-for-byte."""
        write_project_script(tmp_path, "scripts/canary.py", 'print("v1")\n', SKILL)
        target = tmp_path / "scripts" / "canary.py"
        hacked = target.read_text(encoding="utf-8").replace('print("v1")', 'print("HACKED")')
        target.write_text(hacked, encoding="utf-8")

        write_project_script(tmp_path, "scripts/canary.py", 'print("v2")\n', SKILL)
        text = target.read_text(encoding="utf-8")
        expected = wrap_asset('print("v2")', SKILL, "scripts/canary.py")
        assert text == expected, f"inside-marker edit not replaced byte-for-byte:\n{text!r}"

    def test_find_asset_block_round_trips_a_hash_commented_file(self) -> None:
        """Evidence item 4: strip_asset_scaffolding recovers the exact body."""
        wrapped = wrap_asset("echo canary", SKILL, "scripts/canary.sh")
        assert strip_asset_scaffolding(wrapped) == "echo canary"

    def test_find_asset_block_round_trips_a_slash_commented_file(self) -> None:
        wrapped = wrap_asset("console.log('canary')", SKILL, "workflows/canary.js")
        assert strip_asset_scaffolding(wrapped) == "console.log('canary')"

    def test_has_asset_customization_for_hash_commented_file(self) -> None:
        clean = wrap_asset("echo hi", SKILL, "scripts/canary.sh")
        assert not has_asset_customization(clean)
        assert has_asset_customization(clean + "\n# mine\n")

    @pytest.mark.parametrize(
        "rel_path,body,hand_edit_line,checker",
        [
            ("scripts/canary.sh", "echo v1\n", "local_leftover=1\n", "sh"),
            ("scripts/canary.py", 'print("v1")\n', "leftover = 1\n", "py"),
            ("workflows/canary.js", "console.log('v1')\n", "const leftover = 1;\n", "js"),
        ],
    )
    def test_migrated_non_markdown_asset_is_syntax_valid_and_preserves_content(
        self,
        tmp_path: Path,
        rel_path: str,
        body: str,
        hand_edit_line: str,
        checker: str,
    ) -> None:
        """TAP-6981: the ``migrated`` branch x non-Markdown hole.

        ``TestAssetManagedBlock.test_edited_pre_marker_copy_is_migrated_not_discarded``
        exercises ``migrated`` but only for a ``.md`` asset (where the hardcoded HTML
        heading is correct); this class covers ``.sh``/``.py``/``.js`` but only for
        ``created``/``refreshed``. Nothing exercised ``migrated`` for a non-Markdown
        suffix — exactly the path that emitted ``ASSET_PROJECT_REGION_HEADING``'s
        unconditional ``<!-- ... -->`` HTML comment into a ``.sh``/``.py``/``.js`` file,
        breaking its syntax (live proof: ``nlt-orchestrator/scripts/gitfacts.sh``,
        ``bash -n`` exit 2).
        """
        target = tmp_path / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        # A pre-existing, hand-edited, pre-marker copy -- the exact shape that
        # drives install_or_refresh_asset's "migrated" branch.
        target.write_text(body + hand_edit_line, encoding="utf-8")

        action = write_project_script(tmp_path, rel_path, body, SKILL)
        assert action == "migrated"

        text = target.read_text(encoding="utf-8")
        assert hand_edit_line.strip() in text, (
            "the point of the migrated branch is preservation -- a fix that produces "
            "a parseable file by discarding local content would be worse than the bug"
        )
        assert "<!--" not in text and "-->" not in text, (
            f"a non-Markdown asset must never carry an HTML comment marker:\n{text!r}"
        )

        _MIGRATED_SYNTAX_CHECKS[checker](target)


class TestWriteProjectScript:
    def test_writes_under_project_root_scripts_dir(self, tmp_path: Path) -> None:
        write_project_script(tmp_path, "scripts/canary.sh", "echo hi\n", SKILL)
        assert (tmp_path / "scripts" / "canary.sh").exists()

    def test_version_stamp_is_present_in_the_begin_marker(self, tmp_path: Path) -> None:
        write_project_script(tmp_path, "scripts/canary.py", 'print("hi")\n', SKILL)
        text = (tmp_path / "scripts" / "canary.py").read_text(encoding="utf-8")
        assert f"v{__version__}" in text

    def test_dry_run_writes_nothing_and_does_not_chmod(self, tmp_path: Path) -> None:
        action = write_project_script(
            tmp_path, "scripts/canary.sh", "echo hi\n", SKILL, dry_run=True
        )
        assert action == "created"
        assert not (tmp_path / "scripts" / "canary.sh").exists()

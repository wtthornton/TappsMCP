"""TAP-7428: the ``.claude/skills`` (and ``.cursor/skills``) pin must cover
``docs_automation``'s six SKILL.md files, without silencing its agents half.

Before this fix, ``apply_docs_automation`` called ``generate_docs_automation``
with a single hardcoded ``overwrite=True`` and no reference to
``ctx.skip`` at all. ``SKIP_TOKENS["claude_skills"] == frozenset({".claude/skills"})``
and ``SKIP_TOKENS["docs_automation"] == frozenset({"docs_automation"})`` are
disjoint sets, so ``skipped("docs_automation", {".claude/skills"})`` was always
``False`` and the pin never reached the skills half at all — the six SKILL.md
files under ``.claude/skills/`` were rewritten on every upgrade regardless of
the pin.

Every test here corrupts the managed block of an already-generated file
*before* re-running the upgrade, then checks whether the corruption survived.
A byte-identical rerun of the same template is not evidence either way — the
generator produces the same bytes whether or not a skip decision fired
(see ``install_or_refresh_skill``'s ``updated == original`` short-circuit) — so
"unchanged file" only becomes a meaningful signal once there is a genuine
diff for the fix to either preserve or clobber.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from tapps_core.config.settings import _reset_settings_cache
from tapps_mcp.pipeline.skill_managed_block import MARKER_END
from tapps_mcp.pipeline.upgrade import upgrade_pipeline
from tapps_mcp.pipeline.upgrade_report import build_dry_run_summary

_INJECTED = "<!-- TAP-7428-TEST-CUSTOMIZATION-MARKER -->"

_DOCS_SKILLS = (
    "tapps-docs-refresh",
    "tapps-docs-bootstrap",
    "tapps-docs-finish-task",
    "tapps-docs-report",
    "tapps-docs-validate",
    "tapps-docs-generate",
)


@pytest.fixture(autouse=True)
def _fresh_settings() -> Iterator[None]:
    _reset_settings_cache()
    yield
    _reset_settings_cache()


def _docs_project(root: Path) -> None:
    (root / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = ["docs-mcp"]\n',
        encoding="utf-8",
    )


def _corrupt_managed_block(path: Path) -> str:
    """Inject a line inside the BEGIN..END managed block; return the corrupted text.

    A rewrite (``overwrite=True``) reverts this — the marker text is inside the
    span ``install_or_refresh_skill`` regenerates. A skipped write leaves it in
    place. This is the only place on the file a corruption is guaranteed to be
    clobbered by a real regeneration and preserved by a real skip.
    """
    original = path.read_text(encoding="utf-8")
    assert MARKER_END in original, f"{path} has no managed block to corrupt"
    corrupted = original.replace(MARKER_END, f"{_INJECTED}\n{MARKER_END}")
    path.write_text(corrupted, encoding="utf-8")
    return corrupted


def _corrupt_agent_file(path: Path) -> str:
    """Append a marker line to a plain (non-managed-block) generated file.

    ``generate_docs_agents`` writes the template verbatim via ``write_text``
    with no markers, so any byte in the file is clobbered by a real rewrite —
    unlike the skill files, there is no "outside the block" region that
    survives regeneration.
    """
    original = path.read_text(encoding="utf-8")
    corrupted = original + f"\n{_INJECTED}\n"
    path.write_text(corrupted, encoding="utf-8")
    return corrupted


def _skill_path(root: Path, platform: str, skill_name: str) -> Path:
    skills_dir = ".claude" if platform == "claude" else ".cursor"
    return root / skills_dir / "skills" / skill_name / "SKILL.md"


def _agent_path(root: Path, platform: str, name: str) -> Path:
    agents_dir = ".claude" if platform == "claude" else ".cursor"
    return root / agents_dir / "agents" / name


def _platform_component(result: dict, host: str, name: str) -> object:
    (matched,) = [p for p in result["components"]["platforms"] if p.get("host") == host]
    return matched["components"][name]


def _host_name(platform: str) -> str:
    return "claude-code" if platform == "claude" else "cursor"


def _skills_dir(root: Path, platform: str) -> Path:
    return root / (".claude" if platform == "claude" else ".cursor") / "skills"


def _skip_token(platform: str) -> str:
    return ".claude/skills" if platform == "claude" else ".cursor/skills"


class TestSkillsPinCoversDocsAutomationSkillsButNotAgents:
    """VAL-02: main + positive control, one body per platform.

    The main assertion (skills untouched) and the positive control (agents
    still rewritten) live together per test: a fix that over-broadly disables
    the whole ``docs_automation`` component would pass the main half and fail
    the positive control, so splitting them into separate tests would let
    that regression hide in whichever file runs first.
    """

    @pytest.mark.parametrize("platform", ["claude", "cursor"])
    def test_skills_pin_protects_skill_files_but_not_agent_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str
    ) -> None:
        _docs_project(tmp_path)

        # Bootstrap: create the baseline files this project would already have.
        upgrade_pipeline(tmp_path, platform=platform, dry_run=False)

        skill_paths = [_skill_path(tmp_path, platform, name) for name in _DOCS_SKILLS]
        agent_path = _agent_path(tmp_path, platform, "tapps-docs-reviewer.md")
        assert agent_path.is_file()

        corrupted_skills = [_corrupt_managed_block(p) for p in skill_paths]
        corrupted_agent = _corrupt_agent_file(agent_path)

        skip_token = ".claude/skills" if platform == "claude" else ".cursor/skills"
        monkeypatch.setenv("TAPPS_MCP_UPGRADE_SKIP_FILES", f'["{skip_token}"]')

        result = upgrade_pipeline(tmp_path, platform=platform, dry_run=False)

        docs_component_host = "claude-code" if platform == "claude" else "cursor"
        (matched,) = [
            p for p in result["components"]["platforms"] if p.get("host") == docs_component_host
        ]
        docs_info = matched["components"]["docs_automation"]
        assert docs_info != "skipped (upgrade_skip_files)", (
            "pinning only the skills directory must not disable the whole docs_automation component"
        )

        # Main assertion: 0 changed paths among the six SKILL.md files.
        for path, before in zip(skill_paths, corrupted_skills, strict=True):
            after = path.read_text(encoding="utf-8")
            assert after == before, f"{path} changed even though its pin was configured"

        # Positive control: the agents file the pin does not cover DID change
        # (the injected marker was reverted by a real regeneration).
        after_agent = agent_path.read_text(encoding="utf-8")
        assert after_agent != corrupted_agent
        assert _INJECTED not in after_agent


class TestFreshProjectPinBlocksCreation:
    """BLOCKER 1 (fix1): the pin must stop *creation*, not just refresh.

    ``generate_docs_skills`` used to gate only the ``target.exists()`` branch
    on ``overwrite`` — a fresh project (no SKILL.md files yet) always fell
    into the ``else: create`` branch regardless of the pin. This is the
    direct refutation: pin the skills dir on a project that has never been
    upgraded before, and confirm nothing lands under ``.claude/skills`` /
    ``.cursor/skills`` while the agents half still writes (positive control).
    """

    @pytest.mark.parametrize("platform", ["claude", "cursor"])
    def test_fresh_project_with_pin_creates_zero_skill_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str
    ) -> None:
        _docs_project(tmp_path)
        monkeypatch.setenv("TAPPS_MCP_UPGRADE_SKIP_FILES", f'["{_skip_token(platform)}"]')

        result = upgrade_pipeline(tmp_path, platform=platform, dry_run=False)

        docs_info = _platform_component(result, _host_name(platform), "docs_automation")
        assert isinstance(docs_info, dict), docs_info
        assert docs_info["skills"]["created"] == []
        assert sorted(docs_info["skills"]["skipped"]) == sorted(_DOCS_SKILLS)

        skills_dir = _skills_dir(tmp_path, platform)
        on_disk = sorted(p.name for p in skills_dir.iterdir()) if skills_dir.is_dir() else []
        for name in _DOCS_SKILLS:
            assert name not in on_disk, f"{name} was created under a pinned skills dir"

        # Positive control: agents half is unaffected by the skills pin.
        assert docs_info["agents"]["created"], "agents half must still write under the pin"
        assert _agent_path(tmp_path, platform, "tapps-docs-reviewer.md").is_file()


class TestDeletedPinnedSkillNotRecreated:
    """BLOCKER 1 (fix1): a deleted pinned skill must not reappear."""

    @pytest.mark.parametrize("platform", ["claude", "cursor"])
    def test_deleting_a_pinned_skill_then_upgrading_does_not_recreate_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str
    ) -> None:
        _docs_project(tmp_path)

        # Bootstrap unpinned so all six skills exist on disk first.
        upgrade_pipeline(tmp_path, platform=platform, dry_run=False)
        target = _skill_path(tmp_path, platform, "tapps-docs-report")
        assert target.is_file()
        target.unlink()
        target.parent.rmdir()
        assert not target.exists(), "before: deleted"

        monkeypatch.setenv("TAPPS_MCP_UPGRADE_SKIP_FILES", f'["{_skip_token(platform)}"]')
        result = upgrade_pipeline(tmp_path, platform=platform, dry_run=False)

        docs_info = _platform_component(result, _host_name(platform), "docs_automation")
        assert not target.exists(), "after: pin must not recreate a deleted pinned skill"
        assert "tapps-docs-report" not in docs_info["skills"]["created"]


class TestDryRunMatchesApply:
    """BLOCKER 2 (fix1): the ``plan`` lambda must read ``ctx.skip`` too.

    Before this fix, ``plan`` for ``docs_automation`` was a bare literal that
    always reported ``managed_skills`` in full and never appeared in
    ``skipped_components`` — disagreeing with a pinned live run, which wrote
    nothing under the skills dir. This proves the two now agree.
    """

    @pytest.mark.parametrize("platform", ["claude", "cursor"])
    def test_dryrun_and_live_agree_under_the_pin(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str
    ) -> None:
        _docs_project(tmp_path)
        monkeypatch.setenv("TAPPS_MCP_UPGRADE_SKIP_FILES", f'["{_skip_token(platform)}"]')

        dry = upgrade_pipeline(tmp_path, platform=platform, dry_run=True)
        dry_docs = _platform_component(dry, _host_name(platform), "docs_automation")
        assert isinstance(dry_docs, dict)
        assert dry_docs["skills"] == "skipped (upgrade_skip_files)"
        assert dry_docs["managed_skills"] == []

        summary = build_dry_run_summary(dry)
        expected_entry = f"{_host_name(platform)}:docs_automation.skills"
        assert expected_entry in summary["skipped_components"], summary["skipped_components"]

        live = upgrade_pipeline(tmp_path, platform=platform, dry_run=False)
        live_docs = _platform_component(live, _host_name(platform), "docs_automation")
        assert live_docs["skills"]["created"] == []
        assert sorted(live_docs["skills"]["skipped"]) == sorted(_DOCS_SKILLS)

        # Agree on the agents half too: neither report shows it skipped.
        assert live_docs["agents"]["created"], "live: agents half must still write"

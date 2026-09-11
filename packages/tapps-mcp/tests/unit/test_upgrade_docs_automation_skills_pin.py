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

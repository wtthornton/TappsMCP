"""Every generated SKILL.md must open with its YAML frontmatter.

Claude Code parses skill frontmatter only when the opening ``---`` is the first
byte of the file. Two generators used to prepend text above it — the engagement
note in ``platform_skills`` and the managed-block marker in
``skill_managed_block`` — which silently dropped ``name``, ``description`` and
``allowed-tools`` from every affected skill and stopped it auto-triggering. The
symptom was invisible in review: the file looked fine, and the skill listing
showed the banner line where the description should be.

These tests pin the invariant at both generators and at the helper they share.
"""

from __future__ import annotations

import re

import pytest

from tapps_mcp.pipeline.platform_skills import (
    CLAUDE_SKILLS,
    CURSOR_SKILLS,
    generate_skills,
)
from tapps_mcp.pipeline.skill_managed_block import (
    MARKER_BEGIN_PREFIX,
    MARKER_END,
    install_or_refresh_skill,
    prepend_below_frontmatter,
    split_frontmatter,
    wrap_with_markers,
)

ENGAGEMENT_LEVELS = ["high", "medium", "low"]

BODY = "---\nname: demo\ndescription: A demo skill.\n---\n\nPlatform body line.\n"


def _frontmatter_starts_file(text: str) -> bool:
    return text.startswith("---\n")


class TestSplitFrontmatter:
    def test_splits_delimiters_into_the_frontmatter_half(self):
        frontmatter, rest = split_frontmatter(BODY)
        assert frontmatter == "---\nname: demo\ndescription: A demo skill.\n---\n"
        assert rest == "\nPlatform body line.\n"

    def test_no_frontmatter_returns_empty_and_whole_text(self):
        assert split_frontmatter("# Just a heading\n") == ("", "# Just a heading\n")

    def test_a_bare_rule_mid_body_is_not_frontmatter(self):
        """``---`` further down the file must not be mistaken for the block."""
        text = "# Heading\n\n---\n\nmore\n"
        assert split_frontmatter(text) == ("", text)


class TestPrependBelowFrontmatter:
    def test_prefix_lands_under_the_frontmatter(self):
        out = prepend_below_frontmatter(BODY, "*Engagement: MANDATORY.*\n\n")
        assert _frontmatter_starts_file(out)
        assert out == (
            "---\nname: demo\ndescription: A demo skill.\n---\n"
            "*Engagement: MANDATORY.*\n\nPlatform body line.\n"
        )

    def test_empty_prefix_is_a_no_op(self):
        assert prepend_below_frontmatter(BODY, "") == BODY

    def test_without_frontmatter_the_prefix_goes_first(self):
        assert prepend_below_frontmatter("body\n", "note\n") == "note\nbody\n"


class TestWrapWithMarkers:
    def test_markers_wrap_only_the_prose(self):
        out = wrap_with_markers(BODY, "demo", version="1.2.3")
        assert _frontmatter_starts_file(out)
        assert out.index("---\n") < out.index(MARKER_BEGIN_PREFIX)
        assert "name: demo" not in out.split(MARKER_BEGIN_PREFIX)[1]
        assert out.rstrip().endswith(MARKER_END)


class TestInstallOrRefresh:
    def test_created_file_starts_with_frontmatter(self, tmp_path):
        target = tmp_path / "SKILL.md"
        assert install_or_refresh_skill(target, BODY, "demo", version="1.2.3") == "created"
        assert _frontmatter_starts_file(target.read_text())

    def test_refresh_is_idempotent(self, tmp_path):
        target = tmp_path / "SKILL.md"
        install_or_refresh_skill(target, BODY, "demo", version="1.2.3")
        assert install_or_refresh_skill(target, BODY, "demo", version="1.2.3") == "unchanged"

    def test_refresh_preserves_the_project_region_below_the_block(self, tmp_path):
        target = tmp_path / "SKILL.md"
        install_or_refresh_skill(target, BODY, "demo", version="1.2.3")
        target.write_text(target.read_text() + "\n## Project notes\nkeep me\n")
        newer = BODY.replace("Platform body line.", "Platform body line v2.")

        assert install_or_refresh_skill(target, newer, "demo", version="1.2.4") == "refreshed"
        content = target.read_text()
        assert "keep me" in content
        assert "Platform body line v2." in content
        assert _frontmatter_starts_file(content)

    def test_a_pre_fix_file_heals_on_refresh(self, tmp_path):
        """The old layout wrapped the frontmatter inside the block; fix it in place."""
        target = tmp_path / "SKILL.md"
        broken = (
            f"{MARKER_BEGIN_PREFIX} demo v1.0.0 -->\n"
            "---\nname: demo\ndescription: stale.\n---\n\nold body\n"
            f"{MARKER_END}\n\n## Project notes\nkeep me\n"
        )
        target.write_text(broken)
        assert not _frontmatter_starts_file(broken)

        assert install_or_refresh_skill(target, BODY, "demo", version="1.2.3") == "refreshed"
        content = target.read_text()
        assert _frontmatter_starts_file(content)
        assert "description: A demo skill." in content
        assert "description: stale." not in content
        assert "keep me" in content
        assert content.count(MARKER_BEGIN_PREFIX) == 1

    def test_migration_of_an_unmarked_file_keeps_frontmatter_first(self, tmp_path):
        target = tmp_path / "SKILL.md"
        target.write_text("---\nname: demo\n---\n\nhand-authored\n")

        assert install_or_refresh_skill(target, BODY, "demo", version="1.2.3") == "migrated"
        content = target.read_text()
        assert _frontmatter_starts_file(content)
        assert "hand-authored" in content


@pytest.mark.parametrize("engagement", ENGAGEMENT_LEVELS)
@pytest.mark.parametrize("platform", ["claude", "cursor"])
class TestGenerateSkills:
    def test_every_generated_skill_opens_with_frontmatter(self, tmp_path, platform, engagement):
        generate_skills(tmp_path, platform, engagement_level=engagement)

        written = sorted((tmp_path / f".{platform}" / "skills").glob("*/SKILL.md"))
        assert written, "generate_skills wrote nothing"

        offenders = [p.name for p in written if not _frontmatter_starts_file(p.read_text())]
        assert offenders == [], f"frontmatter is not first in: {offenders}"

    def test_the_declared_name_survives_generation(self, tmp_path, platform, engagement):
        """A parseable file is not enough — the name must still be readable."""
        generate_skills(tmp_path, platform, engagement_level=engagement)

        templates = CLAUDE_SKILLS if platform == "claude" else CURSOR_SKILLS
        for path in sorted((tmp_path / f".{platform}" / "skills").glob("*/SKILL.md")):
            if path.parent.name not in templates:
                continue
            frontmatter, _ = split_frontmatter(path.read_text())
            assert re.search(rf"^name:\s*{re.escape(path.parent.name)}\s*$", frontmatter, re.M), (
                f"{path.parent.name}: name missing from its frontmatter block"
            )

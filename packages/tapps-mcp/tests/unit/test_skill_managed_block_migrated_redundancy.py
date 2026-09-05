"""TAP-7078 boxes 3 and 7: a migrated SKILL.md region must never silently
duplicate the managed block it sits below.

``install_or_refresh_skill``'s legacy-migration branch used to concatenate the
preserved region verbatim with zero redundancy check — the asset path
(``skill_asset_policy.install_or_refresh_asset``) already got this from
TAP-6943/L8b; this ports the same ``heading_redundancy`` check to SKILL.md,
plus a second, independent check (``duplicate_line_fraction``) for a preserved
region that duplicates most of the managed block's lines without matching any
single heading exactly — the counterweight-drift shape that produced a
977-line local override.
"""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.pipeline.skill_managed_block import (
    install_or_refresh_skill,
    migrated_region_redundancy,
)

_CANONICAL_BODY = "## Setup\nSet things up.\n\n## Usage\nUse it.\n"


def _legacy_skill_md(body: str) -> str:
    return f"---\nname: demo\ndescription: demo skill\n---\n{body}"


class TestMigratedRegionRedundancyMeasurement:
    """Pure measurement, independent of the file-write branch below."""

    def test_migrated_region_redundancy_flags_duplicate_heading(self) -> None:
        preserved = "## Setup\nSet things up.\n\n## MyStuff\nGenuinely unique.\n"
        redundancy = migrated_region_redundancy(preserved, _CANONICAL_BODY)
        assert redundancy.section_redundancy.duplicate == ("## Setup",)
        assert redundancy.flagged is True
        assert "duplicate the managed block" in redundancy.verdict()

    def test_migrated_region_redundancy_does_not_flag_genuinely_different_region(self) -> None:
        preserved = "## MyCustomSection\nReally unique content, no overlap upstream.\n"
        redundancy = migrated_region_redundancy(preserved, _CANONICAL_BODY)
        assert redundancy.section_redundancy.duplicate_count == 0
        assert redundancy.duplicate_line_fraction == 0.0
        assert redundancy.flagged is False
        assert redundancy.verdict() == "no redundancy with the managed block detected"

    def test_duplicate_guard_flags_over_10_percent_line_duplication_without_heading_match(
        self,
    ) -> None:
        """Box 7: no heading text matches, but most lines are lifted verbatim."""
        canonical = "\n".join(f"managed line {i}" for i in range(20))
        # No ATX headings at all here, so heading_redundancy sees zero
        # sections — only the line-fraction guard can catch this.
        preserved = "\n".join(f"managed line {i}" for i in range(5)) + "\nmy own line\n"
        redundancy = migrated_region_redundancy(preserved, canonical)
        assert redundancy.section_redundancy.total_count == 0
        assert redundancy.duplicate_line_fraction > 0.10
        assert redundancy.flagged is True
        assert "duplicate the managed block above" in redundancy.verdict()

    def test_duplicate_guard_does_not_flag_under_10_percent(self) -> None:
        canonical = "\n".join(f"managed line {i}" for i in range(20))
        preserved = "managed line 0\nmy own line one\nmy own line two\n"
        redundancy = migrated_region_redundancy(preserved, canonical)
        assert redundancy.duplicate_line_fraction <= 0.10
        assert redundancy.flagged is False


class TestInstallOrRefreshSkillMigratedRedundancyBanner:
    """A legacy migration must be flagged in the written file, never silent."""

    def test_migrated_region_with_heading_duplicate_is_flagged_in_file(
        self, tmp_path: Path
    ) -> None:
        target = tmp_path / "SKILL.md"
        target.write_text(
            _legacy_skill_md("## Setup\nSet things up.\n\n## Mine\nUnique text.\n"),
            encoding="utf-8",
        )

        action = install_or_refresh_skill(target, _CANONICAL_BODY, "demo")
        assert action == "migrated"
        text = target.read_text(encoding="utf-8")
        assert "flagged:" in text
        assert "## Setup" in text

    def test_migrated_region_over_10_percent_duplicate_lines_is_flagged_in_file(
        self, tmp_path: Path
    ) -> None:
        canonical = "\n".join(f"managed line {i}" for i in range(20))
        target = tmp_path / "SKILL.md"
        preserved = "\n".join(f"managed line {i}" for i in range(5)) + "\nmy own line\n"
        target.write_text(_legacy_skill_md(preserved), encoding="utf-8")

        action = install_or_refresh_skill(target, canonical, "demo")
        assert action == "migrated"
        text = target.read_text(encoding="utf-8")
        assert "flagged:" in text
        assert "of this region's lines duplicate" in text

    def test_migrated_region_genuinely_different_is_never_flagged(self, tmp_path: Path) -> None:
        target = tmp_path / "SKILL.md"
        target.write_text(
            _legacy_skill_md("## MyOwnSection\nReally unique content, no overlap.\n"),
            encoding="utf-8",
        )

        action = install_or_refresh_skill(target, _CANONICAL_BODY, "demo")
        assert action == "migrated"
        text = target.read_text(encoding="utf-8")
        assert "flagged:" not in text

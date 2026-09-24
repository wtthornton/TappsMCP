"""TAP-8100: upgrade drops a migrated region that carries no line of its own.

The pre-marker migration left a ``tapps-skill-project-customizations`` region
(``tapps-skill-asset-project-customizations`` for companion assets) below the
managed block. Its own verdict said "100% of this region's lines duplicate the
managed block above", yet every later upgrade carried it verbatim, doubling
the size of consumer skills. A region with even one unique line must still
survive byte-for-byte.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tapps_mcp.pipeline.skill_asset_policy import (
    asset_project_region_heading,
    install_or_refresh_asset,
    policy_header,
)
from tapps_mcp.pipeline.skill_managed_block import (
    PROJECT_REGION_HEADING,
    install_or_refresh_skill,
)

if TYPE_CHECKING:
    from pathlib import Path

_CANONICAL = (
    "---\nname: demo\ndescription: demo skill\n---\n## Setup\nSet things up.\n\n## Usage\nUse it.\n"
)
_CANONICAL_BODY = "## Setup\nSet things up.\n\n## Usage\nUse it.\n"
_FLAG = "<!-- flagged: 100% of this region's lines duplicate the managed block above — review and trim -->"
# The shape the pre-marker migration wrote: heading + verdict, a blank line,
# then the old body — which opened with the old overwrite policy header.
_DUPLICATE_REGION = (
    f"\n\n{PROJECT_REGION_HEADING}\n{_FLAG}\n\n{policy_header('overwrite')}\n\n{_CANONICAL_BODY}"
)


def _fresh_skill(tmp_path: Path) -> Path:
    target = tmp_path / "SKILL.md"
    assert install_or_refresh_skill(target, _CANONICAL, "demo") == "created"
    return target


class TestSkillRegion:
    def test_full_duplicate_region_is_dropped_on_refresh(self, tmp_path: Path) -> None:
        target = _fresh_skill(tmp_path)
        fresh = target.read_text(encoding="utf-8")
        target.write_text(fresh + _DUPLICATE_REGION, encoding="utf-8")

        assert install_or_refresh_skill(target, _CANONICAL, "demo") == "refreshed"
        assert target.read_text(encoding="utf-8") == fresh

    def test_partial_duplicate_region_is_kept_verbatim(self, tmp_path: Path) -> None:
        target = _fresh_skill(tmp_path)
        content = target.read_text(encoding="utf-8") + _DUPLICATE_REGION + "Our own rule.\n"
        target.write_text(content, encoding="utf-8")

        assert install_or_refresh_skill(target, _CANONICAL, "demo") == "unchanged"
        assert target.read_text(encoding="utf-8") == content

    def test_project_text_above_a_dropped_region_survives(self, tmp_path: Path) -> None:
        target = _fresh_skill(tmp_path)
        fresh = target.read_text(encoding="utf-8")
        target.write_text(fresh + "\nLocal note.\n" + _DUPLICATE_REGION, encoding="utf-8")

        install_or_refresh_skill(target, _CANONICAL, "demo")
        assert target.read_text(encoding="utf-8") == fresh + "\nLocal note.\n"

    def test_legacy_copy_with_no_unique_line_is_not_preserved(self, tmp_path: Path) -> None:
        target = tmp_path / "SKILL.md"
        target.write_text(
            f"---\nname: demo\n---\n{policy_header('overwrite')}\n\n{_CANONICAL_BODY}",
            encoding="utf-8",
        )

        assert install_or_refresh_skill(target, _CANONICAL, "demo") == "refreshed"
        assert PROJECT_REGION_HEADING not in target.read_text(encoding="utf-8")

    def test_legacy_copy_with_a_unique_line_still_migrates_and_survives(
        self, tmp_path: Path
    ) -> None:
        target = tmp_path / "SKILL.md"
        target.write_text(f"---\nname: demo\n---\n{_CANONICAL_BODY}Mine.\n", encoding="utf-8")

        assert install_or_refresh_skill(target, _CANONICAL, "demo") == "migrated"
        migrated = target.read_text(encoding="utf-8")
        assert "flagged:" in migrated
        assert install_or_refresh_skill(target, _CANONICAL, "demo") == "unchanged"
        assert target.read_text(encoding="utf-8") == migrated


class TestAssetRegion:
    def _fresh(self, tmp_path: Path, rel_path: str, body: str) -> tuple[Path, str]:
        target = tmp_path / rel_path
        assert install_or_refresh_asset(target, body, "demo", rel_path) == "created"
        return target, target.read_text(encoding="utf-8")

    def test_full_duplicate_md_region_is_dropped_on_refresh(self, tmp_path: Path) -> None:
        rel_path = "assets/prompt-template.md"
        target, fresh = self._fresh(tmp_path, rel_path, _CANONICAL_BODY)
        region = f"\n{asset_project_region_heading(rel_path)}\n\n{_CANONICAL_BODY}"
        target.write_text(fresh + region, encoding="utf-8")

        assert install_or_refresh_asset(target, _CANONICAL_BODY, "demo", rel_path) == "refreshed"
        assert target.read_text(encoding="utf-8") == fresh

    def test_partial_duplicate_md_region_is_kept_verbatim(self, tmp_path: Path) -> None:
        rel_path = "assets/prompt-template.md"
        target, fresh = self._fresh(tmp_path, rel_path, _CANONICAL_BODY)
        content = f"{fresh}\n{asset_project_region_heading(rel_path)}\n\n{_CANONICAL_BODY}Mine.\n"
        target.write_text(content, encoding="utf-8")

        assert install_or_refresh_asset(target, _CANONICAL_BODY, "demo", rel_path) == "unchanged"
        assert target.read_text(encoding="utf-8") == content

    def test_full_duplicate_commented_sh_region_is_dropped(self, tmp_path: Path) -> None:
        rel_path = "scripts/run.sh"
        body = "#!/usr/bin/env bash\necho one\n\necho two\n"
        legacy = "#!/usr/bin/env bash\necho one\necho two\nMine\n"
        target = tmp_path / rel_path
        target.parent.mkdir(parents=True)
        target.write_text(legacy, encoding="utf-8")
        assert install_or_refresh_asset(target, body, "demo", rel_path) == "migrated"
        # The migration comment-wrapped the region; remove the unique line so
        # every remaining (commented) line duplicates canonical.
        target.write_text(
            target.read_text(encoding="utf-8").replace("# Mine\n", ""), encoding="utf-8"
        )

        assert install_or_refresh_asset(target, body, "demo", rel_path) == "refreshed"
        assert "project-customizations" not in target.read_text(encoding="utf-8")

    def test_legacy_asset_with_only_a_policy_header_added_is_not_preserved(
        self, tmp_path: Path
    ) -> None:
        rel_path = "references/map.md"
        target = tmp_path / rel_path
        target.parent.mkdir(parents=True)
        target.write_text(f"{policy_header('overwrite')}\n{_CANONICAL_BODY}", encoding="utf-8")

        assert install_or_refresh_asset(target, _CANONICAL_BODY, "demo", rel_path) == "refreshed"
        assert "project-customizations" not in target.read_text(encoding="utf-8")

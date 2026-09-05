"""TAP-6943: measure a migrated asset's preserved-region redundancy on section BODIES.

Split out of test_skill_asset_policy.py (already at its quality-gate size
ceiling — a below-gate megafile split needs a test split alongside it) rather
than grown in place.

Fix round 1: the original version of this module measured redundancy by
comparing ATX heading LINES only, so two sections that shared a heading but
had completely different bodies (a genuine local customisation) were counted
as duplicates. A preserved ``## Setup`` section with hand-written content was
then reported ``fully_redundant`` and stamped "safe to delete this entire
region" purely because a canonical ``## Setup`` heading also existed — a
data-loss-shaped instruction to the operator. 'Redundant' must be a real diff
over section heading *and* body (the ``comm`` the nlt-orchestrator precedent
actually ran, over CONTENT): a section is a duplicate only when both match; a
shared heading with a different body is ``modified``, never removable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.pipeline.skill_asset_policy import (
    heading_redundancy,
    install_or_refresh_asset,
)

SKILL = "orchestration-prompt"
ASSET = "assets/prompt-template.md"

_CANONICAL = "## Setup\nSet things up.\n\n## Usage\nUse it.\n"


class TestSectionRedundancy:
    """TAP-6943 fix round 1: 'redundant' is measured on section bodies, not
    heading lines alone — a modified section must never be reported removable."""

    def test_same_heading_different_body_is_modified_not_duplicate(self) -> None:
        preserved = "## Setup\nOld setup text, hand-customised.\n\n## Usage\nUse it.\n"
        r = heading_redundancy(preserved, _CANONICAL)
        assert r.modified == ("## Setup",)
        assert r.duplicate == ("## Usage",)
        assert r.unique == ()
        assert r.fully_redundant is False

    def test_identical_heading_and_body_is_duplicate(self) -> None:
        preserved = "## Setup\nSet things up.\n\n## Usage\nUse it.\n"
        r = heading_redundancy(preserved, _CANONICAL)
        assert r.duplicate == ("## Setup", "## Usage")
        assert r.modified == ()
        assert r.unique == ()
        assert r.fully_redundant is True

    def test_heading_absent_from_canonical_is_unique(self) -> None:
        preserved = "## MyCustomSection\nGenuinely unique content.\n"
        r = heading_redundancy(preserved, _CANONICAL)
        assert r.unique == ("## MyCustomSection",)
        assert r.duplicate == ()
        assert r.modified == ()
        assert r.fully_redundant is False

    def test_mixed_region_counts_are_correct_and_not_fully_redundant(self) -> None:
        preserved = (
            "## Setup\nSet things up.\n\n"  # duplicate
            "## Usage\nHand-edited usage notes.\n\n"  # modified
            "## MyCustomSection\nGenuinely unique content.\n"  # unique
        )
        r = heading_redundancy(preserved, _CANONICAL)
        assert (r.duplicate_count, r.modified_count, r.unique_count, r.total_count) == (1, 1, 1, 3)
        assert r.fully_redundant is False
        assert r.partially_redundant is True

    def test_trailing_whitespace_and_blank_lines_still_count_as_duplicate(self) -> None:
        preserved = "## Setup  \nSet things up.   \n\n\n\n## Usage\nUse it.\n"
        r = heading_redundancy(preserved, _CANONICAL)
        assert r.duplicate == ("## Setup", "## Usage")
        assert r.modified == ()
        assert r.fully_redundant is True

    def test_genuinely_identical_bodies_is_fully_redundant(self) -> None:
        r = heading_redundancy(_CANONICAL, _CANONICAL)
        assert r.fully_redundant is True
        assert r.modified_count == 0
        assert r.unique_count == 0

    def test_no_headings_is_never_reported_redundant(self) -> None:
        r = heading_redundancy("plain prose, no headings", _CANONICAL)
        assert r.total_count == 0
        assert r.fully_redundant is False
        assert r.partially_redundant is False

    def test_negative_control_heading_only_comparison_would_wrongly_pass(self) -> None:
        """Documents the exact defect this fix closes: a heading-only 'comm' on
        ATX lines (ignoring body) marks a hand-customised body as a duplicate.
        Kept as a regression tripwire alongside the real (body-aware) assertions
        above, which fail on the pre-fix implementation."""
        preserved = "## Setup\nOld setup text, hand-customised.\n\n## Usage\nUse it.\n"
        preserved_headings = {"## Setup", "## Usage"}
        canonical_headings = {"## Setup", "## Usage"}
        heading_only_duplicates = preserved_headings & canonical_headings
        assert heading_only_duplicates == {"## Setup", "## Usage"}  # the bug's view

        r = heading_redundancy(preserved, _CANONICAL)
        assert r.duplicate != ("## Setup", "## Usage")  # the fix's view disagrees
        assert r.modified == ("## Setup",)


class TestMigratedAssetRedundancyVerdict:
    """The banner :func:`install_or_refresh_asset` writes into a migrated file
    must never say "safe to delete" for a region carrying modified/unique
    sections, and must name those sections when it isn't fully redundant."""

    @pytest.mark.parametrize(
        ("preserved", "must_contain", "must_not_contain"),
        [
            pytest.param(
                # Same headings/bodies as canonical but reordered, so it is
                # NOT byte-identical to canonical (which would take the
                # separate "pristine pre-marker copy" branch instead of the
                # migrated/preserved-region branch this test targets).
                "## Usage\nUse it.\n\n## Setup\nSet things up.\n",
                ["fully redundant", "all 2 heading(s)", "safe to delete this entire region"],
                [],
                id="fully_redundant_is_reported",
            ),
            pytest.param(
                "## Setup\nOld setup text, hand-customised.\n\n## Usage\nUse it.\n",
                ["carries local content", "1 modified", "## Setup"],
                ["safe to delete", "fully redundant"],
                id="same_heading_diff_body_is_never_removable",
            ),
            pytest.param(
                "## OnlyMine\nReally unique content, no relation upstream.\n",
                ["carries local content", "1 unique", "## OnlyMine"],
                ["safe to delete", "fully redundant"],
                id="unique_customization_never_reported_removable",
            ),
            pytest.param(
                "## Setup\nSet things up.\n\n"
                "## Usage\nHand-edited usage notes.\n\n"
                "## MyCustomSection\nGenuinely unique content.\n",
                [
                    "carries local content",
                    "1 modified",
                    "1 unique",
                    "## Usage",
                    "## MyCustomSection",
                ],
                ["safe to delete this entire region"],
                id="mixed_region_names_modified_and_unique",
            ),
        ],
    )
    def test_migrated_asset_redundancy_verdict(
        self, tmp_path: Path, preserved: str, must_contain: list[str], must_not_contain: list[str]
    ) -> None:
        target = tmp_path / "a.md"
        target.write_text(preserved, encoding="utf-8")

        assert install_or_refresh_asset(target, _CANONICAL, SKILL, ASSET) == "migrated"
        text = target.read_text(encoding="utf-8")
        for expected in must_contain:
            assert expected in text
        for forbidden in must_not_contain:
            assert forbidden not in text

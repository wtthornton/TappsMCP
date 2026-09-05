"""TAP-6943: measure a migrated asset's preserved-region redundancy at heading level.

Split out of test_skill_asset_policy.py (already at its quality-gate size
ceiling — a below-gate megafile split needs a test split alongside it) rather
than grown in place. 'Redundant' is a real diff over ATX headings, not a
byte/line count: a partially-redundant region must never be reported as
safe to delete.
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

_CANONICAL_HEADINGS = "## Setup\nSet things up.\n\n## Usage\nUse it.\n"

# (preserved region, expected duplicate_count, expected total_count) against
# _CANONICAL_HEADINGS -- covers fully redundant, partially redundant, no
# overlap, and no headings at all in one parametrized comparison.
_REDUNDANCY_CASES = [
    pytest.param(
        "## Setup\nOld setup text.\n\n## Usage\nOld usage text.\n",
        2,
        2,
        id="fully_redundant",
    ),
    pytest.param(
        "## Setup\nOld setup text.\n\n## Usage\nOld usage text.\n\n"
        "## MyCustomSection\nGenuinely unique content.\n",
        2,
        3,
        id="partially_redundant",
    ),
    pytest.param(
        "## OnlyMine\nReally unique content, no relation upstream.\n",
        0,
        1,
        id="no_overlap",
    ),
    pytest.param("plain prose, no headings", 0, 0, id="no_headings"),
]


class TestHeadingRedundancy:
    """TAP-6943: 'redundant' is measured at heading level with a real diff —
    a partially-redundant region must never be reported removable."""

    @pytest.mark.parametrize(("preserved", "expected_dup", "expected_total"), _REDUNDANCY_CASES)
    def test_direct_comparison(
        self, preserved: str, expected_dup: int, expected_total: int
    ) -> None:
        r = heading_redundancy(preserved, _CANONICAL_HEADINGS)
        assert (r.duplicate_count, r.total_count) == (expected_dup, expected_total)
        assert r.fully_redundant == (expected_total > 0 and expected_dup == expected_total)
        assert r.partially_redundant == (0 < expected_dup < expected_total)

    @pytest.mark.parametrize(
        ("preserved", "must_contain", "must_not_contain"),
        [
            pytest.param(
                "## Setup\nOld setup text.\n\n## Usage\nOld usage text.\n",
                ["fully redundant", "all 2 heading(s)", "safe to delete this entire region"],
                [],
                id="fully_redundant_is_reported",
            ),
            pytest.param(
                "## OnlyMine\nReally unique content, no relation upstream.\n",
                [],
                ["fully redundant", "partially redundant", "safe to delete"],
                id="unique_customization_never_reported_removable",
            ),
            pytest.param(
                "## Setup\nOld setup text.\n\n## Usage\nOld usage text.\n\n"
                "## MyCustomSection\nGenuinely unique content.\n",
                ["partially redundant", "2/3 heading(s)", "MyCustomSection"],
                ["safe to delete this entire region"],
                id="partial_overlap_names_the_split",
            ),
        ],
    )
    def test_migrated_asset_redundancy_verdict(
        self, tmp_path: Path, preserved: str, must_contain: list[str], must_not_contain: list[str]
    ) -> None:
        target = tmp_path / "a.md"
        target.write_text(preserved, encoding="utf-8")

        assert install_or_refresh_asset(target, _CANONICAL_HEADINGS, SKILL, ASSET) == "migrated"
        text = target.read_text(encoding="utf-8")
        for expected in must_contain:
            assert expected in text
        for forbidden in must_not_contain:
            assert forbidden not in text

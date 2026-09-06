"""Core generation tests for project-root scaffolded scripts (TAP-6884).

Verifies that ``generate_measure_script`` / ``generate_gitfacts_script`` write
``scripts/measure.py`` / ``scripts/gitfacts.sh`` at the project root on the
comment-syntax-aware managed-block asset class (:mod:`skill_asset_policy`),
and that the ported bodies match the staged sources exactly (apart from the
one documented line).

See sibling files for the rest of the lane's coverage (split for gate size —
a single megafile fails the maintainability/complexity categories on line
count and function count alone, independent of any one test's quality):

- ``test_platform_project_scripts_evidence.py`` — evidence items 6 and 7
  (executable + parses after init/upgrade; project content survives refresh).
- ``test_platform_project_scripts_pipeline.py`` — init/upgrade pipeline wiring.
- ``test_platform_project_scripts_skip_tokens.py`` — skip-token vocabulary.
- ``test_measure_script_behavior.py`` / ``test_gitfacts_script_behavior.py`` —
  evidence items 1-5, the scripts' own functional behavior.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from tapps_mcp.pipeline.platform_project_scripts import (
    GITFACTS_SH_BODY,
    GITFACTS_SH_REL_PATH,
    MEASURE_PY_BODY,
    MEASURE_PY_REL_PATH,
    generate_gitfacts_script,
    generate_measure_script,
)
from tapps_mcp.pipeline.skill_asset_policy import wrap_asset

_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# md5 of the vendored staged sources (packages/tapps-mcp/tests/fixtures/) --
# these are checked-in snapshots of the "staged, proven originals" TAP-6884
# ported from, not the live copies. Guards against silent fixture edits.
_MEASURE_PY_STAGED_MD5 = "5690cee6a231a8d8f004437f20cd44f6"
_GITFACTS_SH_STAGED_MD5 = "3d576bb63f5d0b35c2ae2d2a04fae638"


class TestSourceIsPortedFaithfully:
    """The staged sources are the contract — verify against their md5, not memory.

    Vendored under ``tests/fixtures/`` rather than read from ``/tmp``: the
    original ``/tmp/src-measure.py`` / ``/tmp/src-gitfacts.sh`` staging files
    are outside the repo and drifted after TAP-6884 landed (confirmed via
    ``git log``: the PR body says both scripts were "ported byte-for-byte
    from their staged, proven originals except one documented line" -- the
    fixtures here are that original content, reconstructed from
    ``GITFACTS_SH_BODY``/``MEASURE_PY_BODY`` plus the one documented line
    revert, NOT a refresh of the now-drifted ``/tmp`` copies).
    """

    def test_measure_body_is_byte_identical_to_staged_source(self) -> None:
        path = _FIXTURES_DIR / "src-measure.py.fixture"
        source = path.read_text(encoding="utf-8")
        digest = hashlib.md5(source.encode("utf-8"), usedforsecurity=False).hexdigest()
        assert digest == _MEASURE_PY_STAGED_MD5
        assert source == MEASURE_PY_BODY

    def test_gitfacts_body_differs_from_staged_source_by_exactly_one_line(self) -> None:
        """The only permitted deviation: usage()'s self-read, made robust to the
        line-shift the managed-block wrapper introduces (documented in the
        module docstring and the PR body)."""
        path = _FIXTURES_DIR / "src-gitfacts.sh.fixture"
        raw = path.read_text(encoding="utf-8")
        digest = hashlib.md5(raw.encode("utf-8"), usedforsecurity=False).hexdigest()
        assert digest == _GITFACTS_SH_STAGED_MD5
        source = raw.splitlines()
        body = GITFACTS_SH_BODY.splitlines()
        assert len(source) == len(body)
        diffs = [(a, b) for a, b in zip(source, body, strict=True) if a != b]
        assert len(diffs) == 1
        old_line, new_line = diffs[0]
        assert old_line == "usage() { sed -n '3,9p' \"${BASH_SOURCE[0]}\" >&2; exit 2; }"
        assert new_line == (
            "usage() { sed -n '/^# Usage:/,/^# *$/p' \"${BASH_SOURCE[0]}\" >&2; exit 2; }"
        )


class TestGenerateMeasureScript:
    def test_creates_script_file(self, tmp_path: Path) -> None:
        generate_measure_script(tmp_path)
        assert (tmp_path / MEASURE_PY_REL_PATH).exists()

    def test_returns_created_action(self, tmp_path: Path) -> None:
        result = generate_measure_script(tmp_path)
        assert result == {"file": MEASURE_PY_REL_PATH, "action": "created"}

    def test_returns_unchanged_on_rerun(self, tmp_path: Path) -> None:
        generate_measure_script(tmp_path)
        result = generate_measure_script(tmp_path)
        assert result["action"] == "unchanged"

    def test_written_content_matches_wrap_asset(self, tmp_path: Path) -> None:
        generate_measure_script(tmp_path)
        written = (tmp_path / MEASURE_PY_REL_PATH).read_text(encoding="utf-8")
        assert written == wrap_asset(MEASURE_PY_BODY, "measure-script", MEASURE_PY_REL_PATH)


class TestGenerateGitfactsScript:
    def test_creates_script_file(self, tmp_path: Path) -> None:
        generate_gitfacts_script(tmp_path)
        assert (tmp_path / GITFACTS_SH_REL_PATH).exists()

    def test_returns_created_action(self, tmp_path: Path) -> None:
        result = generate_gitfacts_script(tmp_path)
        assert result == {"file": GITFACTS_SH_REL_PATH, "action": "created"}

    def test_written_content_matches_wrap_asset(self, tmp_path: Path) -> None:
        generate_gitfacts_script(tmp_path)
        written = (tmp_path / GITFACTS_SH_REL_PATH).read_text(encoding="utf-8")
        assert written == wrap_asset(GITFACTS_SH_BODY, "gitfacts-script", GITFACTS_SH_REL_PATH)

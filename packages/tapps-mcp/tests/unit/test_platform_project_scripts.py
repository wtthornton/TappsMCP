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

    def test_gitfacts_body_differs_from_staged_source_by_documented_lines_only(self) -> None:
        """The only permitted deviations from the staged original:

        1. usage()'s self-read, made robust to the line-shift the managed-block
           wrapper introduces (documented in the module docstring and the PR body).
        2. TAP-7160: the SC2001 and SC2015 shellcheck findings fixed without
           changing behavior (also documented in the module docstring's deviation
           enumeration) -- see ``test_platform_project_scripts_shellcheck.py`` for
           the shellcheck-clean assertion, the pre-fix negative control that
           proves the checker actually caught these two lines, and the equivalent-
           output proof for the ``sed`` -> parameter-expansion rewrite.
        3. TAP-7160 (follow-up): a third SC2015 on the `usage()` argument guard
           (`[ -n "$CMD" ] && [ -n "$REPO" ] || usage`) that local shellcheck 0.11.0
           does not flag but CI's shellcheck does -- rewritten to an unambiguous
           `if`/`then` form so no `&&`...`||` chain remains for any shellcheck
           version to fire on.

        Reconstructs the expected body by applying exactly these documented
        substitutions to the staged fixture and asserts full equality -- any
        further, undocumented drift fails this test rather than the old
        length-mismatch AssertionError, which would have made TAP-7160's own
        fix look like a broken invariant instead of an intentional, catalogued one.
        """
        path = _FIXTURES_DIR / "src-gitfacts.sh.fixture"
        raw = path.read_text(encoding="utf-8")
        digest = hashlib.md5(raw.encode("utf-8"), usedforsecurity=False).hexdigest()
        assert digest == _GITFACTS_SH_STAGED_MD5

        usage_old = "usage() { sed -n '3,9p' \"${BASH_SOURCE[0]}\" >&2; exit 2; }"
        usage_new = "usage() { sed -n '/^# Usage:/,/^# *$/p' \"${BASH_SOURCE[0]}\" >&2; exit 2; }"
        assert usage_old in raw
        assert usage_new not in raw

        sc2001_old = '      echo "$flagged" | sed \'s/^/  /\'\n'
        sc2001_new = '      echo "  ${flagged//$\'\\n\'/$\'\\n\'  }"\n'
        assert sc2001_old in raw

        sc2015_old = (
            '    [ "$behind" -eq 0 ] && echo "VERDICT: current." || {\n'
            '      echo "VERDICT: STALE by $behind commit(s).'
            ' Any -S / grep / read here answers about old code."; }\n'
        )
        sc2015_new = (
            '    if [ "$behind" -eq 0 ]; then\n'
            '      echo "VERDICT: current."\n'
            "    else\n"
            '      echo "VERDICT: STALE by $behind commit(s).'
            ' Any -S / grep / read here answers about old code."\n'
            "    fi\n"
        )
        assert sc2015_old in raw

        guard_old = '[ -n "$CMD" ] && [ -n "$REPO" ] || usage'
        guard_new = 'if [ -z "$CMD" ] || [ -z "$REPO" ]; then usage; fi'
        assert guard_old in raw

        expected_body = (
            raw.replace(usage_old, usage_new)
            .replace(sc2001_old, sc2001_new)
            .replace(sc2015_old, sc2015_new)
            .replace(guard_old, guard_new)
        )
        assert expected_body == GITFACTS_SH_BODY


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

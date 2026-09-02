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


class TestSourceIsPortedFaithfully:
    """The staged sources are the contract — verify against their md5, not memory."""

    def test_measure_body_is_byte_identical_to_staged_source(self) -> None:
        source = Path("/tmp/src-measure.py").read_text(encoding="utf-8")
        assert source == MEASURE_PY_BODY

    def test_gitfacts_body_differs_from_staged_source_by_exactly_one_line(self) -> None:
        """The only permitted deviation: usage()'s self-read, made robust to the
        line-shift the managed-block wrapper introduces (documented in the
        module docstring and the PR body)."""
        source = Path("/tmp/src-gitfacts.sh").read_text(encoding="utf-8").splitlines()
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

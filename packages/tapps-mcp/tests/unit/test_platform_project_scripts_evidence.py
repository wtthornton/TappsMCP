"""Evidence-bar items 6 and 7 for the scaffolding mechanism itself (TAP-6884).

Split out from ``test_platform_project_scripts.py`` for gate size — see that
file's module docstring for why. Items 1-5 (the scripts' own functional
behavior) live in ``test_measure_script_behavior.py`` and
``test_gitfacts_script_behavior.py``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tapps_mcp.pipeline.platform_project_scripts import (
    GITFACTS_SH_REL_PATH,
    MEASURE_PY_REL_PATH,
    generate_gitfacts_script,
    generate_measure_script,
)


class TestEvidenceItem6LandsExecutableAndParses:
    """Both files land executable and parse, after tapps_init and again after
    tapps_upgrade — simulated as two successive writes (create, then refresh),
    the same two call sites init and upgrade wire (see
    ``test_platform_project_scripts_pipeline.py`` for the end-to-end proof)."""

    def _assert_executable_and_parses(self, tmp_path: Path) -> None:
        measure = tmp_path / MEASURE_PY_REL_PATH
        gitfacts = tmp_path / GITFACTS_SH_REL_PATH
        assert measure.stat().st_mode & 0o111, "measure.py is not executable"
        assert gitfacts.stat().st_mode & 0o111, "gitfacts.sh is not executable"

        py_result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(measure)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert py_result.returncode == 0, py_result.stderr

        sh_result = subprocess.run(
            ["bash", "-n", str(gitfacts)], capture_output=True, text=True, timeout=30
        )
        assert sh_result.returncode == 0, sh_result.stderr

    def test_after_first_write_init_like(self, tmp_path: Path) -> None:
        generate_measure_script(tmp_path)
        generate_gitfacts_script(tmp_path)
        self._assert_executable_and_parses(tmp_path)

    def test_after_second_write_upgrade_like(self, tmp_path: Path) -> None:
        generate_measure_script(tmp_path)
        generate_gitfacts_script(tmp_path)
        # Second pass is what tapps_upgrade does: refresh in place.
        result_m = generate_measure_script(tmp_path)
        result_g = generate_gitfacts_script(tmp_path)
        assert result_m["action"] == "unchanged"
        assert result_g["action"] == "unchanged"
        self._assert_executable_and_parses(tmp_path)


class TestEvidenceItem7ProjectContentSurvivesRefresh:
    """Project content written outside the managed-block markers survives a
    refresh — byte-for-byte, mirroring test_skill_asset_policy.py's coverage
    of the underlying mechanism, exercised here through the actual generator
    functions this lane registers."""

    def test_measure_py_project_addendum_survives_refresh(self, tmp_path: Path) -> None:
        generate_measure_script(tmp_path)
        target = tmp_path / MEASURE_PY_REL_PATH
        addendum = "\n# project note: do not delete, keep me\n"
        target.write_text(target.read_text(encoding="utf-8") + addendum, encoding="utf-8")

        generate_measure_script(tmp_path)
        text = target.read_text(encoding="utf-8")
        assert text.endswith(addendum)
        assert "project note: do not delete, keep me" in text

    def test_gitfacts_sh_project_addendum_survives_refresh(self, tmp_path: Path) -> None:
        generate_gitfacts_script(tmp_path)
        target = tmp_path / GITFACTS_SH_REL_PATH
        addendum = "\n# project note: do not delete, keep me\n"
        target.write_text(target.read_text(encoding="utf-8") + addendum, encoding="utf-8")

        generate_gitfacts_script(tmp_path)
        text = target.read_text(encoding="utf-8")
        assert text.endswith(addendum)
        assert "project note: do not delete, keep me" in text

"""Rendering test: emitted shell assets pass ``shellcheck`` cleanly (TAP-7160).

Covers ``GITFACTS_SH_BODY`` (:mod:`tapps_mcp.pipeline.platform_project_scripts`)
and ``START_PROGRAM_SCRIPT_BODY`` (:mod:`tapps_mcp.pipeline.platform_skill_orchestration`).

Three properties are asserted, not just "shellcheck exits 0":

1. **The checker is actually engaged.** A missing ``shellcheck`` binary must fail
   the test loudly (``pytest.fail``), never silently pass or skip — a missing
   binary exits non-zero/absent and would otherwise read as "no findings".
2. **The checker is not vacuously passing.** A hand-written positive-control
   script using a bash shebang plus a self-reassignment ``sed`` substitution
   (SC2001) and an arbitrary-command ``&&``/``||`` chain (SC2015) must be FLAGGED
   by the same invocation used to check the real bodies. Without this, a broken
   or misconfigured shellcheck invocation (e.g. wrong dialect, wrong severity)
   would certify a false green.
3. **Each real body is clean today, and was NOT clean before the fix** — a
   negative control renders the pre-fix ``gitfacts.sh`` body (reconstructed from
   the two exact defects this lane fixed) and asserts it reproduces the original
   two findings, proving the post-fix zero-findings result is not vacuous.

Severity is asserted at shellcheck's *default* severity (not ``-S warning``):
SC2001 is style and SC2015 is info, both of which vanish under a ``warning``
floor -- a test written against ``-S warning`` would pass even against the
unfixed bodies and would prove nothing.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tapps_mcp.pipeline.platform_project_scripts import GITFACTS_SH_BODY
from tapps_mcp.pipeline.platform_skill_orchestration import START_PROGRAM_SCRIPT_BODY

# The exact two lines this lane replaced, reconstructed here (not imported) so the
# negative control still exercises the pre-fix shape even after the source no longer
# contains it.
_PRE_FIX_GITFACTS_TAIL = r"""#!/usr/bin/env bash
set -euo pipefail
flagged="a
b"
behind=0
if [ -n "$flagged" ]; then
  echo "ASSUME-UNCHANGED FILES PRESENT -- 'git status' is blind to these:"
  echo "$flagged" | sed 's/^/  /'
fi
[ "$behind" -eq 0 ] && echo "VERDICT: current." || {
  echo "VERDICT: STALE by $behind commit(s). Any -S / grep / read here answers about old code."; }
"""

_POSITIVE_CONTROL = r"""#!/usr/bin/env bash
x=$(echo "$x" | sed 's/a/b/')
[ -n "$x" ] && foo || bar
"""


def _shellcheck_bin() -> str:
    binary = shutil.which("shellcheck")
    if not binary:
        pytest.fail(
            "shellcheck is not installed / not on PATH. This test must fail loudly "
            "rather than skip: a missing checker exits non-zero-or-absent and reads "
            "as 'no findings' otherwise. Install via `uv tool install shellcheck-py`."
        )
    return binary


def _run_shellcheck(body: str, tmp_path: Path, name: str) -> subprocess.CompletedProcess[str]:
    script_path = tmp_path / name
    script_path.write_text(body, encoding="utf-8")
    return subprocess.run(
        [_shellcheck_bin(), str(script_path)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_shellcheck_positive_control_is_flagged(tmp_path: Path) -> None:
    """Prove the checker is engaged: a hand-written bad script must be flagged.

    Without this, a broken invocation (wrong dialect selected by shebang, wrong
    severity floor) would certify every clean verdict below as a false green.
    """
    result = _run_shellcheck(_POSITIVE_CONTROL, tmp_path, "positive_control.sh")
    assert result.returncode == 1, (
        f"positive control did not trigger any findings -- the shellcheck probe "
        f"is broken: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "SC2001" in result.stdout
    assert "SC2015" in result.stdout


def test_gitfacts_sh_body_pre_fix_shape_is_flagged(tmp_path: Path) -> None:
    """Negative control: the pre-fix shape reproduces the original two findings."""
    result = _run_shellcheck(_PRE_FIX_GITFACTS_TAIL, tmp_path, "gitfacts_pre.sh")
    assert result.returncode == 1, (
        f"pre-fix reconstruction did not reproduce findings: stdout={result.stdout!r}"
    )
    assert "SC2001" in result.stdout
    assert "SC2015" in result.stdout


def test_gitfacts_sh_body_passes_shellcheck(tmp_path: Path) -> None:
    """Box 1: the rendered gitfacts.sh body reports zero shellcheck findings."""
    result = _run_shellcheck(GITFACTS_SH_BODY, tmp_path, "gitfacts.sh")
    assert result.returncode == 0, (
        f"gitfacts.sh body has shellcheck findings: stdout={result.stdout!r}"
    )
    assert result.stdout == ""


def test_start_program_sh_body_passes_shellcheck(tmp_path: Path) -> None:
    """Box 2: the rendered start-program.sh body reports zero shellcheck findings."""
    result = _run_shellcheck(START_PROGRAM_SCRIPT_BODY, tmp_path, "start-program.sh")
    assert result.returncode == 0, (
        f"start-program.sh body has shellcheck findings: stdout={result.stdout!r}"
    )
    assert result.stdout == ""

"""Tests for process inspection helpers (TAP-6893).

blue_green_proc.pids_referencing originally only checked exe/cwd, which is
blind to a release held via sys.path/argv -- exactly how the real dev-fleet
MCP servers hold their release dir (verified live: exe resolves to the
shared uv-managed CPython, cwd resolves to the operator's home dir, and the
release path is visible only in argv/cmdline and in the process's mapped
.so files under the release's site-packages).
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from tapps_mcp.distribution.blue_green_proc import pids_referencing


def test_pids_referencing_finds_argv_held_release_and_ignores_unrelated_dir(
    tmp_path: Path,
) -> None:
    """Both directions in one test -- a one-sided (empty-only) test is exactly
    what let the exe/cwd-only defect ship undetected."""
    release_dir = (tmp_path / "release-1.0.0-abc1234").resolve()
    release_dir.mkdir()
    unrelated_dir = (tmp_path / "unrelated").resolve()
    unrelated_dir.mkdir()

    # Real subprocess: exe is the system interpreter, cwd is tmp_path itself
    # (neither release_dir nor unrelated_dir) -- the release path is only
    # present in argv, mirroring the live server shape.
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)", str(release_dir)],
        cwd=str(tmp_path),
    )
    try:
        deadline = time.monotonic() + 10
        found: set[int] = set()
        while time.monotonic() < deadline:
            found = pids_referencing(release_dir)
            if proc.pid in found:
                break
            time.sleep(0.1)

        # Known-positive: the live process holding release_dir via argv is found.
        assert proc.pid in found, f"expected pid {proc.pid} in {found}"

        # Known-negative: an unrelated directory with nothing running from it
        # is not reported. This is the case the defective exe/cwd-only
        # function already passed -- asserting it alone would prove nothing.
        assert pids_referencing(unrelated_dir) == set()
    finally:
        proc.terminate()
        proc.wait(timeout=5)

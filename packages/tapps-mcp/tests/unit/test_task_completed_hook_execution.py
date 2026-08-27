"""TAP-6068 / VAL-18: end-to-end execution of the blocking Stop/TaskCompleted
hook templates against a hermetic scratch git repo.

These exercise the *rendered* shell scripts (not just their source text —
see ``test_hook_script_syntax.py`` for the bash -n pass) against real
scratch project roots under ``tmp_path``, mirroring the execution pattern
already used for ``tapps-pre-bash.sh`` in that file. Never touches this
repo's own ``.tapps-mcp/``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tapps_mcp.pipeline.platform_hook_templates import CLAUDE_HOOK_SCRIPTS_BLOCKING

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or sys.platform == "win32",
    reason="bash required",
)


def _init_scratch_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("# scratch\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)


def _run_hook(script_name: str, tmp_path: Path, *, payload: str = "{}") -> subprocess.CompletedProcess[str]:
    script_path = tmp_path / script_name
    script_path.write_text(CLAUDE_HOOK_SCRIPTS_BLOCKING[script_name], encoding="utf-8")
    return subprocess.run(
        ["bash", str(script_path)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=10,
        cwd=tmp_path,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)},
    )


class TestTaskCompletedHookCleanSession:
    """VAL-18: a scratch repo with no code changes must exit 0 honestly."""

    def test_no_marker_no_changes_exits_zero(self, tmp_path: Path) -> None:
        _init_scratch_repo(tmp_path)
        proc = _run_hook("tapps-task-completed.sh", tmp_path)
        assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"
        assert "OK" in proc.stderr

    def test_stop_hook_no_marker_no_changes_exits_zero(self, tmp_path: Path) -> None:
        _init_scratch_repo(tmp_path)
        proc = _run_hook("tapps-stop.sh", tmp_path, payload='{"stop_hook_active": false}')
        assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"

    def test_stale_marker_no_changes_exits_zero(self, tmp_path: Path) -> None:
        """The no-scorable-changes check runs before the marker is even
        inspected, so a stale marker with nothing to validate is still an
        honest pass — see test_stale_marker_with_scorable_change_blocks for
        the case where staleness actually matters."""
        _init_scratch_repo(tmp_path)
        marker_dir = tmp_path / ".tapps-mcp"
        marker_dir.mkdir()
        (marker_dir / ".validation-marker").write_text(str(time.time() - 7200), encoding="utf-8")
        proc = _run_hook("tapps-task-completed.sh", tmp_path)
        assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"
        assert "OK" in proc.stderr


class TestTaskCompletedHookStillBlocks:
    """Genuinely unvalidated scorable changes must still block (item 2)."""

    def test_no_marker_with_scorable_change_blocks(self, tmp_path: Path) -> None:
        _init_scratch_repo(tmp_path)
        (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
        proc = _run_hook("tapps-task-completed.sh", tmp_path)
        assert proc.returncode == 2, f"stdout={proc.stdout}\nstderr={proc.stderr}"
        assert "BLOCKED" in proc.stderr

    def test_stale_marker_with_scorable_change_blocks(self, tmp_path: Path) -> None:
        _init_scratch_repo(tmp_path)
        (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
        marker_dir = tmp_path / ".tapps-mcp"
        marker_dir.mkdir()
        (marker_dir / ".validation-marker").write_text(str(time.time() - 7200), encoding="utf-8")
        proc = _run_hook("tapps-task-completed.sh", tmp_path)
        assert proc.returncode == 2, f"stdout={proc.stdout}\nstderr={proc.stderr}"
        assert "stale" in proc.stderr.lower()

    def test_stop_hook_no_marker_with_scorable_change_blocks(self, tmp_path: Path) -> None:
        _init_scratch_repo(tmp_path)
        (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
        proc = _run_hook("tapps-stop.sh", tmp_path, payload='{"stop_hook_active": false}')
        assert proc.returncode == 2, f"stdout={proc.stdout}\nstderr={proc.stderr}"
        assert "BLOCKED" in proc.stderr

    def test_fresh_marker_still_passes(self, tmp_path: Path) -> None:
        """Sanity: a fresh marker (the honest all-gates-passed case) is unaffected."""
        _init_scratch_repo(tmp_path)
        (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
        marker_dir = tmp_path / ".tapps-mcp"
        marker_dir.mkdir()
        (marker_dir / ".validation-marker").write_text(str(time.time()), encoding="utf-8")
        proc = _run_hook("tapps-task-completed.sh", tmp_path)
        assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"

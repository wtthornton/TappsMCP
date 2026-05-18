"""Smoke tests for the post-merge hook (TAP-2130).

The hook auto-runs ``uv sync --all-packages`` after a merge that touches
pyproject.toml / packages/*/pyproject.toml / uv.lock, so the project venv
stays in lockstep with the merged tree. These tests follow the pattern
established by ``test_pre_push_hook_pipefail.py``: assert on hook *source*
for structure, plus one subprocess smoke test for the bypass path.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

HOOK_PATH = Path(__file__).resolve().parents[4] / ".githooks" / "post-merge"


@pytest.fixture(scope="module")
def hook_source() -> str:
    assert HOOK_PATH.exists(), f"post-merge hook missing at {HOOK_PATH}"
    return HOOK_PATH.read_text(encoding="utf-8")


def test_hook_is_executable() -> None:
    assert os.access(HOOK_PATH, os.X_OK), f"{HOOK_PATH} must be chmod +x"


def test_hook_sets_strict_bash(hook_source: str) -> None:
    """``set -euo pipefail`` is the safety floor for any shell hook."""
    assert "set -euo pipefail" in hook_source


def test_hook_handles_bypass_env_var(hook_source: str) -> None:
    """TAPPS_SKIP_POSTMERGE=1 must short-circuit before invoking uv."""
    assert "TAPPS_SKIP_POSTMERGE" in hook_source


def test_hook_logs_bypass_to_jsonl(hook_source: str) -> None:
    """Bypass log parity with the pre-push hook (.tapps-mcp/.bypass-log.jsonl)."""
    assert ".tapps-mcp" in hook_source
    assert ".bypass-log.jsonl" in hook_source


def test_hook_detects_dependency_file_changes(hook_source: str) -> None:
    """Sync trigger must include pyproject.toml + packages/*/pyproject.toml + uv.lock."""
    assert "pyproject.toml" in hook_source
    assert "packages/*/pyproject.toml" in hook_source
    assert "uv.lock" in hook_source


def test_hook_calls_uv_sync_all_packages(hook_source: str) -> None:
    """The sync invocation must cover all workspace members."""
    assert "uv sync --all-packages" in hook_source


def test_hook_uses_orig_head_for_diff(hook_source: str) -> None:
    """ORIG_HEAD vs HEAD is the standard pre-merge / post-merge diff base."""
    assert "ORIG_HEAD" in hook_source
    assert "HEAD" in hook_source


def test_bypass_env_short_circuits(tmp_path: Path) -> None:
    """Invoke the hook with TAPPS_SKIP_POSTMERGE=1 in a tmp git repo;
    expect exit 0, log entry written, no uv subprocess invoked.
    """
    subprocess.run(
        ["git", "init", "-q"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "--allow-empty", "-q", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    env = {**os.environ, "TAPPS_SKIP_POSTMERGE": "1"}
    result = subprocess.run(
        ["bash", str(HOOK_PATH)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, f"hook should exit 0 on bypass; stderr={result.stderr}"
    assert "TAPPS_SKIP_POSTMERGE" in result.stderr
    log = tmp_path / ".tapps-mcp" / ".bypass-log.jsonl"
    assert log.exists(), "bypass log file must be written"
    assert "TAPPS_SKIP_POSTMERGE=1" in log.read_text()

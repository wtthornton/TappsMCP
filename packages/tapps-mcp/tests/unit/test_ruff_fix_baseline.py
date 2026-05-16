"""TAP-1789: run_ruff_fix must capture the pre-fix baseline before fixing.

The previous sync implementation ran ``ruff check --fix`` first and used its
output (which is the *remaining* post-fix issues) as the baseline. Both runs
then saw the file in the same already-fixed state and ``len(before) - len(after)``
was always 0.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

from tapps_mcp.tools.ruff import run_ruff_fix


class _FakeCommandResult:
    """Mimics the subset of ``run_command``'s return shape ruff.py reads."""

    def __init__(self, stdout: str = "", success: bool = True) -> None:
        self.stdout = stdout
        self.success = success


def _issue(code: str = "F401") -> dict[str, Any]:
    return {"code": code, "message": "ignored", "location": {}}


def test_run_ruff_fix_counts_diff_between_pre_fix_and_post_fix() -> None:
    """before=2, after=0 → fixes_applied=2 (the common case)."""
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], *, cwd: Any = None, timeout: int = 30) -> _FakeCommandResult:
        calls.append(cmd)
        if "--fix" in cmd and "--output-format=json" not in cmd:
            # The actual fix invocation — no JSON requested.
            return _FakeCommandResult(stdout="", success=True)
        if "--fix" in cmd:
            # Legacy combined call — should NOT happen post-fix.
            return _FakeCommandResult(stdout=json.dumps([]), success=True)
        # Read-only check; first call returns the pre-fix baseline, second the empty after.
        if calls.count(cmd) == 1:
            return _FakeCommandResult(stdout=json.dumps([_issue("F401"), _issue("E501")]))
        return _FakeCommandResult(stdout=json.dumps([]))

    with patch("tapps_mcp.tools.ruff.run_command", side_effect=fake_run):
        n = run_ruff_fix("/tmp/sample.py")

    # 3 sub-calls: pre-fix read, fix, post-fix read
    assert len(calls) == 3
    assert "--fix" not in calls[0], "pre-fix baseline must NOT pass --fix"
    assert "--fix" in calls[1], "second call must perform the fix"
    assert "--fix" not in calls[2], "post-fix verification must NOT pass --fix"
    assert n == 2


def test_run_ruff_fix_clean_file_reports_zero() -> None:
    """before=0, after=0 → fixes_applied=0."""
    def fake_run(cmd: list[str], *, cwd: Any = None, timeout: int = 30) -> _FakeCommandResult:
        return _FakeCommandResult(stdout=json.dumps([]))

    with patch("tapps_mcp.tools.ruff.run_command", side_effect=fake_run):
        assert run_ruff_fix("/tmp/clean.py") == 0


def test_run_ruff_fix_clamps_negative_to_zero() -> None:
    """Defensive: if after > before (concurrent edit, ruff config drift), clamp."""
    outputs = [
        _FakeCommandResult(stdout=json.dumps([_issue()])),       # before: 1 issue
        _FakeCommandResult(stdout="", success=True),             # fix
        _FakeCommandResult(stdout=json.dumps([_issue(), _issue()])),  # after: 2 issues
    ]
    it = iter(outputs)

    def fake_run(*_args: Any, **_kwargs: Any) -> _FakeCommandResult:
        return next(it)

    with patch("tapps_mcp.tools.ruff.run_command", side_effect=fake_run):
        assert run_ruff_fix("/tmp/weird.py") == 0


def test_run_ruff_fix_handles_invalid_json_baseline() -> None:
    """Bad JSON from ruff is treated as zero issues, not a crash."""
    outputs = [
        _FakeCommandResult(stdout="garbage not json"),
        _FakeCommandResult(stdout="", success=True),
        _FakeCommandResult(stdout=json.dumps([])),
    ]
    it = iter(outputs)

    def fake_run(*_args: Any, **_kwargs: Any) -> _FakeCommandResult:
        return next(it)

    with patch("tapps_mcp.tools.ruff.run_command", side_effect=fake_run):
        assert run_ruff_fix("/tmp/maybe.py") == 0

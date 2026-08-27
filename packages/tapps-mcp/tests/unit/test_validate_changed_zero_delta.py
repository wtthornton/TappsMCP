"""TAP-6068: pre-existing debt (zero-delta) detection for validate_changed.

A batch that only fails on files byte-identical to their content on trunk
is pre-existing debt the session never touched — distinguishable from a
fresh regression so Stop/TaskCompleted hooks don't block a session for
debt it didn't introduce. See ``only_pre_existing_debt_failed`` in
``validate_changed_output._build_response_data`` and the per-file
``zero_delta`` flag in ``_build_file_entry``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tapps_mcp.tools.validate_changed import _BatchContext, _finalize_outcome, _TimedOutInfo
from tapps_mcp.tools.validate_changed_collection import (
    _annotate_zero_delta_failures,
    _is_zero_delta_against_trunk,
)
from tapps_mcp.tools.validate_changed_output import _only_pre_existing_debt_failed


def _init_repo_with_file(tmp_path: Path, name: str, content: str) -> Path:
    """Create a hermetic scratch git repo with one committed file on ``main``."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    f = tmp_path / name
    f.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    subprocess.run(["git", "branch", "-M", "main"], cwd=tmp_path, check=True)
    return f


class TestIsZeroDeltaAgainstTrunk:
    def test_unchanged_file_is_zero_delta(self, tmp_path: Path) -> None:
        f = _init_repo_with_file(tmp_path, "debt.py", "x = 1\n")
        assert _is_zero_delta_against_trunk(tmp_path, str(f)) is True

    def test_modified_file_is_not_zero_delta(self, tmp_path: Path) -> None:
        f = _init_repo_with_file(tmp_path, "debt.py", "x = 1\n")
        f.write_text("x = 2\n", encoding="utf-8")
        assert _is_zero_delta_against_trunk(tmp_path, str(f)) is False

    def test_new_untracked_file_is_not_zero_delta(self, tmp_path: Path) -> None:
        _init_repo_with_file(tmp_path, "debt.py", "x = 1\n")
        new_file = tmp_path / "new.py"
        new_file.write_text("y = 1\n", encoding="utf-8")
        assert _is_zero_delta_against_trunk(tmp_path, str(new_file)) is False

    def test_no_git_repo_fails_closed(self, tmp_path: Path) -> None:
        f = tmp_path / "solo.py"
        f.write_text("x = 1\n", encoding="utf-8")
        assert _is_zero_delta_against_trunk(tmp_path, str(f)) is False


class TestAnnotateZeroDeltaFailures:
    def test_all_failures_zero_delta_returns_true(self, tmp_path: Path) -> None:
        f = _init_repo_with_file(tmp_path, "debt.py", "x = 1\n")
        results = [{"file_path": str(f), "gate_passed": False}]
        only_debt = _annotate_zero_delta_failures(results, tmp_path)
        assert only_debt is True
        assert results[0]["zero_delta"] is True

    def test_mixed_failures_returns_false(self, tmp_path: Path) -> None:
        f = _init_repo_with_file(tmp_path, "debt.py", "x = 1\n")
        new_file = tmp_path / "new.py"
        new_file.write_text("y = 1\n", encoding="utf-8")
        results = [
            {"file_path": str(f), "gate_passed": False},
            {"file_path": str(new_file), "gate_passed": False},
        ]
        only_debt = _annotate_zero_delta_failures(results, tmp_path)
        assert only_debt is False
        assert results[0]["zero_delta"] is True
        assert results[1]["zero_delta"] is False

    def test_no_failures_returns_false(self, tmp_path: Path) -> None:
        results = [{"file_path": "x.py", "gate_passed": True}]
        assert _annotate_zero_delta_failures(results, tmp_path) is False


class TestFinalizeOutcomeZeroDeltaDebt:
    def _make_bc(self, tmp_path: Path, path: Path) -> _BatchContext:
        return _BatchContext(
            file_paths=str(path),
            base_ref="HEAD",
            preset="standard",
            include_security=False,
            quick=True,
            security_depth="basic",
            include_impact=False,
            correlation_id="",
            judges=None,
            ctx=None,
            start=0,
            settings=SimpleNamespace(project_root=tmp_path),
            paths=[path],
            capped=False,
            extra_count=0,
            tracker=MagicMock(),
            auto_detect=False,
            cached_results=[],
            uncached_paths=[path],
        )

    @pytest.mark.asyncio
    async def test_marker_written_when_only_debt_failed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        f = _init_repo_with_file(tmp_path, "debt.py", "x = 1\n")
        monkeypatch.setattr("tapps_mcp.server._record_call", lambda *a, **k: None)
        monkeypatch.setattr("tapps_mcp.server._record_execution", lambda *a, **k: None)
        wrote: dict[str, Path] = {}
        monkeypatch.setattr(
            "tapps_mcp.server_pipeline_tools._write_validate_ok_marker",
            lambda root: wrote.setdefault("root", root),
        )
        bc = self._make_bc(tmp_path, f)
        outcome = await _finalize_outcome(
            bc,
            [{"file_path": str(f), "gate_passed": False, "security_issues": 0}],
            _TimedOutInfo(),
        )
        assert outcome.all_passed is False
        assert outcome.results[0]["zero_delta"] is True
        assert _only_pre_existing_debt_failed(outcome.results) is True
        assert wrote.get("root") == tmp_path

    @pytest.mark.asyncio
    async def test_marker_not_written_when_fresh_failure(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _init_repo_with_file(tmp_path, "debt.py", "x = 1\n")
        new_file = tmp_path / "new.py"
        new_file.write_text("y = 1\n", encoding="utf-8")
        monkeypatch.setattr("tapps_mcp.server._record_call", lambda *a, **k: None)
        monkeypatch.setattr("tapps_mcp.server._record_execution", lambda *a, **k: None)
        monkeypatch.setattr(
            "tapps_mcp.server_pipeline_tools._write_validate_ok_marker",
            lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not write marker")),
        )
        bc = self._make_bc(tmp_path, new_file)
        outcome = await _finalize_outcome(
            bc,
            [{"file_path": str(new_file), "gate_passed": False, "security_issues": 0}],
            _TimedOutInfo(),
        )
        assert outcome.all_passed is False
        assert outcome.results[0]["zero_delta"] is False
        assert _only_pre_existing_debt_failed(outcome.results) is False

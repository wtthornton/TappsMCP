"""TAP-1414: tapps_session_start surfaces ruff/mypy missing as a loud warning.

Audit data: BambuStudio's tool-versions.json showed ruff and mypy both
``available: false``, but tapps_session_start returned success with no
surfaced warning. Agents only learned the quality gate was running degraded
by inspecting the cache file — by which point they'd already shipped.

These tests pin the new contract:

- Python project (pyproject.toml present) + ruff/mypy missing → response
  carries top-level ``degraded_checkers`` and a warning in ``next_steps``.
- Non-Python project + ruff/mypy missing → silent (no warning, no field).
- Python project + all checkers present → silent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tapps_mcp.tools.session_start_core import compute_python_degraded_checkers


def _checker(name: str, *, available: bool) -> dict[str, object]:
    return {"name": name, "available": available, "version": None, "install_hint": None}


class TestComputePythonDegradedCheckers:
    """Unit tests for the compute_python_degraded_checkers helper."""

    def test_python_project_with_ruff_and_mypy_missing_warns(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
        checkers = [
            _checker("ruff", available=False),
            _checker("mypy", available=False),
            _checker("bandit", available=True),
        ]
        degraded, warning = compute_python_degraded_checkers(tmp_path, checkers)

        assert degraded == ["ruff", "mypy"]
        assert warning is not None
        assert "ruff and mypy are missing" in warning
        assert "uv tool install tapps-mcp --with ruff --with mypy" in warning

    def test_python_project_with_only_ruff_missing_warns(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
        checkers = [
            _checker("ruff", available=False),
            _checker("mypy", available=True),
        ]
        degraded, warning = compute_python_degraded_checkers(tmp_path, checkers)

        assert degraded == ["ruff"]
        assert warning is not None
        assert "ruff is missing" in warning

    def test_python_project_with_all_checkers_present_silent(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
        checkers = [
            _checker("ruff", available=True),
            _checker("mypy", available=True),
        ]
        degraded, warning = compute_python_degraded_checkers(tmp_path, checkers)

        assert degraded == []
        assert warning is None

    def test_non_python_project_silent_even_when_missing(self, tmp_path: Path) -> None:
        # No pyproject.toml, no setup.py, no .py files. ruff/mypy missing is
        # irrelevant for, say, a Node project.
        checkers = [
            _checker("ruff", available=False),
            _checker("mypy", available=False),
        ]
        degraded, warning = compute_python_degraded_checkers(tmp_path, checkers)

        assert degraded == []
        assert warning is None

    def test_loose_python_files_count_as_python_project(self, tmp_path: Path) -> None:
        (tmp_path / "script.py").write_text("print('x')\n")
        checkers = [_checker("ruff", available=False), _checker("mypy", available=False)]
        degraded, warning = compute_python_degraded_checkers(tmp_path, checkers)

        assert degraded == ["ruff", "mypy"]
        assert warning is not None

    def test_setup_py_counts_as_python_project(self, tmp_path: Path) -> None:
        (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup()\n")
        checkers = [_checker("ruff", available=False), _checker("mypy", available=True)]
        degraded, warning = compute_python_degraded_checkers(tmp_path, checkers)

        assert degraded == ["ruff"]
        assert warning is not None

    def test_object_checker_entries_handled(self, tmp_path: Path) -> None:
        """The helper should accept InstalledTool model instances too."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")

        class _Stub:
            def __init__(self, name: str, available: bool) -> None:
                self.name = name
                self.available = available

        checkers = [_Stub("ruff", False), _Stub("mypy", False)]
        degraded, warning = compute_python_degraded_checkers(tmp_path, checkers)

        assert degraded == ["ruff", "mypy"]
        assert warning is not None

    def test_bandit_radon_missing_does_not_trigger(self, tmp_path: Path) -> None:
        """Only ruff/mypy are critical — bandit/radon missing is silent."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
        checkers = [
            _checker("ruff", available=True),
            _checker("mypy", available=True),
            _checker("bandit", available=False),
            _checker("radon", available=False),
        ]
        degraded, warning = compute_python_degraded_checkers(tmp_path, checkers)

        assert degraded == []
        assert warning is None


class TestPrependNextStep:
    """Verify the helper that injects warnings into a wrapped response."""

    def test_prepends_to_existing_next_steps(self) -> None:
        from tapps_mcp.server_pipeline_tools import _prepend_next_step

        resp: dict[str, object] = {
            "success": True,
            "data": {"next_steps": ["NEXT: do something else"]},
        }
        _prepend_next_step(resp, "WARNING: degraded")

        data = resp["data"]
        assert isinstance(data, dict)
        assert data["next_steps"] == ["WARNING: degraded", "NEXT: do something else"]

    def test_creates_next_steps_when_missing(self) -> None:
        from tapps_mcp.server_pipeline_tools import _prepend_next_step

        resp: dict[str, object] = {"success": True, "data": {}}
        _prepend_next_step(resp, "WARNING: degraded")

        data = resp["data"]
        assert isinstance(data, dict)
        assert data["next_steps"] == ["WARNING: degraded"]

    def test_idempotent_when_already_present(self) -> None:
        from tapps_mcp.server_pipeline_tools import _prepend_next_step

        resp: dict[str, object] = {
            "success": True,
            "data": {"next_steps": ["WARNING: degraded", "other"]},
        }
        _prepend_next_step(resp, "WARNING: degraded")

        data = resp["data"]
        assert isinstance(data, dict)
        assert data["next_steps"] == ["WARNING: degraded", "other"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Tests for scripts/measure_context_floor.py -- the context-floor CLI.

TAP-7770: ``scripts/measure_context_floor.py --skills`` used to exit 1 and print no
skills numbers whenever the (unrelated) tools bucket failed to resolve a registration.
This is the deterministic VAL for the fix: the CLI at this exact path must exit 0 and
print the skills numbers even while the tools bucket is broken, and a failed bucket
must be visibly reported rather than silently dropped.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = REPO_ROOT / "scripts"
SCRIPT_PATH = SCRIPTS_DIR / "measure_context_floor.py"


@pytest.fixture(scope="module", autouse=True)
def _scripts_on_path() -> None:
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture(scope="module")
def cli_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("measure_context_floor", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["measure_context_floor"] = module
    spec.loader.exec_module(module)
    return module


class TestSkillsExecutionPath:
    """Execution-path proof: invoke the real, pinned script path as a subprocess,
    exactly as a user would -- not an in-process import of some other copy."""

    def test_skills_flag_exits_zero_and_prints_skills(self) -> None:
        assert SCRIPT_PATH.is_file(), f"pinned path does not exist: {SCRIPT_PATH}"
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--skills"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert "skills," in result.stdout
        assert "session_start_impl" not in result.stdout
        assert "session_start_impl" not in result.stderr


class TestPrintTableBucketTolerance:
    def test_print_table_renders_failed_bucket_without_crashing(
        self, cli_module: ModuleType, capsys: pytest.CaptureFixture[str]
    ) -> None:
        report: dict[str, Any] = {
            "tool_schema_tokens": None,
            "tool_docstring_tokens": None,
            "tool_param_tokens": None,
            "tool_count": None,
            "skill_description_tokens": 1938,
            "always_loaded_rule_tokens": 10438,
            "claude_md_tokens": 3914,
            "server_instruction_tokens": 2193,
            "session_start_tokens": 574,
            "floor_tokens": None,
            "bucket_errors": {"tools": "boom"},
            "detail": {"tools": {"error": "boom"}},
        }
        cli_module.print_table(report)
        out = capsys.readouterr().out
        assert "FAILED" in out
        assert "10,438" in out

    def test_print_skills_table_reports_failure_to_stderr_without_crashing(
        self, cli_module: ModuleType, capsys: pytest.CaptureFixture[str]
    ) -> None:
        report: dict[str, Any] = {"detail": {"skills": {"error": "boom"}}}
        cli_module.print_skills_table(report)
        captured = capsys.readouterr()
        assert captured.err
        assert captured.out == ""

    def test_print_bucket_errors_writes_to_stderr(
        self, cli_module: ModuleType, capsys: pytest.CaptureFixture[str]
    ) -> None:
        report: dict[str, Any] = {"bucket_errors": {"tools": "boom"}}
        cli_module._print_bucket_errors(report)
        captured = capsys.readouterr()
        assert "[FAILED] tools bucket: boom" in captured.err
        assert captured.out == ""

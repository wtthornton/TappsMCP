"""Tests for scripts/context_floor_report.py -- bucket-tolerant report assembly.

TAP-7770: a ``MeasurementError`` raised by any one ``context_floor_*`` bucket used to
abort ``build_report()`` entirely, discarding buckets that measured successfully (the
skills bucket, in the reported case). ``build_report()`` now measures each bucket
independently: a failed bucket is recorded in ``bucket_errors`` and its ``detail`` entry
becomes ``{"error": ...}``, while every other bucket's numbers still come through.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = REPO_ROOT / "scripts"


@pytest.fixture(scope="module", autouse=True)
def _scripts_on_path() -> None:
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture(scope="module")
def report_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "context_floor_report", SCRIPTS_DIR / "context_floor_report.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["context_floor_report"] = module
    spec.loader.exec_module(module)
    return module


class TestBuildReportBucketTolerance:
    def test_tools_bucket_failure_does_not_suppress_skills_bucket(
        self, report_module: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _broken_measure_tools() -> None:
            raise report_module.MeasurementError("DELIBERATE-BREAK-FOR-TEST")

        monkeypatch.setattr(report_module, "measure_tools", _broken_measure_tools)

        report = report_module.build_report()

        assert report["bucket_errors"] == {"tools": "DELIBERATE-BREAK-FOR-TEST"}
        assert report["detail"]["tools"] == {"error": "DELIBERATE-BREAK-FOR-TEST"}
        assert report["tool_schema_tokens"] is None
        assert report["tool_docstring_tokens"] is None
        assert report["tool_param_tokens"] is None
        assert report["tool_count"] is None

        # The skills bucket -- and every other bucket -- still measured.
        assert report["skill_description_tokens"] is not None
        assert report["skill_description_tokens"] > 0
        assert isinstance(report["detail"]["skills"], list)
        assert len(report["detail"]["skills"]) > 0
        assert report["always_loaded_rule_tokens"] is not None
        assert report["claude_md_tokens"] is not None
        assert report["server_instruction_tokens"] is not None
        assert report["session_start_tokens"] is not None

    def test_a_failed_bucket_makes_floor_tokens_none_not_wrong(
        self, report_module: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """floor_tokens sums every bucket -- a bucket silently treated as 0 would
        under-report the floor. It must be None (visibly incomplete) instead."""

        def _broken_measure_tools() -> None:
            raise report_module.MeasurementError("boom")

        monkeypatch.setattr(report_module, "measure_tools", _broken_measure_tools)

        report = report_module.build_report()

        assert report["floor_tokens"] is None

    def test_no_bucket_failure_means_no_bucket_errors(
        self, report_module: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When every bucket measures cleanly, floor_tokens is a real sum and
        bucket_errors is empty."""

        class _StubToolsResult:
            tool_count = 3
            docstring_bytes = 120
            param_bytes = 60
            tools: list[object] = []
            docstrings_over_400_bytes = 0

        monkeypatch.setattr(report_module, "measure_tools", lambda: _StubToolsResult())

        report = report_module.build_report()

        assert report["bucket_errors"] == {}
        assert report["tool_count"] == 3
        assert report["floor_tokens"] is not None
        assert "error" not in report["detail"]["tools"]

    def test_session_start_impl_is_not_the_failure_reason(
        self, report_module: ModuleType
    ) -> None:
        """TAP-7770's specific named defect: against the real tree, if the tools
        bucket fails it must not be because of the "session_start_impl" symbol --
        that name resolution bug is fixed (see test_context_floor_tools.py)."""
        report = report_module.build_report()
        tools_error = report["bucket_errors"].get("tools", "")
        assert "session_start_impl" not in tools_error

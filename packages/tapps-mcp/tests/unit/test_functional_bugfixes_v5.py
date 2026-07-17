"""Regression tests for the v5 functional bugfix batch."""

from __future__ import annotations

import ast
import math
from pathlib import Path
from textwrap import dedent
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tapps_core.metrics.execution_metrics import ToolCallMetric, ToolCallMetricsCollector
from tapps_core.metrics.trends import calculate_trend
from tapps_mcp.common.cache_paths import resolve_kb_cache_dir
from tapps_mcp.common.elicitation import PresetElicitation
from tapps_mcp.project.import_graph import _is_tc_guard, resolve_relative_import
from tapps_mcp.scoring.cross_ref import _extract_function_params, analyze_cross_references
from tapps_mcp.tools.batch_validator import format_batch_summary
from tapps_mcp.tools.checklist import _check_compile_time_red
from tapps_mcp.tools.loop_metrics import loop_row_gate_skipped
from tapps_mcp.tools.mypy import parse_mypy_output
from tapps_mcp.tools.ruff import parse_ruff_json
from tapps_mcp.tools.usage import append_call_graph_stop_followup
from tapps_mcp.tools.validate_changed import _BatchContext, _TimedOutInfo, _finalize_outcome


class TestMypyWindowsDrivePaths:
    def test_drive_letter_path_is_parsed(self) -> None:
        raw = r"C:\Users\dev\proj\src\foo.py:10: error: Incompatible types [assignment]"
        issues = parse_mypy_output(raw)
        assert len(issues) == 1
        assert issues[0].line == 10
        assert issues[0].file.lower().endswith("foo.py")


class TestRuffParseFailure:
    def test_garbage_json_is_none_not_clean(self) -> None:
        assert parse_ruff_json("{not json") is None


class TestTypeCheckingBoolOp:
    def test_and_guard_is_type_checking(self) -> None:
        tree = ast.parse("if TYPE_CHECKING and sys.version_info >= (3, 12):\n    pass\n")
        assert isinstance(tree.body[0], ast.If)
        assert _is_tc_guard(tree.body[0].test) is True


class TestRelativeImportEscape:
    def test_over_deep_relative_returns_empty(self) -> None:
        assert resolve_relative_import("pkg.mod", "x", level=5) == ""


class TestCrossRefClassMethod:
    def test_resolves_correct_class_method(self, tmp_path: Path) -> None:
        callee = tmp_path / "mod.py"
        callee.write_text(
            dedent(
                """\
                class A:
                    def process(self, x: int) -> None:
                        pass

                class B:
                    def process(self, y: int, z: int) -> None:
                        pass
                """
            ),
            encoding="utf-8",
        )
        caller = tmp_path / "caller.py"
        caller.write_text(
            dedent(
                """\
                from mod import B

                def run() -> None:
                    B.process(y=1, z=2)
                """
            ),
            encoding="utf-8",
        )
        result = analyze_cross_references(caller, project_root=tmp_path)
        assert result.findings == []

        tree = ast.parse(callee.read_text(encoding="utf-8"))
        assert _extract_function_params(tree, "process", class_name="B") == ["y", "z"]
        assert _extract_function_params(tree, "process", class_name="A") == ["x"]


class TestTrendsPolarity:
    def test_latency_decrease_is_improving(self) -> None:
        trend = calculate_trend("avg_latency_ms", [100.0, 80.0, 60.0, 40.0])
        assert trend.direction == "improving"

    def test_error_rate_increase_is_degrading(self) -> None:
        trend = calculate_trend("error_rate", [0.01, 0.05, 0.1, 0.2])
        assert trend.direction == "degrading"

    def test_score_increase_is_improving(self) -> None:
        trend = calculate_trend("avg_score", [1.0, 2.0, 3.0, 4.0])
        assert trend.direction == "improving"


class TestCallGraphStopFollowup:
    def test_validate_changed_does_not_suppress_nudge(self, tmp_path: Path) -> None:
        from tapps_mcp.project.call_graph_cache import save_call_graph_index
        from tapps_mcp.project.call_graph_types import INDEX_VERSION, CallGraphIndex

        save_call_graph_index(
            tmp_path,
            CallGraphIndex(
                project_root=str(tmp_path),
                fingerprint="stale-fingerprint",
                version=INDEX_VERSION,
            ),
        )
        followup = append_call_graph_stop_followup(
            None,
            tmp_path,
            files_edited=["src/a.ts"],
            called_tools={"tapps_validate_changed"},
        )
        assert followup is not None
        assert "stale" in followup.lower()


class TestPresetElicitationAlignment:
    def test_enum_matches_real_presets(self) -> None:
        extra = PresetElicitation.model_fields["preset"].json_schema_extra
        assert extra is not None
        assert extra["enum"] == ["standard", "strict", "framework"]


class TestLoopMetricsGateSkipped:
    def test_checklist_alone_does_not_count_as_gate(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.py").write_text("x = 1\n", encoding="utf-8")
        row = {
            "files_edited": ["src/a.py"],
            "tools_used": [],
            "checklist_called": True,
            "gate_skipped_files": [],
        }
        assert loop_row_gate_skipped(row, tmp_path) is True


class TestFormatBatchSummary:
    def test_none_gate_passed_counts_as_failed(self) -> None:
        summary = format_batch_summary(
            [
                {"gate_passed": True, "security_issues": 0},
                {"gate_passed": None, "security_issues": 0},
                {"security_issues": 0},
            ]
        )
        assert "1 passed gate" in summary
        assert "2 failed gate" in summary


class TestValidateChangedIncomplete:
    @pytest.mark.asyncio()
    async def test_timeout_forces_fail(self, monkeypatch: object, tmp_path: Path) -> None:
        monkeypatch.setattr(
            "tapps_mcp.server._record_call",
            lambda *a, **k: None,
        )
        monkeypatch.setattr(
            "tapps_mcp.server._record_execution",
            lambda *a, **k: None,
        )
        monkeypatch.setattr(
            "tapps_mcp.server_pipeline_tools._write_validate_ok_marker",
            lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not write marker")),
        )
        bc = _BatchContext(
            file_paths="",
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
            paths=[],
            capped=False,
            extra_count=0,
            tracker=MagicMock(),
            auto_detect=True,
            cached_results=[],
            uncached_paths=[],
        )
        timeout = _TimedOutInfo(
            timed_out=True,
            files_remaining=[tmp_path / "a.py", tmp_path / "b.py"],
        )
        outcome = await _finalize_outcome(
            bc,
            [{"gate_passed": True, "security_issues": 0}],
            timeout,
        )
        assert outcome.all_passed is False

    @pytest.mark.asyncio()
    async def test_cap_forces_fail(self, monkeypatch: object, tmp_path: Path) -> None:
        monkeypatch.setattr("tapps_mcp.server._record_call", lambda *a, **k: None)
        monkeypatch.setattr("tapps_mcp.server._record_execution", lambda *a, **k: None)
        wrote = {"marker": False}

        def _mark(_root: Path) -> None:
            wrote["marker"] = True

        monkeypatch.setattr(
            "tapps_mcp.server_pipeline_tools._write_validate_ok_marker",
            _mark,
        )
        bc = _BatchContext(
            file_paths="a.py",
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
            paths=[],
            capped=True,
            extra_count=3,
            tracker=MagicMock(),
            auto_detect=False,
            cached_results=[],
            uncached_paths=[],
        )
        outcome = await _finalize_outcome(
            bc,
            [{"gate_passed": True, "security_issues": 0}],
            _TimedOutInfo(),
        )
        assert outcome.all_passed is False
        assert wrote["marker"] is False


class TestP95NearestRank:
    def test_small_n_uses_ceil(self) -> None:
        metrics = [
            ToolCallMetric(
                call_id="1",
                tool_name="a",
                status="success",
                duration_ms=10.0,
                started_at="t0",
                completed_at="t1",
            ),
            ToolCallMetric(
                call_id="2",
                tool_name="a",
                status="success",
                duration_ms=100.0,
                started_at="t0",
                completed_at="t1",
            ),
        ]
        _avg, p95 = ToolCallMetricsCollector._compute_duration_stats(metrics)
        n = 2
        expected_idx = min(n - 1, max(0, math.ceil(n * 0.95) - 1))
        assert p95 == sorted(m.duration_ms for m in metrics)[expected_idx]
        assert p95 == 100.0


class TestBrainDegradedReachable:
    def test_503_marks_dsn_reachable(self) -> None:
        from tapps_core.brain_bridge import HttpBrainBridge

        bridge = HttpBrainBridge.__new__(HttpBrainBridge)
        result = bridge._health_check_degraded({"http_url": "http://x"}, {"db_ok": False})
        assert result["dsn_reachable"] is True
        assert result["ok"] is False
        assert result["native_health_ok"] is False


class TestKbCacheDir:
    def test_honors_tapps_cache_dir(self, tmp_path: Path, monkeypatch: object) -> None:
        custom = tmp_path / "custom-cache"
        monkeypatch.setenv("TAPPS_CACHE_DIR", str(custom))
        resolved, fallback = resolve_kb_cache_dir(tmp_path / "proj")
        assert resolved == custom
        assert fallback is False
        assert custom.is_dir()


class TestCompileTimeRedScan:
    def test_reports_relative_path_and_skips_venv(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        bad = src / "broken.py"
        bad.write_text("def (\n", encoding="utf-8")
        venv = tmp_path / ".venv" / "lib"
        venv.mkdir(parents=True)
        (venv / "junk.py").write_text("def (\n", encoding="utf-8")
        check = _check_compile_time_red(tmp_path)
        assert check.result == "failed"
        assert "src/broken.py" in check.message
        assert "junk.py" not in check.message

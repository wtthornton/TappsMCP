"""Direct tests for decompose_helpers module (TAP-2769 coverage)."""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.tools.decompose_helpers import (
    _build_unit,
    _collect_file_summaries,
    _decompose_task,
    _summarize_quick_check,
)


class TestSummarizeQuickCheck:
    def test_batch_summary(self) -> None:
        summary = _summarize_quick_check({"batch": {"passed_count": 2, "failed_count": 1}})
        assert "2 passed" in summary
        assert "1 failed" in summary

    def test_score_summary(self) -> None:
        assert _summarize_quick_check({"overall_score": 88.5}) == "score=88.5"

    def test_fallback_ok(self) -> None:
        assert _summarize_quick_check({}) == "ok"


class TestBuildUnit:
    def test_first_unit_with_context_files(self) -> None:
        unit = _build_unit(1, "implement auth module", ["src/auth.py", "tests/test_auth.py"])
        assert "context:" in unit.description
        assert unit.depends_on == []

    def test_second_unit_depends_on_prior(self) -> None:
        unit = _build_unit(2, "write tests for auth", [])
        assert unit.depends_on == ["u1"]


class TestDecomposeTask:
    def test_splits_and_orders_risk_first(self) -> None:
        units = _decompose_task(
            "read config file; implement security fix for auth",
            [],
        )
        assert len(units) >= 2
        assert units[0].dominant_risk == "high"


class TestCollectFileSummaries:
    def test_reports_existing_file(self, tmp_path: Path) -> None:
        f = tmp_path / "sample.py"
        f.write_text("x = 1\n", encoding="utf-8")
        summaries = _collect_file_summaries([str(f), str(tmp_path / "missing.py")])
        assert summaries[0]["exists"] is True
        assert summaries[0]["size_bytes"] == len("x = 1\n")
        assert summaries[1]["exists"] is False

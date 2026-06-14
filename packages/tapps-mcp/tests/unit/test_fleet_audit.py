"""Tests for fleet audit CLI helpers (TAP-3572)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tapps_core.metrics.execution_metrics import ToolCallMetric

from tapps_mcp.tools.fleet_audit import (
    audit_project_root,
    discover_project_roots,
    format_fleet_audit_markdown,
    load_jsonl_metrics,
    merge_metrics,
    parse_period,
    run_fleet_audit,
    run_tool_usage_fleet,
)


def _write_metric(metrics_dir: Path, metric: ToolCallMetric) -> None:
    metrics_dir.mkdir(parents=True, exist_ok=True)
    day = metric.started_at[:10]
    path = metrics_dir / f"tool_calls_{day}.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(metric.to_dict()) + "\n")


def _sample_metric(*, call_id: str = "c1", tool: str = "tapps_session_start") -> ToolCallMetric:
    now = datetime.now(tz=UTC).isoformat()
    return ToolCallMetric(
        call_id=call_id,
        tool_name=tool,
        status="success",
        duration_ms=1.0,
        started_at=now,
        completed_at=now,
        gate_passed=True,
        score=90.0,
    )


class TestFleetAuditHelpers:
    def test_parse_period(self) -> None:
        assert parse_period("1d") == 1
        assert parse_period("7d") == 7

    def test_discover_explicit_roots(self, tmp_path: Path) -> None:
        bootstrapped = tmp_path / "proj-a"
        bootstrapped.mkdir()
        (bootstrapped / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")
        bare = tmp_path / "bare"
        bare.mkdir()

        found = discover_project_roots(explicit_roots=[bootstrapped, bare])
        assert found == [bootstrapped.resolve()]

    def test_discover_scan_parent(self, tmp_path: Path) -> None:
        child = tmp_path / "child"
        child.mkdir()
        (child / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")

        found = discover_project_roots(scan_parent=tmp_path)
        assert found == [child.resolve()]

    def test_load_jsonl_metrics_filters_by_window(self, tmp_path: Path) -> None:
        metrics_dir = tmp_path / "metrics"
        recent = _sample_metric(call_id="recent")
        _write_metric(metrics_dir, recent)

        old_ts = (datetime.now(tz=UTC) - timedelta(days=10)).isoformat()
        old = ToolCallMetric(
            call_id="old",
            tool_name="tapps_score_file",
            status="success",
            duration_ms=1.0,
            started_at=old_ts,
            completed_at=old_ts,
        )
        _write_metric(metrics_dir, old)

        since = datetime.now(tz=UTC) - timedelta(days=1)
        loaded = load_jsonl_metrics(metrics_dir, since=since)
        assert len(loaded) == 1
        assert loaded[0].call_id == "recent"

    def test_merge_metrics_deduplicates(self) -> None:
        local = [_sample_metric(call_id="shared")]
        brain = [_sample_metric(call_id="shared"), _sample_metric(call_id="brain-only")]
        merged = merge_metrics(local, brain)
        assert len(merged) == 2
        assert {m.call_id for m in merged} == {"shared", "brain-only"}


class TestFleetAuditProject:
    def test_audit_project_root_jsonl_only(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("TAPPS_METRICS_STORAGE", "local")
        project = tmp_path / "demo"
        project.mkdir()
        (project / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")
        metrics_dir = project / ".tapps-mcp" / "metrics"
        _write_metric(metrics_dir, _sample_metric(call_id="a"))
        _write_metric(
            metrics_dir,
            _sample_metric(call_id="b", tool="tapps_lookup_docs"),
        )

        report = audit_project_root(
            project,
            since=datetime.now(tz=UTC) - timedelta(days=1),
            include_brain=False,
        )
        assert report["metrics"]["total_calls"] == 2
        assert report["metrics"]["local_jsonl_rows"] == 2
        assert report["metrics"]["session_start_lookup_ratio"] == 1.0
        assert report["top_tools"][0]["name"] == "tapps_session_start"
        assert report["handoff"]["exists"] is False

    def test_run_tool_usage_fleet_leaderboard(self, tmp_path: Path) -> None:
        project = tmp_path / "demo"
        project.mkdir()
        (project / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")
        metrics_dir = project / ".tapps-mcp" / "metrics"
        _write_metric(metrics_dir, _sample_metric(call_id="a", tool="docs_generate_epic"))
        _write_metric(metrics_dir, _sample_metric(call_id="b", tool="tapps_session_start"))

        report = run_tool_usage_fleet(period="1d", roots=[project], include_brain=False)
        assert report["fleet_top_tools"][0]["name"] == "docs_generate_epic"
        assert report["projects"][0]["top_tools"][0]["count"] == 1

    def test_format_markdown_includes_top_tools_and_skills(self, tmp_path: Path) -> None:
        project = tmp_path / "demo"
        project.mkdir()
        (project / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")
        metrics_dir = project / ".tapps-mcp" / "metrics"
        _write_metric(metrics_dir, _sample_metric())
        loop_metrics = project / ".tapps-mcp" / "loop-metrics.jsonl"
        loop_metrics.parent.mkdir(parents=True, exist_ok=True)
        loop_metrics.write_text(
            json.dumps({"ts": int(__import__("time").time()), "skills_used": ["tapps-finish-task"]})
            + "\n",
            encoding="utf-8",
        )
        report = run_fleet_audit(period="1d", roots=[project], include_brain=False)
        md = format_fleet_audit_markdown(report)
        assert "Fleet top tools" in md
        assert "Skill utilization" in md
        assert "tapps-finish-task" in md

    def test_run_fleet_audit_shape(self, tmp_path: Path) -> None:
        project = tmp_path / "demo"
        project.mkdir()
        (project / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")
        metrics_dir = project / ".tapps-mcp" / "metrics"
        _write_metric(metrics_dir, _sample_metric())

        report = run_fleet_audit(period="1d", roots=[project], include_brain=False)
        assert report["project_count"] == 1
        assert report["total_tool_calls"] == 1
        assert report["projects"][0]["project_root"] == str(project.resolve())

    def test_format_markdown_includes_project(self, tmp_path: Path) -> None:
        project = tmp_path / "demo"
        project.mkdir()
        (project / ".tapps-mcp.yaml").write_text("quality_preset: standard\n")
        report = run_fleet_audit(period="1d", roots=[project], include_brain=False)
        md = format_fleet_audit_markdown(report)
        assert "demo" in md
        assert "Total tool calls" in md

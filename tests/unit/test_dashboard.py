"""Tests for dashboard generation."""

from datetime import UTC, datetime, timedelta

import pytest

from tapps_mcp.metrics.dashboard import DashboardGenerator


@pytest.fixture
def metrics_dir(tmp_path):
    d = tmp_path / ".tapps-mcp" / "metrics"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def generator(metrics_dir):
    return DashboardGenerator(metrics_dir)


@pytest.fixture
def generator_with_data(metrics_dir):
    gen = DashboardGenerator(metrics_dir)
    now = datetime.now(tz=UTC)
    gen._execution.record(
        "tapps_score_file",
        now,
        now + timedelta(milliseconds=100),
        status="success",
        score=80.0,
        gate_passed=True,
    )
    gen._execution.record(
        "tapps_quality_gate",
        now,
        now + timedelta(milliseconds=200),
        status="success",
        gate_passed=True,
    )
    gen._execution.record(
        "tapps_consult_expert",
        now,
        now + timedelta(milliseconds=50),
        status="failed",
        error_code="domain_not_found",
    )
    gen._confidence.record("security", 0.85, 0.6)
    gen._rag.record_query("test query", "security", 30.0, 3, [0.8], True)
    return gen


class TestDashboardGenerator:
    def test_generate_json_dashboard(self, generator):
        data = generator.generate_json_dashboard()
        assert "timestamp" in data
        assert "summary" in data
        assert "tool_metrics" in data
        assert "alerts" in data

    def test_generate_with_sections(self, generator):
        data = generator.generate_json_dashboard(sections=["summary", "alerts"])
        assert "summary" in data
        assert "alerts" in data
        assert "tool_metrics" not in data

    def test_summary_section(self, generator_with_data):
        data = generator_with_data.generate_json_dashboard(sections=["summary"])
        summary = data["summary"]
        assert summary["total_tool_calls"] == 3
        assert summary["gate_pass_rate"] > 0

    def test_tool_metrics_section(self, generator_with_data):
        data = generator_with_data.generate_json_dashboard(sections=["tool_metrics"])
        tools = data["tool_metrics"]
        assert len(tools) > 0
        names = [t["tool_name"] for t in tools]
        assert "tapps_score_file" in names

    def test_alerts_section(self, generator):
        data = generator.generate_json_dashboard(sections=["alerts"])
        assert isinstance(data["alerts"], list)

    def test_recommendations_section(self, generator):
        data = generator.generate_json_dashboard(sections=["recommendations"])
        assert isinstance(data["recommendations"], list)

    def test_generate_markdown_dashboard(self, generator_with_data):
        md = generator_with_data.generate_markdown_dashboard()
        assert "# TappsMCP Dashboard" in md
        assert "Summary" in md

    def test_generate_html_dashboard(self, generator_with_data):
        html = generator_with_data.generate_html_dashboard()
        assert "<!DOCTYPE html>" in html
        assert "TappsMCP Dashboard" in html

    def test_save_dashboard_json(self, generator_with_data):
        path = generator_with_data.save_dashboard(fmt="json")
        assert path.exists()
        assert path.suffix == ".json"

    def test_save_dashboard_markdown(self, generator_with_data):
        path = generator_with_data.save_dashboard(fmt="markdown")
        assert path.exists()
        assert path.suffix == ".md"

    def test_save_dashboard_html(self, generator_with_data):
        path = generator_with_data.save_dashboard(fmt="html")
        assert path.exists()
        assert path.suffix == ".html"

    def test_save_dashboard_invalid_format(self, generator):
        with pytest.raises(ValueError, match="Unsupported format"):
            generator.save_dashboard(fmt="pdf")

    def test_quality_distribution(self, generator_with_data):
        data = generator_with_data.generate_json_dashboard(sections=["quality_distribution"])
        dist = data["quality_distribution"]
        assert "90-100" in dist
        assert "0-59" in dist

    def test_coverage_metrics_from_disk(self, metrics_dir):
        """Coverage metrics use disk data, so files_scored reflects file_path in records."""
        gen = DashboardGenerator(metrics_dir)
        project_root = metrics_dir.parent.parent
        file_path = str(project_root / "src" / "main.py")
        now = datetime.now(tz=UTC)
        gen._execution.record(
            "tapps_score_file",
            now,
            now + timedelta(milliseconds=100),
            status="success",
            file_path=file_path,
            score=85.0,
        )
        gen._execution.record(
            "tapps_quality_gate",
            now,
            now + timedelta(milliseconds=150),
            status="success",
            file_path=file_path,
            gate_passed=True,
        )
        data = gen.generate_json_dashboard(sections=["coverage_metrics"])
        cov = data["coverage_metrics"]
        assert cov["files_scored"] >= 1
        assert cov["files_gated"] >= 1
        assert "tapps_score_file" in cov["core_tools_used"]

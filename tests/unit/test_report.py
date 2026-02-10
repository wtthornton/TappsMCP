"""Tests for project.report -- JSON / Markdown / HTML quality report generation."""

from __future__ import annotations

from tapps_mcp.gates.models import GateResult
from tapps_mcp.project.report import generate_report
from tapps_mcp.scoring.models import CategoryScore, ScoreResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_score(
    path: str = "test.py",
    overall: float = 75.0,
) -> ScoreResult:
    """Create a minimal ScoreResult for testing."""
    return ScoreResult(
        file_path=path,
        categories={
            "security": CategoryScore(name="security", score=8.0, weight=0.27),
        },
        overall_score=overall,
    )


def _make_gate(passed: bool = True) -> GateResult:
    """Create a minimal GateResult for testing."""
    return GateResult(passed=passed, preset="standard")


# ---------------------------------------------------------------------------
# JSON format (default)
# ---------------------------------------------------------------------------


class TestJsonReport:
    """Tests for the default JSON report format."""

    def test_json_report_structure(self) -> None:
        """Default format returns dict with format, content, and summary keys."""
        result = generate_report([_make_score()])

        assert "format" in result
        assert "content" in result
        assert "summary" in result
        assert result["format"] == "json"

    def test_json_report_content_has_files(self) -> None:
        """The content dict has a 'files' list."""
        result = generate_report([_make_score()])
        content = result["content"]

        assert isinstance(content, dict)
        assert "files" in content
        assert isinstance(content["files"], list)
        assert len(content["files"]) == 1
        assert content["files"][0]["file_path"] == "test.py"

    def test_empty_scores(self) -> None:
        """Empty score list returns files_scored=0 in summary."""
        result = generate_report([])
        summary = result["summary"]

        assert summary["files_scored"] == 0

    def test_multiple_files(self) -> None:
        """Multiple ScoreResults are aggregated correctly."""
        scores = [
            _make_score("a.py", 60.0),
            _make_score("b.py", 80.0),
            _make_score("c.py", 100.0),
        ]
        result = generate_report(scores)
        summary = result["summary"]

        assert summary["files_scored"] == 3
        assert summary["avg_score"] == 80.0  # (60+80+100)/3
        assert summary["min_score"] == 60.0
        assert summary["max_score"] == 100.0

        content = result["content"]
        assert len(content["files"]) == 3


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------


class TestSummaryStats:
    """Tests for summary calculations."""

    def test_summary_avg_score(self) -> None:
        """Summary has correct avg_score for a single file."""
        result = generate_report([_make_score(overall=82.0)])
        summary = result["summary"]

        assert summary["avg_score"] == 82.0

    def test_summary_gate_pass_rate(self) -> None:
        """With gates provided, summary has a gate_pass_rate."""
        scores = [_make_score("a.py", 90.0), _make_score("b.py", 50.0)]
        gates = [_make_gate(passed=True), _make_gate(passed=False)]

        result = generate_report(scores, gates)
        summary = result["summary"]

        assert summary["gate_pass_rate"] == 0.5

    def test_summary_no_gates(self) -> None:
        """When no gates are provided, gate_pass_rate is None."""
        result = generate_report([_make_score()])
        summary = result["summary"]

        assert summary["gate_pass_rate"] is None


# ---------------------------------------------------------------------------
# Markdown format
# ---------------------------------------------------------------------------


class TestMarkdownReport:
    """Tests for the Markdown report format."""

    def test_markdown_report_is_string(self) -> None:
        """format='markdown' returns string content."""
        result = generate_report(
            [_make_score()],
            report_format="markdown",
        )

        assert result["format"] == "markdown"
        assert isinstance(result["content"], str)
        assert "# TappsMCP Quality Report" in result["content"]

    def test_markdown_contains_file_table(self) -> None:
        """Markdown output includes the file table with score."""
        result = generate_report(
            [_make_score("my_module.py", 88.0)],
            report_format="markdown",
        )
        content: str = result["content"]

        assert "my_module.py" in content
        assert "88.0" in content


# ---------------------------------------------------------------------------
# HTML format
# ---------------------------------------------------------------------------


class TestHtmlReport:
    """Tests for the HTML report format."""

    def test_html_report_is_string(self) -> None:
        """format='html' returns string content."""
        result = generate_report(
            [_make_score()],
            report_format="html",
        )

        assert result["format"] == "html"
        assert isinstance(result["content"], str)
        assert "<!DOCTYPE html>" in result["content"]

    def test_html_contains_score_color(self) -> None:
        """HTML output includes colour styling for scores."""
        result = generate_report(
            [_make_score(overall=90.0)],
            report_format="html",
        )
        content: str = result["content"]

        # Score >= 80 -> green (#2e7d32)
        assert "#2e7d32" in content

    def test_html_low_score_color(self) -> None:
        """HTML output uses red colour for low scores."""
        result = generate_report(
            [_make_score(overall=40.0)],
            report_format="html",
        )
        content: str = result["content"]

        # Score < 60 -> red (#c62828)
        assert "#c62828" in content

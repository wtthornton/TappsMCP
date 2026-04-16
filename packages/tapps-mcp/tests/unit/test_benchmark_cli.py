"""Unit tests for benchmark CLI commands (Epic 30, Story 6)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from click.testing import CliRunner

from tapps_mcp.benchmark.mock_evaluator import make_test_result
from tapps_mcp.benchmark.models import (
    BenchmarkConfig,
    BenchmarkInstance,
    BenchmarkResult,
    ContextMode,
    RunMetadata,
)
from tapps_mcp.cli import main

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REQUIRED_INSTANCE_FIELDS: dict[str, Any] = {
    "instance_id": "cli-test-001",
    "repo": "owner/repo",
    "problem_description": "Fix the bug.",
    "clean_pr_patch": ("--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-old\n+new\n"),
    "test_commands": ["pytest tests/"],
    "test_file_names": ["tests/test_foo.py"],
    "test_file_contents": {"tests/test_foo.py": "def test(): pass"},
    "docker_image": "",
}


def _make_instance(**overrides: Any) -> BenchmarkInstance:
    """Build a BenchmarkInstance with sensible defaults."""
    fields: dict[str, Any] = {**_REQUIRED_INSTANCE_FIELDS, **overrides}
    return BenchmarkInstance(**fields)


def _make_results(
    count: int = 3,
    mode: ContextMode = ContextMode.NONE,
) -> list[BenchmarkResult]:
    """Build a list of BenchmarkResult for testing."""
    return [
        make_test_result(
            instance_id=f"inst-{i}",
            context_mode=mode,
            resolved=i % 2 == 0,
        )
        for i in range(count)
    ]


def _write_run_data(
    output_dir: Path,
    run_id: str,
    results: list[BenchmarkResult] | None = None,
    config: BenchmarkConfig | None = None,
) -> None:
    """Write minimal run data (results.jsonl + metadata.json)."""
    effective_results = results or _make_results()
    effective_config = config or BenchmarkConfig()

    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Write JSONL
    jsonl_path = run_dir / "results.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for result in effective_results:
            f.write(result.model_dump_json() + "\n")

    # Write metadata
    mode = effective_results[0].context_mode if effective_results else effective_config.context_mode
    metadata = RunMetadata(
        run_id=run_id,
        config=effective_config,
        instance_count=len(effective_results),
        context_mode=mode,
    )
    meta_path = run_dir / "metadata.json"
    meta_path.write_text(
        metadata.model_dump_json(indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Help output tests
# ---------------------------------------------------------------------------


class TestBenchmarkGroupHelp:
    """Test that the benchmark group and subcommands expose help."""

    def test_benchmark_group_help(self) -> None:
        """``tapps-mcp benchmark --help`` shows subcommands."""
        runner = CliRunner()
        result = runner.invoke(main, ["benchmark", "--help"])

        assert result.exit_code == 0
        assert "benchmark" in result.output.lower()
        assert "run" in result.output
        assert "analyze" in result.output
        assert "report" in result.output

    def test_benchmark_run_help(self) -> None:
        """``tapps-mcp benchmark run --help`` shows all options."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["benchmark", "run", "--help"],
        )

        assert result.exit_code == 0
        assert "--dataset" in result.output
        assert "--context-mode" in result.output
        assert "--engagement-level" in result.output
        assert "--subset" in result.output
        assert "--workers" in result.output
        assert "--output-dir" in result.output
        assert "--run-id" in result.output
        assert "--mock" in result.output

    def test_benchmark_analyze_help(self) -> None:
        """``tapps-mcp benchmark analyze --help`` shows options."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["benchmark", "analyze", "--help"],
        )

        assert result.exit_code == 0
        assert "--run-id" in result.output
        assert "--compare" in result.output
        assert "--format" in result.output
        assert "--output-dir" in result.output

    def test_benchmark_report_help(self) -> None:
        """``tapps-mcp benchmark report --help`` shows options."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["benchmark", "report", "--help"],
        )

        assert result.exit_code == 0
        assert "--output" in result.output
        assert "--output-dir" in result.output
        assert "--include-redundancy" in result.output


# ---------------------------------------------------------------------------
# Run command tests
# ---------------------------------------------------------------------------


class TestBenchmarkRunCommand:
    """Test the benchmark run command."""

    def test_run_with_mock(self, tmp_path: Path) -> None:
        """Run with --mock and a fixture dataset produces output."""
        dataset_file = tmp_path / "dataset.jsonl"
        instance_data = {
            **_REQUIRED_INSTANCE_FIELDS,
            "instance_id": "mock-run-001",
        }
        dataset_file.write_text(
            json.dumps(instance_data) + "\n",
            encoding="utf-8",
        )

        output_dir = tmp_path / "results"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "benchmark",
                "run",
                "--mock",
                "--dataset",
                str(dataset_file),
                "--output-dir",
                str(output_dir),
                "--run-id",
                "test-run",
                "--context-mode",
                "none",
                "--subset",
                "0",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "Benchmark run: test-run" in result.output
        assert "Loaded 1 instances" in result.output
        assert "MockEvaluator" in result.output

    def test_run_default_options(self) -> None:
        """Verify default option values appear in help."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["benchmark", "run", "--help"],
        )

        assert result.exit_code == 0
        assert "eth-sri/agentbench" in result.output
        assert "all" in result.output  # context-mode default
        assert "medium" in result.output  # engagement-level default

    def test_run_creates_output(self, tmp_path: Path) -> None:
        """Mock run creates output files in the output directory."""
        dataset_file = tmp_path / "dataset.jsonl"
        instance_data = {
            **_REQUIRED_INSTANCE_FIELDS,
            "instance_id": "output-test-001",
        }
        dataset_file.write_text(
            json.dumps(instance_data) + "\n",
            encoding="utf-8",
        )

        output_dir = tmp_path / "bench_output"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "benchmark",
                "run",
                "--mock",
                "--dataset",
                str(dataset_file),
                "--output-dir",
                str(output_dir),
                "--run-id",
                "out-test",
                "--context-mode",
                "tapps",
                "--subset",
                "0",
            ],
        )

        assert result.exit_code == 0, result.output
        run_dir = output_dir / "out-test-tapps"
        assert run_dir.exists(), f"Expected {run_dir} to exist. Output: {result.output}"
        assert (run_dir / "results.jsonl").exists()
        assert (run_dir / "metadata.json").exists()

    def test_run_all_modes_creates_multiple_dirs(
        self,
        tmp_path: Path,
    ) -> None:
        """Run with --context-mode all creates dirs for each mode."""
        dataset_file = tmp_path / "dataset.jsonl"
        instance_data = {
            **_REQUIRED_INSTANCE_FIELDS,
            "instance_id": "all-mode-001",
        }
        dataset_file.write_text(
            json.dumps(instance_data) + "\n",
            encoding="utf-8",
        )

        output_dir = tmp_path / "all_modes"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "benchmark",
                "run",
                "--mock",
                "--dataset",
                str(dataset_file),
                "--output-dir",
                str(output_dir),
                "--run-id",
                "multi",
                "--context-mode",
                "all",
                "--subset",
                "0",
            ],
        )

        assert result.exit_code == 0, result.output
        assert (output_dir / "multi-none").exists()
        assert (output_dir / "multi-tapps").exists()
        assert (output_dir / "multi-human").exists()


# ---------------------------------------------------------------------------
# Analyze command tests
# ---------------------------------------------------------------------------


class TestBenchmarkAnalyzeCommand:
    """Test the benchmark analyze command."""

    def test_analyze_no_runs(self, tmp_path: Path) -> None:
        """Analyze with empty directory shows error."""
        output_dir = tmp_path / "empty_bench"
        output_dir.mkdir()

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "benchmark",
                "analyze",
                "--output-dir",
                str(output_dir),
            ],
        )

        assert result.exit_code != 0
        assert "No benchmark runs found" in result.output

    def test_analyze_single_run(self, tmp_path: Path) -> None:
        """Analyze a single run prints summary."""
        output_dir = tmp_path / "bench"
        _write_run_data(output_dir, "run-001")

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "benchmark",
                "analyze",
                "--run-id",
                "run-001",
                "--output-dir",
                str(output_dir),
            ],
        )

        assert result.exit_code == 0
        assert "Run: run-001" in result.output
        assert "Instances:" in result.output
        assert "Resolution rate:" in result.output

    def test_analyze_latest_run(self, tmp_path: Path) -> None:
        """Analyze without --run-id uses the latest run."""
        output_dir = tmp_path / "bench"
        _write_run_data(output_dir, "run-old")
        _write_run_data(output_dir, "run-new")

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "benchmark",
                "analyze",
                "--output-dir",
                str(output_dir),
            ],
        )

        assert result.exit_code == 0
        assert "Run:" in result.output

    def test_analyze_compare_wrong_count(
        self,
        tmp_path: Path,
    ) -> None:
        """Compare with 1 or 3 IDs shows error."""
        output_dir = tmp_path / "bench"
        output_dir.mkdir()

        runner = CliRunner()

        # Single ID
        result_one = runner.invoke(
            main,
            [
                "benchmark",
                "analyze",
                "--compare",
                "run-001",
                "--output-dir",
                str(output_dir),
            ],
        )
        assert result_one.exit_code != 0
        assert "exactly 2" in result_one.output

        # Three IDs
        result_three = runner.invoke(
            main,
            [
                "benchmark",
                "analyze",
                "--compare",
                "run-001,run-002,run-003",
                "--output-dir",
                str(output_dir),
            ],
        )
        assert result_three.exit_code != 0
        assert "exactly 2" in result_three.output

    def test_analyze_compare_two_runs(
        self,
        tmp_path: Path,
    ) -> None:
        """Compare two runs produces comparison output."""
        output_dir = tmp_path / "bench"
        _write_run_data(
            output_dir,
            "baseline",
            _make_results(5, ContextMode.NONE),
        )
        _write_run_data(
            output_dir,
            "treatment",
            _make_results(5, ContextMode.TAPPS),
        )

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "benchmark",
                "analyze",
                "--compare",
                "baseline,treatment",
                "--output-dir",
                str(output_dir),
                "--format",
                "markdown",
            ],
        )

        assert result.exit_code == 0
        assert "Comparison" in result.output or "Resolution" in result.output

    def test_analyze_compare_json_format(
        self,
        tmp_path: Path,
    ) -> None:
        """Compare with --format json produces valid JSON."""
        output_dir = tmp_path / "bench"
        _write_run_data(
            output_dir,
            "base",
            _make_results(3, ContextMode.NONE),
        )
        _write_run_data(
            output_dir,
            "treat",
            _make_results(3, ContextMode.TAPPS),
        )

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "benchmark",
                "analyze",
                "--compare",
                "base,treat",
                "--output-dir",
                str(output_dir),
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        # Output may contain structlog debug lines before the JSON.
        # Extract the JSON object starting from the first '{'.
        output = result.output
        json_start = output.index("{")
        parsed = json.loads(output[json_start:])
        assert "resolution_delta" in parsed

    def test_analyze_compare_missing_run(
        self,
        tmp_path: Path,
    ) -> None:
        """Compare with a nonexistent run ID shows error."""
        output_dir = tmp_path / "bench"
        _write_run_data(output_dir, "exists")

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "benchmark",
                "analyze",
                "--compare",
                "exists,does-not-exist",
                "--output-dir",
                str(output_dir),
            ],
        )

        assert result.exit_code != 0
        assert "Error" in result.output


# ---------------------------------------------------------------------------
# Report command tests
# ---------------------------------------------------------------------------


class TestBenchmarkReportCommand:
    """Test the benchmark report command."""

    def test_report_no_runs(self, tmp_path: Path) -> None:
        """Report with empty directory shows error."""
        output_dir = tmp_path / "empty_bench"
        output_dir.mkdir()

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "benchmark",
                "report",
                "--output-dir",
                str(output_dir),
            ],
        )

        assert result.exit_code != 0
        assert "No benchmark runs found" in result.output

    def test_report_stdout(self, tmp_path: Path) -> None:
        """Report with runs prints markdown to stdout."""
        output_dir = tmp_path / "bench"
        _write_run_data(output_dir, "run-abc")

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "benchmark",
                "report",
                "--output-dir",
                str(output_dir),
            ],
        )

        assert result.exit_code == 0
        assert "# TappsMCP Benchmark Report" in result.output
        assert "run-abc" in result.output
        assert "Total runs: 1" in result.output

    def test_report_to_file(self, tmp_path: Path) -> None:
        """Report with --output writes to file."""
        output_dir = tmp_path / "bench"
        _write_run_data(output_dir, "run-file")
        report_file = tmp_path / "report.md"

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "benchmark",
                "report",
                "--output-dir",
                str(output_dir),
                "--output",
                str(report_file),
            ],
        )

        assert result.exit_code == 0
        assert report_file.exists()
        content = report_file.read_text(encoding="utf-8")
        assert "# TappsMCP Benchmark Report" in content
        assert "run-file" in content

    def test_report_include_redundancy(
        self,
        tmp_path: Path,
    ) -> None:
        """Report with --include-redundancy adds a note."""
        output_dir = tmp_path / "bench"
        _write_run_data(output_dir, "run-red")

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "benchmark",
                "report",
                "--output-dir",
                str(output_dir),
                "--include-redundancy",
            ],
        )

        assert result.exit_code == 0
        assert "Redundancy" in result.output

    def test_report_multiple_runs(self, tmp_path: Path) -> None:
        """Report lists all runs in a table."""
        output_dir = tmp_path / "bench"
        _write_run_data(output_dir, "run-1")
        _write_run_data(output_dir, "run-2")
        _write_run_data(output_dir, "run-3")

        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "benchmark",
                "report",
                "--output-dir",
                str(output_dir),
            ],
        )

        assert result.exit_code == 0
        assert "Total runs: 3" in result.output
        assert "run-1" in result.output
        assert "run-2" in result.output
        assert "run-3" in result.output

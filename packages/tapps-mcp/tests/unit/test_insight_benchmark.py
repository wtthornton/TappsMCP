"""Tests for tapps_mcp.benchmark.insight_benchmark (STORY-102.7)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from tapps_mcp.benchmark.insight_benchmark import (
    BenchmarkLatencies,
    InsightBenchmarkResult,
    run_insight_benchmark,
)


# ---------------------------------------------------------------------------
# BenchmarkLatencies
# ---------------------------------------------------------------------------


class TestBenchmarkLatencies:
    def test_from_empty_samples(self):
        lat = BenchmarkLatencies.from_samples("write", [])
        assert lat.count == 0
        assert lat.p50_ms == 0.0

    def test_from_single_sample(self):
        lat = BenchmarkLatencies.from_samples("write", [10.0])
        assert lat.count == 1
        assert lat.p50_ms == 10.0
        assert lat.p95_ms == 10.0
        assert lat.p99_ms == 10.0

    def test_from_multiple_samples(self):
        samples = [float(i) for i in range(1, 101)]
        lat = BenchmarkLatencies.from_samples("search", samples)
        assert lat.count == 100
        assert lat.p50_ms <= 55.0
        assert lat.p95_ms <= 100.0
        assert lat.p99_ms <= 100.0

    def test_throughput_non_negative(self):
        lat = BenchmarkLatencies.from_samples("write", [1.0, 2.0, 3.0])
        assert lat.throughput_per_s >= 0.0

    def test_operation_name_preserved(self):
        lat = BenchmarkLatencies.from_samples("bulk_migrate", [5.0])
        assert lat.operation == "bulk_migrate"

    def test_total_ms_is_sum(self):
        lat = BenchmarkLatencies.from_samples("write", [10.0, 20.0, 30.0])
        assert abs(lat.total_ms - 60.0) < 0.01


# ---------------------------------------------------------------------------
# InsightBenchmarkResult
# ---------------------------------------------------------------------------


class TestInsightBenchmarkResult:
    def test_markdown_report_unavailable(self):
        r = InsightBenchmarkResult(available=False)
        report = r.markdown_report()
        assert "Skipped" in report or "unavailable" in report

    def test_markdown_report_error(self):
        r = InsightBenchmarkResult(error="something went wrong")
        report = r.markdown_report()
        assert "Error" in report or "something went wrong" in report

    def test_markdown_report_has_table(self):
        lat = BenchmarkLatencies.from_samples("write", [1.0, 2.0])
        r = InsightBenchmarkResult(latencies=[lat], n=10, backend="sqlite")
        report = r.markdown_report()
        assert "| write |" in report

    def test_markdown_report_has_header(self):
        r = InsightBenchmarkResult(latencies=[], n=0)
        report = r.markdown_report()
        assert "Insight Benchmark" in report

    def test_default_backend_is_sqlite(self):
        r = InsightBenchmarkResult()
        assert r.backend == "sqlite"


# ---------------------------------------------------------------------------
# run_insight_benchmark — with fake store
# ---------------------------------------------------------------------------


class FakeBenchStore:
    """Minimal fake store for benchmark testing."""

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []

    def save(self, **kwargs: Any) -> dict[str, Any]:
        self._entries.append(kwargs)
        return {"key": kwargs["key"]}

    def search(self, query: str, **kwargs: Any) -> list[Any]:
        return []


class TestRunInsightBenchmark:
    def test_returns_benchmark_result(self, tmp_path: Path):
        store = FakeBenchStore()
        result = run_insight_benchmark(tmp_path, n=5, store=store)
        assert isinstance(result, InsightBenchmarkResult)

    def test_result_is_available(self, tmp_path: Path):
        store = FakeBenchStore()
        result = run_insight_benchmark(tmp_path, n=5, store=store)
        assert result.available is True

    def test_n_recorded(self, tmp_path: Path):
        store = FakeBenchStore()
        result = run_insight_benchmark(tmp_path, n=10, store=store)
        assert result.n == 10

    def test_writes_n_entries(self, tmp_path: Path):
        store = FakeBenchStore()
        run_insight_benchmark(tmp_path, n=7, store=store)
        assert len(store._entries) == 7

    def test_three_operations_in_latencies(self, tmp_path: Path):
        store = FakeBenchStore()
        result = run_insight_benchmark(tmp_path, n=5, store=store)
        ops = [lat.operation for lat in result.latencies]
        assert "write" in ops
        assert "search" in ops
        assert "bulk_migrate" in ops

    def test_write_latencies_count_matches_n(self, tmp_path: Path):
        store = FakeBenchStore()
        result = run_insight_benchmark(tmp_path, n=8, store=store)
        write_lat = next(l for l in result.latencies if l.operation == "write")
        assert write_lat.count == 8

    def test_project_root_in_result(self, tmp_path: Path):
        store = FakeBenchStore()
        result = run_insight_benchmark(tmp_path, n=2, store=store, backend="sqlite")
        assert str(tmp_path) in result.project_root

    def test_backend_label_preserved(self, tmp_path: Path):
        store = FakeBenchStore()
        result = run_insight_benchmark(tmp_path, n=2, store=store, backend="postgres")
        assert result.backend == "postgres"

    def test_unavailable_on_import_error(self, tmp_path: Path):
        import sys
        with pytest.MonkeyPatch().context() as mp:
            mp.setitem(sys.modules, "tapps_brain", None)  # type: ignore[arg-type]
            mp.setitem(sys.modules, "tapps_brain.store", None)  # type: ignore[arg-type]
            result = run_insight_benchmark(tmp_path, n=5)
        assert result.available is False

    def test_markdown_report_from_run(self, tmp_path: Path):
        store = FakeBenchStore()
        result = run_insight_benchmark(tmp_path, n=3, store=store)
        report = result.markdown_report()
        assert "write" in report
        assert "search" in report

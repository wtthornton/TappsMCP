"""Postgres-backed brain performance benchmark (STORY-102.7).

Benchmarks the tapps-brain MemoryStore (SQLite backend, EPIC-43 Postgres path)
across the core insight operations: bulk write, BM25 search, and bulk_migrate
promotion. Reports p50/p95/p99 latencies per operation so that teams can
baseline SQLite performance and quantify the Postgres uplift once EPIC-43 lands.

Postgres integration
--------------------
The actual Postgres backend lives in EPIC-43 (tapps-brain v3). This benchmark
is intentionally backend-agnostic: it measures whatever store is instantiated.
To benchmark Postgres, instantiate a MemoryStore pointing at a Postgres DSN
and pass it to :func:`run_insight_benchmark` via the ``store`` parameter.

Typical usage::

    from tapps_mcp.benchmark.insight_benchmark import run_insight_benchmark
    from pathlib import Path

    result = run_insight_benchmark(Path.cwd(), n=500)
    print(result.markdown_report())
"""

from __future__ import annotations

import random
import statistics
import time
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

_BENCH_MEMORY_GROUP = "benchmark-insights"
_SAMPLE_VALUES = [
    "Architecture: uses layered shim pattern over tapps-brain",
    "Quality gate failing on complexity in scorer.py",
    "Security: no hardcoded secrets found in config module",
    "Pattern: all async handlers use structlog for logging",
    "Dependency: tapps-brain pinned at v2.0.4 via git tag",
    "Documentation: README is comprehensive and up-to-date",
    "Architecture: memory module is deprecated re-export shim",
    "Quality: 97% test coverage on core scoring module",
    "Security: path traversal protection in PathValidator",
    "Pattern: Pydantic v2 models used throughout for config",
]
_SAMPLE_TAGS = [
    ["architecture", "docs-mcp", "schema-v1", "insight-type:architecture"],
    ["quality", "tapps-mcp", "schema-v1", "insight-type:quality"],
    ["security", "tapps-mcp", "schema-v1", "insight-type:security"],
    ["pattern", "docs-mcp", "schema-v1", "insight-type:pattern"],
    ["dependency", "tapps-mcp", "schema-v1", "insight-type:dependency"],
]


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class BenchmarkLatencies(BaseModel):
    """Latency statistics for a single benchmark operation."""

    operation: str = Field(description="Operation name (write, search, migrate).")
    count: int = Field(default=0, ge=0, description="Number of samples.")
    p50_ms: float = Field(default=0.0, description="Median latency (ms).")
    p95_ms: float = Field(default=0.0, description="95th percentile latency (ms).")
    p99_ms: float = Field(default=0.0, description="99th percentile latency (ms).")
    mean_ms: float = Field(default=0.0, description="Mean latency (ms).")
    total_ms: float = Field(default=0.0, description="Total wall-clock time (ms).")
    throughput_per_s: float = Field(default=0.0, description="Operations per second.")

    @classmethod
    def from_samples(cls, operation: str, samples_ms: list[float]) -> BenchmarkLatencies:
        if not samples_ms:
            return cls(operation=operation)
        sorted_s = sorted(samples_ms)
        n = len(sorted_s)
        total = sum(sorted_s)
        return cls(
            operation=operation,
            count=n,
            p50_ms=round(sorted_s[int(n * 0.50)], 3),
            p95_ms=round(sorted_s[min(int(n * 0.95), n - 1)], 3),
            p99_ms=round(sorted_s[min(int(n * 0.99), n - 1)], 3),
            mean_ms=round(statistics.mean(sorted_s), 3),
            total_ms=round(total, 3),
            throughput_per_s=round(n / (total / 1000) if total > 0 else 0.0, 1),
        )


class InsightBenchmarkResult(BaseModel):
    """Full result of an insight benchmark run."""

    backend: str = Field(default="sqlite", description="Store backend (sqlite or postgres).")
    n: int = Field(default=0, ge=0, description="Number of synthetic entries used.")
    project_root: str = Field(default="", description="Project root path.")
    latencies: list[BenchmarkLatencies] = Field(default_factory=list)
    available: bool = Field(default=True, description="False when tapps-brain is absent.")
    error: str = Field(default="", description="Non-empty when benchmark failed.")

    def markdown_report(self) -> str:
        """Return a markdown-formatted benchmark report."""
        if not self.available:
            return "## Insight Benchmark\n\nSkipped: tapps-brain unavailable.\n"
        if self.error:
            return f"## Insight Benchmark\n\nError: {self.error}\n"

        lines = [
            "## Insight Benchmark",
            "",
            f"**Backend:** {self.backend}  **N:** {self.n}  **Root:** `{self.project_root}`",
            "",
            "| Operation | Count | p50 ms | p95 ms | p99 ms | Mean ms | Throughput/s |",
            "|-----------|-------|--------|--------|--------|---------|-------------|",
        ]
        for lat in self.latencies:
            lines.append(
                f"| {lat.operation} | {lat.count} | {lat.p50_ms} "
                f"| {lat.p95_ms} | {lat.p99_ms} | {lat.mean_ms} "
                f"| {lat.throughput_per_s} |"
            )
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------


def _gen_key(i: int) -> str:
    return f"bench.insight.entry.{i:05d}"


def _gen_entry_kwargs(i: int) -> dict[str, Any]:
    return {
        "key": _gen_key(i),
        "value": random.choice(_SAMPLE_VALUES) + f" (entry {i})",
        "tier": "architectural",
        "source": "system",
        "source_agent": "bench",
        "scope": "project",
        "tags": random.choice(_SAMPLE_TAGS),
        "memory_group": _BENCH_MEMORY_GROUP,
        "skip_consolidation": True,
    }


def run_insight_benchmark(
    project_root: Path,
    n: int = 100,
    *,
    store: Any = None,
    backend: str = "sqlite",
) -> InsightBenchmarkResult:
    """Run the insight benchmark suite against a MemoryStore.

    Phases:
    1. **Write** — save N synthetic entries one-by-one; measure per-save latency.
    2. **Search** — run 20 BM25 queries; measure per-query latency.
    3. **Migrate** — call bulk_migrate on all N entries; measure total latency.

    Args:
        project_root: Project root for the default MemoryStore. Ignored when
            *store* is provided.
        n: Number of synthetic entries to write. Default 100 for fast CI runs;
            use 1000+ for production benchmarking.
        store: Optional pre-constructed MemoryStore. When None, opens the
            default SQLite store at *project_root*.
        backend: Label for the report (``"sqlite"`` or ``"postgres"``).

    Returns:
        :class:`InsightBenchmarkResult` with per-operation latency stats.
    """
    from tapps_core.insights.migration import bulk_migrate

    if store is None:
        try:
            from tapps_brain.store import MemoryStore

            store = MemoryStore(project_root)
        except ImportError:
            logger.debug("tapps_brain_unavailable_for_benchmark")
            return InsightBenchmarkResult(
                backend=backend,
                n=n,
                project_root=str(project_root),
                available=False,
            )
        except Exception as exc:
            return InsightBenchmarkResult(
                backend=backend,
                n=n,
                project_root=str(project_root),
                available=False,
                error=str(exc),
            )

    # ------------------------------------------------------------------
    # Phase 1: Write
    # ------------------------------------------------------------------
    write_samples: list[float] = []
    try:
        for i in range(n):
            kwargs = _gen_entry_kwargs(i)
            t0 = time.perf_counter()
            store.save(**kwargs)
            write_samples.append((time.perf_counter() - t0) * 1000)
    except Exception as exc:
        logger.warning("benchmark_write_failed", exc_info=True)
        return InsightBenchmarkResult(
            backend=backend, n=n, project_root=str(project_root), error=str(exc)
        )

    # ------------------------------------------------------------------
    # Phase 2: Search
    # ------------------------------------------------------------------
    search_queries = [
        "architecture",
        "quality",
        "security",
        "pattern",
        "dependency",
        "shim",
        "test",
        "config",
        "memory",
        "async",
        "scorer",
        "complexity",
        "docs",
        "brain",
        "federat",
        "tapps",
        "api",
        "pydantic",
        "structlog",
        "path",
    ]
    search_samples: list[float] = []
    try:
        for q in search_queries:
            t0 = time.perf_counter()
            store.search(q, memory_group=_BENCH_MEMORY_GROUP)
            search_samples.append((time.perf_counter() - t0) * 1000)
    except Exception:
        logger.warning("benchmark_search_failed", exc_info=True)

    # ------------------------------------------------------------------
    # Phase 3: bulk_migrate
    # ------------------------------------------------------------------
    migrate_samples: list[float] = []
    try:
        raw = store.search("bench", memory_group=_BENCH_MEMORY_GROUP)
        t0 = time.perf_counter()
        bulk_migrate(raw)
        migrate_samples.append((time.perf_counter() - t0) * 1000)
    except Exception:
        logger.warning("benchmark_migrate_failed", exc_info=True)

    latencies = [
        BenchmarkLatencies.from_samples("write", write_samples),
        BenchmarkLatencies.from_samples("search", search_samples),
        BenchmarkLatencies.from_samples("bulk_migrate", migrate_samples),
    ]

    logger.info(
        "insight_benchmark_complete",
        n=n,
        backend=backend,
        write_p95=latencies[0].p95_ms,
        search_p95=latencies[1].p95_ms,
    )

    return InsightBenchmarkResult(
        backend=backend,
        n=n,
        project_root=str(project_root),
        latencies=latencies,
        available=True,
    )

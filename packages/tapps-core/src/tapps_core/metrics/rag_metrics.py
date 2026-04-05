"""RAG (Retrieval-Augmented Generation) metrics tracker.

Tracks RAG query performance: latency, hit rates, similarity distributions,
and backend type breakdown. Stored as bounded JSON (last N queries).
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import structlog

from tapps_core.common.utils import utc_now

logger = structlog.get_logger(__name__)

_MAX_RECORDS = 100


@dataclass
class RAGQueryMetric:
    """Single RAG query performance record."""

    query: str
    domain: str
    latency_ms: float
    num_results: int
    avg_similarity: float = 0.0
    max_similarity: float = 0.0
    min_similarity: float = 0.0
    cache_hit: bool = False
    backend_type: str = "simple"  # simple or vector
    session_id: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RAGQueryMetric:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class RAGPerformanceMetrics:
    """Aggregate RAG performance metrics."""

    total_queries: int = 0
    avg_latency_ms: float = 0.0
    cache_hit_rate: float = 0.0
    avg_similarity: float = 0.0
    by_domain: dict[str, dict[str, Any]] = field(default_factory=dict)
    by_backend: dict[str, dict[str, Any]] = field(default_factory=dict)


class RAGMetricsTracker:
    """Tracks RAG query metrics with bounded storage."""

    def __init__(self, metrics_dir: Path) -> None:
        self._metrics_dir = metrics_dir
        self._metrics_dir.mkdir(parents=True, exist_ok=True)
        self._file = self._metrics_dir / "rag_metrics.json"
        self._write_lock = threading.Lock()

    def record_query(
        self,
        query: str,
        domain: str,
        latency_ms: float,
        num_results: int,
        similarities: list[float] | None = None,
        cache_hit: bool = False,
        backend_type: str = "simple",
        session_id: str = "",
    ) -> RAGQueryMetric:
        """Record a RAG query result."""
        sims = similarities or []
        metric = RAGQueryMetric(
            query=query[:200],  # truncate long queries
            domain=domain,
            latency_ms=round(latency_ms, 2),
            num_results=num_results,
            avg_similarity=round(sum(sims) / len(sims), 4) if sims else 0.0,
            max_similarity=round(max(sims), 4) if sims else 0.0,
            min_similarity=round(min(sims), 4) if sims else 0.0,
            cache_hit=cache_hit,
            backend_type=backend_type,
            session_id=session_id,
            timestamp=utc_now().isoformat(),
        )

        with self._write_lock:
            records = self._load()
            records.append(metric)
            if len(records) > _MAX_RECORDS:
                records = records[-_MAX_RECORDS:]
            self._save(records)

        return metric

    def get_metrics(self) -> RAGPerformanceMetrics:
        """Get aggregate RAG performance metrics."""
        records = self._load()
        if not records:
            return RAGPerformanceMetrics()

        avg_lat = sum(r.latency_ms for r in records) / len(records)
        cache_hits = sum(1 for r in records if r.cache_hit)
        sims = [r.avg_similarity for r in records if r.avg_similarity > 0]
        avg_sim = sum(sims) / len(sims) if sims else 0.0

        # By domain
        by_domain: dict[str, dict[str, Any]] = {}
        domain_groups: dict[str, list[RAGQueryMetric]] = {}
        for r in records:
            domain_groups.setdefault(r.domain, []).append(r)
        for domain, group in domain_groups.items():
            by_domain[domain] = {
                "queries": len(group),
                "avg_latency_ms": round(sum(g.latency_ms for g in group) / len(group), 2),
                "cache_hit_rate": round(sum(1 for g in group if g.cache_hit) / len(group), 4),
            }

        # By backend
        by_backend: dict[str, dict[str, Any]] = {}
        backend_groups: dict[str, list[RAGQueryMetric]] = {}
        for r in records:
            backend_groups.setdefault(r.backend_type, []).append(r)
        for backend, group in backend_groups.items():
            by_backend[backend] = {
                "queries": len(group),
                "avg_latency_ms": round(sum(g.latency_ms for g in group) / len(group), 2),
                "avg_similarity": round(sum(g.avg_similarity for g in group) / len(group), 4),
            }

        return RAGPerformanceMetrics(
            total_queries=len(records),
            avg_latency_ms=round(avg_lat, 2),
            cache_hit_rate=round(cache_hits / len(records), 4),
            avg_similarity=round(avg_sim, 4),
            by_domain=by_domain,
            by_backend=by_backend,
        )

    def get_recent(self, limit: int = 20) -> list[RAGQueryMetric]:
        """Get most recent RAG query records."""
        records = self._load()
        return records[-limit:]

    def _load(self) -> list[RAGQueryMetric]:
        if not self._file.exists():
            return []
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return []
            return [RAGQueryMetric.from_dict(r) for r in data]
        except (json.JSONDecodeError, OSError, TypeError):
            return []

    def _save(self, records: list[RAGQueryMetric]) -> None:
        data = [r.to_dict() for r in records]
        try:
            self._file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            logger.warning("rag_metrics_write_failed", exc_info=True)


class RAGQueryTimer:
    """Context manager for timing RAG queries.

    Usage::

        timer = RAGQueryTimer()
        with timer:
            results = rag.search(query)
        latency = timer.elapsed_ms
    """

    def __init__(self) -> None:
        self._start: float = 0.0
        self.elapsed_ms: float = 0.0

    def __enter__(self) -> RAGQueryTimer:
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args: object) -> None:
        self.elapsed_ms = (time.perf_counter() - self._start) * 1000.0

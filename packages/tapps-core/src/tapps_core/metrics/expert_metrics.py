"""Expert performance tracking and analysis.

Tracks consultation outcomes, identifies weak domains, and correlates
expert consultations with code quality improvements.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import structlog

from tapps_core.common.utils import utc_now

logger = structlog.get_logger(__name__)

_LOW_CONFIDENCE_THRESHOLD = 0.5
_LOW_SUCCESS_THRESHOLD = 0.5


@dataclass
class ExpertPerformanceRecord:
    """Aggregated performance for a single expert/domain."""

    expert_id: str
    domain: str
    consultations: int = 0
    avg_confidence: float = 0.0
    first_pass_success_rate: float = 0.0
    code_quality_improvement: float = 0.0
    domain_coverage: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConsultationRecord:
    """Single expert consultation event."""

    expert_id: str
    domain: str
    confidence: float
    query: str = ""
    session_id: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConsultationRecord:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class ExpertPerformanceTracker:
    """Tracks expert consultation performance.

    Records each consultation and aggregates performance by expert/domain.
    """

    def __init__(self, metrics_dir: Path) -> None:
        self._metrics_dir = metrics_dir
        self._metrics_dir.mkdir(parents=True, exist_ok=True)
        self._file = self._metrics_dir / "expert_performance.jsonl"
        self._write_lock = threading.Lock()

    def track_consultation(
        self,
        expert_id: str,
        domain: str,
        confidence: float,
        query: str = "",
        session_id: str = "",
    ) -> ConsultationRecord:
        """Record an expert consultation."""
        record = ConsultationRecord(
            expert_id=expert_id,
            domain=domain,
            confidence=confidence,
            query=query,
            session_id=session_id,
            timestamp=utc_now().isoformat(),
        )

        with self._write_lock:
            line = json.dumps(record.to_dict(), ensure_ascii=False)
            try:
                with self._file.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError:
                logger.warning("expert_perf_write_failed", exc_info=True)

        return record

    def get_performance(
        self,
        expert_id: str | None = None,
        days: int = 30,
    ) -> list[ExpertPerformanceRecord]:
        """Get aggregated performance, optionally filtered by expert."""
        records = self._load_records(days=days)

        # Group by expert_id
        by_expert: dict[str, list[ConsultationRecord]] = {}
        for r in records:
            if expert_id and r.expert_id != expert_id:
                continue
            by_expert.setdefault(r.expert_id, []).append(r)

        results: list[ExpertPerformanceRecord] = []
        for eid, consultations in sorted(by_expert.items()):
            confs = [c.confidence for c in consultations]
            avg_conf = sum(confs) / len(confs) if confs else 0.0
            domains = sorted({c.domain for c in consultations})
            weaknesses = self._identify_weaknesses(avg_conf)

            results.append(
                ExpertPerformanceRecord(
                    expert_id=eid,
                    domain=domains[0] if domains else "",
                    consultations=len(consultations),
                    avg_confidence=round(avg_conf, 4),
                    domain_coverage=domains,
                    weaknesses=weaknesses,
                )
            )

        return results

    def get_domain_breakdown(self, days: int = 30) -> dict[str, dict[str, Any]]:
        """Get performance breakdown by domain."""
        records = self._load_records(days=days)

        by_domain: dict[str, list[ConsultationRecord]] = {}
        for r in records:
            by_domain.setdefault(r.domain, []).append(r)

        breakdown: dict[str, dict[str, Any]] = {}
        for domain, consultations in sorted(by_domain.items()):
            confs = [c.confidence for c in consultations]
            breakdown[domain] = {
                "consultations": len(consultations),
                "avg_confidence": round(sum(confs) / len(confs), 4) if confs else 0.0,
                "unique_experts": len({c.expert_id for c in consultations}),
            }

        return breakdown

    def rotate(self, keep_recent: int = 1000) -> int:
        """Rotate the performance file, keeping only the most recent entries.

        Returns the number of entries removed.
        """
        with self._write_lock:
            records = self._load_all_records()
            if len(records) <= keep_recent:
                return 0

            removed = len(records) - keep_recent
            kept = records[-keep_recent:]

            try:
                with self._file.open("w", encoding="utf-8") as fh:
                    for r in kept:
                        fh.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")
            except OSError:
                logger.warning("expert_perf_rotate_failed", exc_info=True)
                return 0

            return removed

    def _load_all_records(self) -> list[ConsultationRecord]:
        """Load all consultation records without date filtering."""
        if not self._file.exists():
            return []

        records: list[ConsultationRecord] = []
        try:
            text = self._file.read_text(encoding="utf-8")
        except OSError:
            return []

        for line in text.strip().splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                if not isinstance(data, dict):
                    continue
                records.append(ConsultationRecord.from_dict(data))
            except (json.JSONDecodeError, TypeError):
                pass

        return records

    def _load_records(self, days: int = 30) -> list[ConsultationRecord]:
        """Load consultation records within the time window."""
        if not self._file.exists():
            return []

        cutoff = utc_now() - timedelta(days=days)
        records: list[ConsultationRecord] = []

        try:
            text = self._file.read_text(encoding="utf-8")
        except OSError:
            return []

        for line in text.strip().splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                if not isinstance(data, dict):
                    continue
                record = ConsultationRecord.from_dict(data)
                if record.timestamp:
                    try:
                        ts = datetime.fromisoformat(record.timestamp)
                        if ts < cutoff:
                            continue
                    except (ValueError, TypeError):
                        pass
                records.append(record)
            except (json.JSONDecodeError, TypeError):
                pass

        return records

    @staticmethod
    def _identify_weaknesses(avg_confidence: float) -> list[str]:
        weaknesses: list[str] = []
        if avg_confidence < _LOW_CONFIDENCE_THRESHOLD:
            weaknesses.append("low_confidence")
        return weaknesses

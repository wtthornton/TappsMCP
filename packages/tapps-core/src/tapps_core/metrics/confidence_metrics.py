"""Confidence metrics tracker.

Tracks expert agreement levels and confidence threshold compliance.
Stored as a bounded JSON file (last N records).
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import structlog

from tapps_core.common.utils import utc_now

logger = structlog.get_logger(__name__)

_MAX_RECORDS = 1000


@dataclass
class ConfidenceMetric:
    """Single confidence measurement."""

    domain: str
    confidence: float
    threshold: float
    meets_threshold: bool
    agreement_level: float = 0.0  # 0-1, how much experts agree
    num_experts: int = 1
    session_id: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConfidenceMetric:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ConfidenceStatistics:
    """Aggregate confidence statistics."""

    total_records: int = 0
    avg_confidence: float = 0.0
    threshold_meet_rate: float = 0.0
    avg_agreement: float = 0.0
    by_domain: dict[str, dict[str, float]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.by_domain is None:
            self.by_domain = {}


class ConfidenceMetricsTracker:
    """Tracks confidence metrics with bounded storage.

    Stores last N records in a JSON file.
    """

    def __init__(self, metrics_dir: Path) -> None:
        self._metrics_dir = metrics_dir
        self._metrics_dir.mkdir(parents=True, exist_ok=True)
        self._file = self._metrics_dir / "confidence_metrics.json"
        self._write_lock = threading.Lock()

    def record(
        self,
        domain: str,
        confidence: float,
        threshold: float = 0.6,
        agreement_level: float = 0.0,
        num_experts: int = 1,
        session_id: str = "",
    ) -> ConfidenceMetric:
        """Record a confidence measurement."""
        metric = ConfidenceMetric(
            domain=domain,
            confidence=confidence,
            threshold=threshold,
            meets_threshold=confidence >= threshold,
            agreement_level=agreement_level,
            num_experts=num_experts,
            session_id=session_id,
            timestamp=utc_now().isoformat(),
        )

        with self._write_lock:
            records = self._load()
            records.append(metric)
            # Trim to max
            if len(records) > _MAX_RECORDS:
                records = records[-_MAX_RECORDS:]
            self._save(records)

        return metric

    def get_statistics(self) -> ConfidenceStatistics:
        """Get aggregate confidence statistics."""
        records = self._load()
        if not records:
            return ConfidenceStatistics()

        avg_conf = sum(r.confidence for r in records) / len(records)
        meet_rate = sum(1 for r in records if r.meets_threshold) / len(records)
        avg_agreement = sum(r.agreement_level for r in records) / len(records)

        # Per-domain breakdown
        by_domain: dict[str, dict[str, float]] = {}
        domain_groups: dict[str, list[ConfidenceMetric]] = {}
        for r in records:
            domain_groups.setdefault(r.domain, []).append(r)

        for domain, group in domain_groups.items():
            by_domain[domain] = {
                "avg_confidence": round(sum(g.confidence for g in group) / len(group), 4),
                "threshold_meet_rate": round(
                    sum(1 for g in group if g.meets_threshold) / len(group), 4
                ),
                "count": float(len(group)),
            }

        return ConfidenceStatistics(
            total_records=len(records),
            avg_confidence=round(avg_conf, 4),
            threshold_meet_rate=round(meet_rate, 4),
            avg_agreement=round(avg_agreement, 4),
            by_domain=by_domain,
        )

    def get_recent(self, limit: int = 50) -> list[ConfidenceMetric]:
        """Get most recent confidence records."""
        records = self._load()
        return records[-limit:]

    def _load(self) -> list[ConfidenceMetric]:
        """Load records from JSON file."""
        if not self._file.exists():
            return []
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return []
            return [ConfidenceMetric.from_dict(r) for r in data]
        except (json.JSONDecodeError, OSError, TypeError):
            return []

    def _save(self, records: list[ConfidenceMetric]) -> None:
        """Save records to JSON file."""
        data = [r.to_dict() for r in records]
        try:
            self._file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            logger.warning("confidence_metrics_write_failed", exc_info=True)

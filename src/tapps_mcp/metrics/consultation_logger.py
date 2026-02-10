"""Consultation history logger.

Append-only JSONL log of all expert consultations with rotation support.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path  # noqa: TC003
from typing import Any

import structlog

from tapps_mcp.common.utils import utc_now

logger = structlog.get_logger(__name__)

_DEFAULT_KEEP_RECENT = 1000


@dataclass
class ConsultationEntry:
    """A single consultation log entry."""

    expert_id: str
    domain: str
    confidence: float
    reasoning: str = ""
    context_summary: str = ""
    session_id: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConsultationEntry:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class ConsultationLogger:
    """Append-only consultation history with rotation."""

    def __init__(self, metrics_dir: Path) -> None:
        self._metrics_dir = metrics_dir
        self._metrics_dir.mkdir(parents=True, exist_ok=True)
        self._file = self._metrics_dir / "expert-history.jsonl"
        self._write_lock = threading.Lock()

    def log_consultation(
        self,
        expert_id: str,
        domain: str,
        confidence: float,
        reasoning: str = "",
        context_summary: str = "",
        session_id: str = "",
    ) -> ConsultationEntry:
        """Log a consultation entry."""
        entry = ConsultationEntry(
            expert_id=expert_id,
            domain=domain,
            confidence=confidence,
            reasoning=reasoning[:500],  # truncate long reasoning
            context_summary=context_summary[:200],
            session_id=session_id,
            timestamp=utc_now().isoformat(),
        )

        with self._write_lock:
            line = json.dumps(entry.to_dict(), ensure_ascii=False)
            try:
                with self._file.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError:
                logger.warning("consultation_log_failed", exc_info=True)

        return entry

    def get_recent(self, limit: int = 50) -> list[ConsultationEntry]:
        """Get most recent consultation entries."""
        entries = self._load_all()
        return entries[-limit:]

    def get_by_expert(self, expert_id: str) -> list[ConsultationEntry]:
        """Get all consultations for a specific expert."""
        return [e for e in self._load_all() if e.expert_id == expert_id]

    def get_by_domain(self, domain: str) -> list[ConsultationEntry]:
        """Get all consultations for a specific domain."""
        return [e for e in self._load_all() if e.domain == domain]

    def get_statistics(self) -> dict[str, Any]:
        """Get consultation statistics."""
        entries = self._load_all()
        if not entries:
            return {"total_consultations": 0, "domains": {}, "experts": {}}

        domain_counts: dict[str, int] = {}
        expert_counts: dict[str, int] = {}
        for e in entries:
            domain_counts[e.domain] = domain_counts.get(e.domain, 0) + 1
            expert_counts[e.expert_id] = expert_counts.get(e.expert_id, 0) + 1

        return {
            "total_consultations": len(entries),
            "domains": domain_counts,
            "experts": expert_counts,
        }

    def rotate(self, keep_recent: int = _DEFAULT_KEEP_RECENT) -> int:
        """Rotate log, keeping only the most recent entries.

        Returns the number of entries removed.
        """
        with self._write_lock:
            entries = self._load_all()
            if len(entries) <= keep_recent:
                return 0

            removed = len(entries) - keep_recent
            kept = entries[-keep_recent:]

            try:
                with self._file.open("w", encoding="utf-8") as fh:
                    for entry in kept:
                        fh.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
            except OSError:
                logger.warning("consultation_rotate_failed", exc_info=True)
                return 0

            return removed

    def _load_all(self) -> list[ConsultationEntry]:
        """Load all consultation entries from disk."""
        if not self._file.exists():
            return []

        entries: list[ConsultationEntry] = []
        try:
            text = self._file.read_text(encoding="utf-8")
        except OSError:
            return []

        for line in text.strip().splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                entries.append(ConsultationEntry.from_dict(data))
            except (json.JSONDecodeError, TypeError):
                pass

        return entries

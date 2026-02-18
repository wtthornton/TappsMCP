"""File-based implementations of the adaptive tracking protocols.

Provides JSONL-backed :class:`FileOutcomeTracker` and
:class:`FilePerformanceTracker` that satisfy the protocol interfaces
defined in :mod:`tapps_mcp.adaptive.protocols`.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import structlog

from tapps_mcp.adaptive.models import CodeOutcome, ExpertPerformance, _utc_now_iso

logger = structlog.get_logger(__name__)

# Quality threshold for first-pass success determination.
_QUALITY_THRESHOLD = 70.0

# Weakness detection thresholds.
_LOW_CONFIDENCE_THRESHOLD = 0.6
_LOW_SUCCESS_THRESHOLD = 0.5


class FileOutcomeTracker:
    """JSONL file-backed outcome tracker.

    Each :class:`CodeOutcome` is appended as a single JSON line to
    ``{project_root}/.tapps-mcp/learning/outcomes.jsonl``.
    """

    def __init__(self, project_root: Path) -> None:
        self._store_dir = project_root / ".tapps-mcp" / "learning"
        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._file = self._store_dir / "outcomes.jsonl"

    # -- Protocol methods ---------------------------------------------------

    def save_outcome(self, outcome: CodeOutcome) -> None:
        """Append *outcome* as a JSONL record."""
        line = json.dumps(outcome.model_dump(), ensure_ascii=False)
        try:
            with self._file.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            logger.warning("outcome_save_failed", file=str(self._file), exc_info=True)

    def load_outcomes(
        self,
        limit: int | None = None,
        workflow_id: str | None = None,
    ) -> list[CodeOutcome]:
        """Load outcomes from disk, optionally filtered by *workflow_id*."""
        if not self._file.exists():
            return []

        outcomes: list[CodeOutcome] = []
        try:
            text = self._file.read_text(encoding="utf-8")
        except OSError:
            logger.warning("outcome_load_failed", file=str(self._file), exc_info=True)
            return []

        for line in text.strip().splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                outcome = CodeOutcome.model_validate(data)
                if workflow_id is not None and outcome.workflow_id != workflow_id:
                    continue
                outcomes.append(outcome)
            except (json.JSONDecodeError, ValueError):
                logger.debug("outcome_parse_failed", line=line[:120])

        if limit is not None:
            outcomes = outcomes[-limit:]
        return outcomes

    def get_statistics(self) -> dict[str, Any]:
        """Return aggregate statistics over stored outcomes."""
        outcomes = self.load_outcomes()
        if not outcomes:
            return {
                "total_outcomes": 0,
                "first_pass_success_rate": 0.0,
                "avg_iterations": 0.0,
                "expert_usage": {},
            }

        first_pass_count = sum(1 for o in outcomes if o.first_pass_success)
        total_iterations = sum(o.iterations for o in outcomes)
        expert_usage: dict[str, int] = {}
        for o in outcomes:
            for eid in o.expert_consultations:
                expert_usage[eid] = expert_usage.get(eid, 0) + 1

        return {
            "total_outcomes": len(outcomes),
            "first_pass_success_rate": first_pass_count / len(outcomes),
            "avg_iterations": total_iterations / len(outcomes),
            "expert_usage": expert_usage,
        }


class FilePerformanceTracker:
    """JSONL file-backed expert performance tracker.

    Consultation records are appended to
    ``{project_root}/.tapps-mcp/learning/expert_performance.jsonl``.
    """

    def __init__(self, project_root: Path) -> None:
        self._store_dir = project_root / ".tapps-mcp" / "learning"
        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._file = self._store_dir / "expert_performance.jsonl"

    # -- Protocol methods ---------------------------------------------------

    def track_consultation(
        self,
        expert_id: str,
        domain: str,
        confidence: float,
        query: str | None = None,
    ) -> None:
        """Append a consultation record."""
        record = {
            "expert_id": expert_id,
            "domain": domain,
            "confidence": confidence,
            "query": query or "",
            "timestamp": _utc_now_iso(),
        }
        line = json.dumps(record, ensure_ascii=False)
        try:
            with self._file.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            logger.warning("consultation_save_failed", file=str(self._file), exc_info=True)

    def calculate_performance(
        self,
        expert_id: str,
        days: int = 30,
    ) -> ExpertPerformance | None:
        """Calculate aggregated performance for *expert_id* within *days*."""
        records = self._load_consultations(expert_id, days)
        if not records:
            return None

        confidences = [r["confidence"] for r in records]
        domains = list({r["domain"] for r in records})
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

        weaknesses = self._identify_weaknesses(avg_conf)

        return ExpertPerformance(
            expert_id=expert_id,
            consultations=len(records),
            avg_confidence=round(avg_conf, 4),
            first_pass_success_rate=0.0,  # requires outcome data from Epic 7
            code_quality_improvement=0.0,  # requires outcome data from Epic 7
            domain_coverage=domains,
            weaknesses=weaknesses,
        )

    def get_all_performance(
        self,
        days: int = 30,
    ) -> dict[str, ExpertPerformance]:
        """Calculate performance for every tracked expert."""
        all_ids = self._get_all_expert_ids(days)
        results: dict[str, ExpertPerformance] = {}
        for eid in all_ids:
            perf = self.calculate_performance(eid, days)
            if perf is not None:
                results[eid] = perf
        return results

    # -- Private helpers ----------------------------------------------------

    def _load_consultations(
        self,
        expert_id: str | None = None,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Load consultation records, filtered by expert and time window."""
        if not self._file.exists():
            return []

        cutoff = datetime.now(tz=UTC) - timedelta(days=days)
        records: list[dict[str, Any]] = []

        try:
            text = self._file.read_text(encoding="utf-8")
        except OSError:
            return []

        for line in text.strip().splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue

            # Time filter.
            ts_str = data.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str)
                if ts < cutoff:
                    continue
            except (ValueError, TypeError):
                pass  # keep records without valid timestamps

            if expert_id is not None and data.get("expert_id") != expert_id:
                continue

            records.append(data)

        return records

    def _get_all_expert_ids(self, days: int = 30) -> set[str]:
        """Return all unique expert IDs within the time window."""
        records = self._load_consultations(expert_id=None, days=days)
        return {r["expert_id"] for r in records if "expert_id" in r}

    @staticmethod
    def _identify_weaknesses(avg_confidence: float) -> list[str]:
        """Identify weakness indicators from aggregate metrics."""
        weaknesses: list[str] = []
        if avg_confidence < _LOW_CONFIDENCE_THRESHOLD:
            weaknesses.append("low_confidence")
        return weaknesses


def save_json_atomic(data: dict[str, Any] | list[Any], target: Path) -> None:
    """Write *data* to *target* atomically via a temporary file."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(target.parent),
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        Path(tmp_path).replace(target)
    except BaseException:
        with contextlib.suppress(OSError):
            Path(tmp_path).unlink()
        raise

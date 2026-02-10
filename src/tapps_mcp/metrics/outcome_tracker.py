"""Outcome tracker for code quality lifecycle.

Tracks the full lifecycle of file quality improvement across MCP sessions:
initial scores -> iterations -> gate pass (or abandoned).
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


@dataclass
class CodeOutcome:
    """Record of a file's quality improvement lifecycle."""

    session_id: str
    file_path: str
    initial_scores: dict[str, float] = field(default_factory=dict)
    final_scores: dict[str, float] = field(default_factory=dict)
    iterations: int = 0
    expert_consultations: list[str] = field(default_factory=list)
    time_to_quality: float = 0.0  # seconds
    first_pass_success: bool = False
    gate_preset: str = "standard"
    timestamp: str = ""
    finalized: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CodeOutcome:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class OutcomeTracker:
    """Tracks code quality outcomes across MCP tool sessions.

    Each file being worked on gets an outcome record that tracks
    initial scoring, re-scoring iterations, and final gate pass/fail.
    """

    def __init__(self, metrics_dir: Path) -> None:
        self._metrics_dir = metrics_dir
        self._metrics_dir.mkdir(parents=True, exist_ok=True)
        self._file = self._metrics_dir / "outcomes.jsonl"
        self._active: dict[str, CodeOutcome] = {}  # keyed by session_id:file_path
        self._write_lock = threading.Lock()

    def track_initial_scores(
        self,
        session_id: str,
        file_path: str,
        scores: dict[str, float],
        gate_preset: str = "standard",
    ) -> CodeOutcome:
        """Record the first scoring of a file in a session."""
        key = f"{session_id}:{file_path}"

        # Determine first-pass success from overall score
        overall = scores.get("overall", 0.0)
        thresholds = {"standard": 70.0, "strict": 80.0, "framework": 75.0}
        threshold = thresholds.get(gate_preset, 70.0)

        outcome = CodeOutcome(
            session_id=session_id,
            file_path=file_path,
            initial_scores=dict(scores),
            final_scores=dict(scores),
            iterations=1,
            first_pass_success=overall >= threshold,
            gate_preset=gate_preset,
            timestamp=_utc_now().isoformat(),
        )

        with self._write_lock:
            self._active[key] = outcome

        return outcome

    def track_iteration(
        self,
        session_id: str,
        file_path: str,
        scores: dict[str, float],
        expert_domain: str | None = None,
    ) -> CodeOutcome | None:
        """Record a subsequent re-scoring of a file."""
        key = f"{session_id}:{file_path}"

        with self._write_lock:
            outcome = self._active.get(key)
            if outcome is None:
                return None

            outcome.iterations += 1
            outcome.final_scores = dict(scores)
            if expert_domain and expert_domain not in outcome.expert_consultations:
                outcome.expert_consultations.append(expert_domain)

        return outcome

    def finalize_outcome(
        self,
        session_id: str,
        file_path: str,
        gate_passed: bool = False,
    ) -> CodeOutcome | None:
        """Mark a file outcome as finalized (gate passed or abandoned)."""
        key = f"{session_id}:{file_path}"

        with self._write_lock:
            outcome = self._active.pop(key, None)
            if outcome is None:
                return None

            outcome.finalized = True

            # Calculate time_to_quality if we have a timestamp
            if outcome.timestamp:
                try:
                    start = datetime.fromisoformat(outcome.timestamp)
                    outcome.time_to_quality = (_utc_now() - start).total_seconds()
                except (ValueError, TypeError):
                    pass

            # Persist to disk
            self._append_to_file(outcome)

        return outcome

    def load_outcomes(
        self,
        limit: int | None = None,
        session_id: str | None = None,
    ) -> list[CodeOutcome]:
        """Load outcomes from disk, optionally filtered."""
        if not self._file.exists():
            return []

        outcomes: list[CodeOutcome] = []
        try:
            text = self._file.read_text(encoding="utf-8")
        except OSError:
            return []

        for line in text.strip().splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                outcome = CodeOutcome.from_dict(data)
                if session_id and outcome.session_id != session_id:
                    continue
                outcomes.append(outcome)
            except (json.JSONDecodeError, TypeError):
                pass

        if limit is not None:
            outcomes = outcomes[-limit:]
        return outcomes

    def get_active_outcomes(self) -> list[CodeOutcome]:
        """Return all currently active (non-finalized) outcomes."""
        with self._write_lock:
            return list(self._active.values())

    def get_learning_data(self, min_outcomes: int = 10) -> list[CodeOutcome]:
        """Return outcomes suitable for adaptive scoring weight learning.

        Requires at least *min_outcomes* finalized outcomes.
        """
        outcomes = self.load_outcomes()
        if len(outcomes) < min_outcomes:
            return []
        return outcomes

    def get_statistics(self) -> dict[str, Any]:
        """Return aggregate outcome statistics."""
        outcomes = self.load_outcomes()
        if not outcomes:
            return {
                "total_outcomes": 0,
                "first_pass_success_rate": 0.0,
                "avg_iterations": 0.0,
                "avg_time_to_quality": 0.0,
                "expert_usage": {},
            }

        first_pass = sum(1 for o in outcomes if o.first_pass_success)
        total_iters = sum(o.iterations for o in outcomes)
        times = [o.time_to_quality for o in outcomes if o.time_to_quality > 0]
        avg_ttq = sum(times) / len(times) if times else 0.0

        expert_usage: dict[str, int] = {}
        for o in outcomes:
            for d in o.expert_consultations:
                expert_usage[d] = expert_usage.get(d, 0) + 1

        return {
            "total_outcomes": len(outcomes),
            "first_pass_success_rate": round(first_pass / len(outcomes), 4),
            "avg_iterations": round(total_iters / len(outcomes), 2),
            "avg_time_to_quality": round(avg_ttq, 2),
            "expert_usage": expert_usage,
        }

    def rotate(self, keep_recent: int = 1000) -> int:
        """Rotate the outcomes file, keeping only the most recent entries.

        Returns the number of entries removed.
        """
        with self._write_lock:
            outcomes = self.load_outcomes()
            if len(outcomes) <= keep_recent:
                return 0

            removed = len(outcomes) - keep_recent
            kept = outcomes[-keep_recent:]

            try:
                with self._file.open("w", encoding="utf-8") as fh:
                    for o in kept:
                        fh.write(json.dumps(o.to_dict(), ensure_ascii=False) + "\n")
            except OSError:
                logger.warning("outcome_rotate_failed", file=str(self._file), exc_info=True)
                return 0

            return removed

    def _append_to_file(self, outcome: CodeOutcome) -> None:
        """Append an outcome record to the JSONL file."""
        line = json.dumps(outcome.to_dict(), ensure_ascii=False)
        try:
            with self._file.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            logger.warning("outcome_write_failed", file=str(self._file), exc_info=True)

"""User feedback tracker.

Records user/LLM feedback on tool helpfulness for adaptive learning.
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


@dataclass
class FeedbackRecord:
    """A single feedback entry."""

    tool_name: str
    helpful: bool
    context: str = ""
    session_id: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeedbackRecord:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class FeedbackTracker:
    """Records and queries user feedback on tool outputs."""

    def __init__(self, metrics_dir: Path) -> None:
        self._metrics_dir = metrics_dir
        self._metrics_dir.mkdir(parents=True, exist_ok=True)
        self._file = self._metrics_dir / "feedback.jsonl"
        self._write_lock = threading.Lock()

    def record(
        self,
        tool_name: str,
        helpful: bool,
        context: str = "",
        session_id: str = "",
    ) -> FeedbackRecord:
        """Record a feedback entry."""
        entry = FeedbackRecord(
            tool_name=tool_name,
            helpful=helpful,
            context=context[:500],
            session_id=session_id,
            timestamp=utc_now().isoformat(),
        )

        with self._write_lock:
            line = json.dumps(entry.to_dict(), ensure_ascii=False)
            try:
                with self._file.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError:
                logger.warning("feedback_write_failed", exc_info=True)

        return entry

    def get_statistics(self, tool_name: str | None = None) -> dict[str, Any]:
        """Get feedback statistics, optionally filtered by tool."""
        records = self._load_all()
        if tool_name:
            records = [r for r in records if r.tool_name == tool_name]

        if not records:
            return {
                "total_feedback": 0,
                "helpful_count": 0,
                "not_helpful_count": 0,
                "helpful_rate": 0.0,
            }

        helpful = sum(1 for r in records if r.helpful)
        not_helpful = len(records) - helpful

        return {
            "total_feedback": len(records),
            "helpful_count": helpful,
            "not_helpful_count": not_helpful,
            "helpful_rate": round(helpful / len(records), 4),
        }

    def get_by_tool(self) -> dict[str, dict[str, Any]]:
        """Get feedback statistics broken down by tool."""
        records = self._load_all()
        by_tool: dict[str, list[FeedbackRecord]] = {}
        for r in records:
            by_tool.setdefault(r.tool_name, []).append(r)

        result: dict[str, dict[str, Any]] = {}
        for tool, entries in sorted(by_tool.items()):
            helpful = sum(1 for e in entries if e.helpful)
            result[tool] = {
                "total": len(entries),
                "helpful": helpful,
                "helpful_rate": round(helpful / len(entries), 4) if entries else 0.0,
            }
        return result

    def _load_all(self) -> list[FeedbackRecord]:
        if not self._file.exists():
            return []
        records: list[FeedbackRecord] = []
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
                records.append(FeedbackRecord.from_dict(data))
            except (json.JSONDecodeError, TypeError):
                pass
        return records

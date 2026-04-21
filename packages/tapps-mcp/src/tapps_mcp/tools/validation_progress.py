"""Shared progress-tracker and heartbeat helpers for validate_changed.

Extracted from ``validate_changed.py`` to keep that module under the 800-line
budget.  The heartbeat looks up ``_PROGRESS_HEARTBEAT_INTERVAL`` on
``tapps_mcp.server_pipeline_tools`` at call time so tests patching the
constant on the host module are honoured.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json as _json
import time
from pathlib import Path
from typing import Any

import structlog

_logger = structlog.get_logger(__name__)

_PROGRESS_HEARTBEAT_INTERVAL = 5  # seconds between progress notifications
_VALIDATION_PROGRESS_FILE = ".tapps-mcp/.validation-progress.json"


@dataclasses.dataclass
class _ProgressTracker:
    """Shared progress state for validate_changed heartbeat and sidecar file."""

    total: int = 0
    completed: int = 0
    last_file: str = ""
    _sidecar_path: Path | None = dataclasses.field(default=None, repr=False)
    _results: list[dict[str, Any]] = dataclasses.field(default_factory=list, repr=False)
    _started_at: str = dataclasses.field(default="", repr=False)

    def init_sidecar(self, project_root: Path) -> None:
        """Create sidecar progress file with initial 'running' status."""
        self._sidecar_path = project_root / _VALIDATION_PROGRESS_FILE
        self._started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._write_sidecar({"status": "running"})

    def record_file_result(self, file_path: str, result: dict[str, Any]) -> None:
        """Record a completed file result and update the sidecar."""
        self._results.append(
            {
                "file": file_path,
                "score": result.get("overall_score", 0.0),
                "gate_passed": result.get("gate_passed", False),
            }
        )
        self._write_sidecar({"status": "running"})

    def finalize(
        self,
        all_passed: bool,
        summary: str,
        elapsed_ms: int,
    ) -> None:
        """Write final sidecar state with completed status."""
        self._write_sidecar(
            {
                "status": "completed",
                "all_gates_passed": all_passed,
                "summary": summary,
                "elapsed_ms": elapsed_ms,
            }
        )

    def finalize_error(self, error: str) -> None:
        """Write error status to sidecar."""
        self._write_sidecar({"status": "error", "error": error})

    def _write_sidecar(self, extra: dict[str, Any]) -> None:
        """Write the sidecar progress file (best-effort, never raises)."""
        if self._sidecar_path is None:
            return
        try:
            data = {
                "started_at": self._started_at,
                "total": self.total,
                "completed": self.completed,
                "last_file": self.last_file,
                "results": self._results,
                **extra,
            }
            self._sidecar_path.parent.mkdir(parents=True, exist_ok=True)
            self._sidecar_path.write_text(_json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            _logger.debug("sidecar_write_failed", exc_info=True)


async def _validate_progress_heartbeat(
    ctx: object,
    total_files: int,
    start_ns: int,
    stop_event: asyncio.Event,
    tracker: _ProgressTracker | None = None,
) -> None:
    """Send progress notifications every _PROGRESS_HEARTBEAT_INTERVAL seconds.
    Stops when stop_event is set. No-op if ctx has no report_progress.

    Looks up ``_PROGRESS_HEARTBEAT_INTERVAL`` on ``server_pipeline_tools`` at
    call time so tests patching the constant on the host module are honoured.
    """
    from tapps_mcp import server_pipeline_tools as _host

    report = getattr(ctx, "report_progress", None)
    if not callable(report):
        return
    while True:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=_host._PROGRESS_HEARTBEAT_INTERVAL)
        if stop_event.is_set():
            return
        with contextlib.suppress(Exception):
            if tracker is not None:
                await _report_tracker_progress(report, tracker)
            else:
                elapsed_sec = (time.perf_counter_ns() - start_ns) / 1_000_000_000.0
                await report(
                    progress=elapsed_sec,
                    total=None,
                    message=f"Validating {total_files} files... (in progress)",
                )


async def _report_tracker_progress(report: Any, tracker: _ProgressTracker) -> None:
    """Emit a tracker-based progress notification."""
    done = tracker.completed
    last = tracker.last_file
    msg = f"Validated {done}/{tracker.total} files"
    if last:
        msg += f" ({last})"
    await report(progress=done, total=tracker.total, message=msg)


__all__ = [
    "_PROGRESS_HEARTBEAT_INTERVAL",
    "_ProgressTracker",
    "_VALIDATION_PROGRESS_FILE",
    "_validate_progress_heartbeat",
]

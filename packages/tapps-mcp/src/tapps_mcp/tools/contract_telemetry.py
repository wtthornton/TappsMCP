"""Contract / creator-verifier telemetry for usage-gap compliance (TAP-5543/5548).

Successful contract verification and creator-verifier passes append to JSONL
under ``.tapps-mcp/`` so ``compute_gaps`` can clear
``contract_assertions_unverified`` and ``creator_verifier_skipped``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Literal

Kind = Literal["contract-verified", "creator-verifier"]

_EVENTS_NAME = ".pipeline-mark-events.jsonl"
_MAX_BYTES = 10 * 1024 * 1024
_DEFAULT_WINDOW_DAYS = 7


def _events_path(project_root: Path) -> Path:
    return project_root / ".tapps-mcp" / _EVENTS_NAME


def record_pipeline_mark(
    project_root: Path,
    *,
    kind: Kind,
    source: str = "cli",
) -> None:
    """Append one pipeline-mark event. Best-effort; never raises."""
    metrics_dir = project_root / ".tapps-mcp"
    path = _events_path(project_root)
    row: dict[str, Any] = {
        "ts": int(time.time()),
        "kind": kind,
        "source": source,
    }
    try:
        metrics_dir.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > _MAX_BYTES:
            path.replace(path.with_suffix(path.suffix + ".1"))
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
    except OSError:
        return


def record_contract_verified(project_root: Path, *, source: str = "cli") -> None:
    """Record that validation-contract assertions were independently verified."""
    record_pipeline_mark(project_root, kind="contract-verified", source=source)


def record_creator_verifier(project_root: Path, *, source: str = "cli") -> None:
    """Record that a fresh creator-verifier pass completed."""
    record_pipeline_mark(project_root, kind="creator-verifier", source=source)


def _read_recent_events(project_root: Path, *, limit: int = 200) -> list[dict[str, Any]]:
    path = _events_path(project_root)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return rows[-limit:]


def mark_recorded_recently(
    project_root: Path,
    *,
    kind: Kind,
    window_days: int = _DEFAULT_WINDOW_DAYS,
) -> bool:
    """True when a mark of *kind* exists within the trailing window."""
    cutoff = int(time.time()) - window_days * 86_400
    return any(
        int(row.get("ts", 0)) >= cutoff and row.get("kind") == kind
        for row in _read_recent_events(project_root)
    )


__all__ = [
    "mark_recorded_recently",
    "record_contract_verified",
    "record_creator_verifier",
    "record_pipeline_mark",
]

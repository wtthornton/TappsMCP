"""Cross-channel lookup telemetry for usage-gap compliance (ADR-0021).

Successful doc lookups via MCP or CLI append to
``.tapps-mcp/.lookup-docs-events.jsonl`` so disk-only gap reports
(SessionStart hooks, ``usage-gaps-hint``) see CLI warmup.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_EVENTS_NAME = ".lookup-docs-events.jsonl"
_MAX_BYTES = 10 * 1024 * 1024
_DEFAULT_WINDOW_DAYS = 7


def _events_path(project_root: Path) -> Path:
    return project_root / ".tapps-mcp" / _EVENTS_NAME


def record_lookup_event(
    project_root: Path,
    *,
    library: str,
    topic: str,
    source: str,
    resolved_library: str | None = None,
) -> None:
    """Append one successful lookup event. Best-effort; never raises."""
    lib = library.strip()
    if not lib:
        return
    metrics_dir = project_root / ".tapps-mcp"
    path = _events_path(project_root)
    row: dict[str, Any] = {
        "ts": int(time.time()),
        "library": lib,
        "topic": topic.strip() or "overview",
        "source": source,
    }
    if resolved_library:
        row["resolved_library"] = resolved_library.strip()
    try:
        metrics_dir.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > _MAX_BYTES:
            path.replace(path.with_suffix(path.suffix + ".1"))
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
    except OSError:
        return


def _read_recent_events(project_root: Path, *, limit: int = 200) -> list[dict[str, Any]]:
    path = _events_path(project_root)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return rows[-limit:]


def lookup_recorded_recently(
    project_root: Path,
    *,
    window_days: int = _DEFAULT_WINDOW_DAYS,
) -> bool:
    """True when any lookup event exists within the trailing window."""
    cutoff = int(time.time()) - window_days * 86_400
    return any(int(row.get("ts", 0)) >= cutoff for row in _read_recent_events(project_root))


def lookup_recorded_libraries(
    project_root: Path,
    *,
    window_days: int = _DEFAULT_WINDOW_DAYS,
) -> set[str]:
    """Library names (requested + resolved) recorded within the window."""
    cutoff = int(time.time()) - window_days * 86_400
    names: set[str] = set()
    for row in _read_recent_events(project_root):
        if int(row.get("ts", 0)) < cutoff:
            continue
        for key in ("library", "resolved_library"):
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                names.add(value.strip().lower())
    return names


__all__ = [
    "lookup_recorded_libraries",
    "lookup_recorded_recently",
    "record_lookup_event",
]

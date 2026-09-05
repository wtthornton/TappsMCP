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

# TAP-6615: per-session token/context-growth ledger. Always resolved against
# *project_root* (the caller's resolved settings.project_root), never the
# worktree cwd -- when CLAUDE_PROJECT_DIR is set, callers pass that as
# project_root so the ledger lands under the real project, not a worktree.
_LEDGER_NAME = ".session-token-ledger.jsonl"
_LEDGER_MAX_BYTES = 10 * 1024 * 1024


def _events_path(project_root: Path) -> Path:
    return project_root / ".tapps-mcp" / _EVENTS_NAME


def _ledger_path(project_root: Path) -> Path:
    return project_root / ".tapps-mcp" / _LEDGER_NAME


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


def record_tool_result_bytes(
    project_root: Path,
    *,
    tool_name: str,
    byte_size: int,
    source: str = "tool",
) -> None:
    """Append one session-ledger line for a tool result (TAP-6615).

    Telemetry only: best-effort and never raises, so a ledger-write failure
    cannot affect the calling tool's own result. ``source`` distinguishes a
    direct MCP tool result (``"tool"``) from a delegated subagent result
    (``"subagent"``) -- both count toward the per-session byte/context-growth
    summary :func:`tapps_mcp.tools.usage.summarize_session_ledger` builds.
    """
    metrics_dir = project_root / ".tapps-mcp"
    path = _ledger_path(project_root)
    row: dict[str, Any] = {
        "ts": int(time.time()),
        "tool": tool_name,
        "bytes": int(byte_size),
        "source": source,
    }
    try:
        metrics_dir.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > _LEDGER_MAX_BYTES:
            path.replace(path.with_suffix(path.suffix + ".1"))
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")
    except OSError:
        return


def read_session_ledger(project_root: Path, *, limit: int = 5000) -> list[dict[str, Any]]:
    """Return the trailing *limit* session-ledger rows, oldest first."""
    path = _ledger_path(project_root)
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


__all__ = [
    "mark_recorded_recently",
    "read_session_ledger",
    "record_contract_verified",
    "record_creator_verifier",
    "record_pipeline_mark",
    "record_tool_result_bytes",
]

"""JSONL path helpers and append/read for loop metrics (TAP-5606)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_METRICS_NAME = "loop-metrics.jsonl"
_VIOLATIONS_NAME = ".completion-gate-violations.jsonl"
_ROTATE_BYTES = 10 * 1024 * 1024


def _metrics_path(project_root: Path) -> Path:
    return project_root / ".tapps-mcp" / _METRICS_NAME


def _cursor_project_slug(workspace_root: Path) -> str:
    return workspace_root.resolve().as_posix().lstrip("/").replace("/", "-")


def _newest_transcript(candidates: list[Path]) -> Path:
    return max(candidates, key=lambda p: p.stat().st_mtime)


def resolve_cursor_transcript_path(
    workspace_root: Path,
    conversation_id: str = "",
) -> Path | None:
    """Best-effort Cursor transcript path from workspace slug + conversation id."""
    base = Path.home() / ".cursor" / "projects" / _cursor_project_slug(workspace_root)
    transcripts = base / "agent-transcripts"
    if not transcripts.is_dir():
        return None
    candidates = list(transcripts.rglob("*.jsonl"))
    if not candidates:
        return None
    if conversation_id:
        matched = [
            p for p in candidates if conversation_id in p.name or conversation_id in str(p.parent)
        ]
        if matched:
            return _newest_transcript(matched)
    return _newest_transcript(candidates)


def _rotate_if_needed(path: Path) -> None:
    if path.exists() and path.stat().st_size > _ROTATE_BYTES:
        path.replace(path.with_name(path.name + ".1"))


def append_loop_metrics_row(project_root: Path, row: dict[str, Any]) -> None:
    """Append one loop-metrics JSONL row (rotates at 10 MB)."""
    metrics_dir = project_root / ".tapps-mcp"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = _metrics_path(project_root)
    _rotate_if_needed(metrics_path)
    payload = {k: v for k, v in row.items() if k != "violations"}
    with metrics_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload) + "\n")


def append_completion_gate_violations(
    project_root: Path,
    violations: list[str],
    files_edited: list[str],
    *,
    mode: str = "warn",
) -> None:
    """Warn-mode completion-gate violation log (TAP-1327 / TAP-5274)."""
    if not violations:
        return
    metrics_dir = project_root / ".tapps-mcp"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    violations_path = metrics_dir / _VIOLATIONS_NAME
    _rotate_if_needed(violations_path)
    with violations_path.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ts": int(time.time()),
                    "mode": mode,
                    "reasons": violations,
                    "files_edited": files_edited[:16],
                }
            )
            + "\n"
        )


def _load_jsonl_rows(path: Path) -> list[dict[str, Any]]:
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
    return rows


def read_loop_metrics(project_root: Path, *, limit: int = 1000) -> list[dict[str, Any]]:
    """Return the most recent ``limit`` loop-metrics rows. Best-effort, no raise."""
    path = _metrics_path(project_root)
    if not path.exists():
        return []
    return _load_jsonl_rows(path)[-limit:]

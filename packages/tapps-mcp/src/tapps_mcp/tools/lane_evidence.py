"""Parse a claude -p lane-log transcript for its final LINEAR EVIDENCE block (TAP-6614).

Pure parser: reads a claude -p stream-JSON (JSONL) transcript already on disk and extracts
the structured evidence a dispatched lane prints at the end of its run. No LLM calls, no
network, no subprocess.

The evidence marker string (``--- LINEAR EVIDENCE ---``) can appear more than once in a log:
a lane's own prompt is frequently echoed back into the transcript as a tool_result (e.g. the
lane reading its own prompt file), and that echo carries the literal marker as part of the
template it was told to fill in. Only ``type == "result"`` events (the terminal event of a
completed turn) are treated as authoritative; a ``type == "user"`` row (which is what a
tool_result echo is wrapped in) is never inspected for the marker. On a resumed session the
log has more than one ``result`` event appended in sequence — the LAST one wins.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_EVIDENCE_START = "--- LINEAR EVIDENCE ---"
_EVIDENCE_END = "--- END EVIDENCE ---"
_SENTINEL_RE = re.compile(r"LANE-COMPLETE:\s*(done|blocked)")


def _iter_rows(log_path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with log_path.open(encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _last_assistant_text(rows: list[dict[str, Any]]) -> str | None:
    """Concatenate text blocks from the LAST top-level assistant message, if any."""
    for row in reversed(rows):
        if row.get("type") != "assistant":
            continue
        message = row.get("message")
        if not isinstance(message, dict):
            continue
        blocks = message.get("content")
        if not isinstance(blocks, list):
            continue
        texts = [
            blk.get("text")
            for blk in blocks
            if isinstance(blk, dict) and blk.get("type") == "text" and isinstance(blk.get("text"), str)
        ]
        if texts:
            return "\n".join(texts)
    return None


def _last_result_text(rows: list[dict[str, Any]]) -> str | None:
    """Return the ``result`` field of the LAST ``type == "result"`` row, if any."""
    for row in reversed(rows):
        if row.get("type") != "result":
            continue
        result = row.get("result")
        if isinstance(result, str):
            return result
    return None


def _extract_evidence_block(text: str) -> str | None:
    start = text.find(_EVIDENCE_START)
    if start == -1:
        return None
    end = text.find(_EVIDENCE_END, start)
    if end == -1:
        return None
    return text[start : end + len(_EVIDENCE_END)]


def _parse_evidence_fields(block: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if line in (_EVIDENCE_START, _EVIDENCE_END) or not line:
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        fields[key.strip()] = value.strip()
    return fields


def parse_lane_evidence(log_path: Path) -> dict[str, Any]:
    """Parse a claude -p stream-JSON lane transcript for its final evidence block.

    Only ``type == "result"`` rows (the last one, for a resumed session) are treated as a
    completed run's final message. When the log has no ``result`` row at all (the lane was
    killed mid-run), the run is reported incomplete and ``evidence_found`` is explicitly
    ``False`` regardless of whatever partial assistant text preceded the kill.
    """
    rows = _iter_rows(log_path)
    result_text = _last_result_text(rows)
    run_completed = result_text is not None
    final_message = result_text if run_completed else _last_assistant_text(rows)

    evidence_block: str | None = None
    evidence_fields: dict[str, str] = {}
    sentinel: str | None = None
    if run_completed and final_message is not None:
        evidence_block = _extract_evidence_block(final_message)
        if evidence_block is not None:
            evidence_fields = _parse_evidence_fields(evidence_block)
        match = _SENTINEL_RE.search(final_message)
        if match is not None:
            sentinel = match.group(1)

    return {
        "final_message": final_message,
        "run_completed": run_completed,
        "evidence_found": run_completed and evidence_block is not None,
        "evidence_block": evidence_block,
        "evidence_fields": evidence_fields,
        "sentinel": sentinel,
    }

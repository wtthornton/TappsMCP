"""TAP-2009 / TAP-6924: Server-side Linear write gate — sentinel I/O and
refusal envelope.

``docs_validate_linear_issue`` writes two sentinels when ``agent_ready=true``:

- ``.tapps-mcp/.linear-validate-sentinel`` — a bare Unix-epoch integer. This
  format is a shared contract with the Claude Code hook pair
  (``tapps-post-docs-validate.sh`` writes it, ``tapps-pre-linear-write.sh``
  reads it) which read/write the file directly in bash, not through this
  module. Its format is frozen — do not change it here, or the hooks silently
  break (see ``.claude/rules/linear-standards.md``).
- ``.tapps-mcp/.linear-validate-payload.json`` (TAP-6924) — a JSON record of
  *which* ``(title, description)`` payload was approved, plus its timestamp.
  This is the payload-keyed gate: ``docs_save_linear_issue`` refuses when the
  payload it is handed does not match the one last validated, in addition to
  the pre-existing staleness check. This file has no client-side reader; it
  is private to this module.

The server-side write is the primary path for clients without PostToolUse
hooks (Cursor, VS Code, CI); Claude Code's hook pair provides defence-in-depth
for the legacy timestamp-only sentinel but does not enforce payload identity.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

# Sentinel TTL — must match tapps-pre-linear-write.sh
_SENTINEL_MAX_AGE_S: int = 1800  # 30 minutes

# Legacy sentinel path relative to project root — shared, bare-integer format
# with the Claude Code hook pair. DO NOT change this file's format or path.
_SENTINEL_REL: str = ".tapps-mcp/.linear-validate-sentinel"

# TAP-6924: payload-keyed sentinel. Separate file, separate format (JSON),
# read only by this module — no hook depends on it.
_PAYLOAD_SENTINEL_REL: str = ".tapps-mcp/.linear-validate-payload.json"


def write_validate_sentinel(project_dir: Path) -> bool:
    """Write a fresh ``docs_validate_linear_issue`` sentinel (Unix epoch seconds).

    Called by ``docs_validate_linear_issue`` when ``agent_ready=true``. Returns
    ``True`` when the file was written successfully.
    """
    sentinel = project_dir / _SENTINEL_REL
    try:
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text(str(int(time.time())), encoding="utf-8")
        return True
    except OSError:
        return False


def check_validate_sentinel(project_dir: Path) -> bool:
    """Return True if a fresh ``docs_validate_linear_issue`` sentinel exists.

    "Fresh" means the sentinel file exists and contains a Unix epoch that
    is within ``_SENTINEL_MAX_AGE_S`` seconds of now — the same TTL
    enforced by the PreToolUse bash hook.
    """
    sentinel = project_dir / _SENTINEL_REL
    if not sentinel.exists():
        return False
    try:
        age = time.time() - float(sentinel.read_text(encoding="utf-8").strip())
        return 0 <= age <= _SENTINEL_MAX_AGE_S
    except (ValueError, OSError):
        return False


def _normalize_payload_text(text: str) -> str:
    """Normalise a title/description string before hashing (TAP-6924).

    Allowed to differ between the validated and saved payload: CRLF vs LF
    line endings, trailing whitespace on any line, and leading/trailing
    blank lines. Everything else — wording, case, internal whitespace,
    section content — must match exactly.

    Server-side rewrites the Linear plugin performs *after* save (e.g.
    bare ``TAP-###`` becoming ``<issue id="…">TAP-###</issue>``) happen
    downstream of this gate and are out of scope for normalisation here.
    """
    unified = text.replace("\r\n", "\n").replace("\r", "\n")
    stripped_lines = [line.rstrip() for line in unified.split("\n")]
    return "\n".join(stripped_lines).strip("\n")


def compute_payload_digest(title: str, description: str) -> str:
    """SHA-256 hex digest of the normalised ``(title, description)`` pair."""
    normalized = f"{_normalize_payload_text(title)}\x00{_normalize_payload_text(description)}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def write_payload_sentinel(project_dir: Path, title: str, description: str) -> bool:
    """Record the digest of the exact payload ``docs_validate_linear_issue`` approved.

    Called alongside :func:`write_validate_sentinel` when ``agent_ready=true``.
    Returns ``True`` when the file was written successfully.
    """
    sentinel = project_dir / _PAYLOAD_SENTINEL_REL
    try:
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        record = {"digest": compute_payload_digest(title, description), "ts": int(time.time())}
        sentinel.write_text(json.dumps(record), encoding="utf-8")
        return True
    except OSError:
        return False


def _read_payload_sentinel(project_dir: Path) -> dict[str, Any] | None:
    sentinel = project_dir / _PAYLOAD_SENTINEL_REL
    if not sentinel.exists():
        return None
    try:
        record = json.loads(sentinel.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict) or "digest" not in record or "ts" not in record:
        return None
    return record


def check_payload_sentinel(project_dir: Path, title: str, description: str) -> str:
    """Evaluate the payload-keyed gate for ``(title, description)``.

    Returns one of:
        - ``"ok"``: a fresh sentinel exists and its digest matches this payload.
        - ``"missing"``: no payload sentinel exists (or it is unreadable).
        - ``"stale"``: the sentinel is older than ``_SENTINEL_MAX_AGE_S``.
        - ``"mismatch"``: the sentinel is fresh but was recorded for a
          different ``(title, description)`` payload.
    """
    record = _read_payload_sentinel(project_dir)
    if record is None:
        return "missing"
    try:
        ts = float(record["ts"])
    except (TypeError, ValueError):
        return "missing"
    age = time.time() - ts
    if age < 0 or age > _SENTINEL_MAX_AGE_S:
        return "stale"
    if record.get("digest") != compute_payload_digest(title, description):
        return "mismatch"
    return "ok"


def validate_missing_envelope(title: str, description: str) -> dict[str, Any]:
    """Return the Agent-Gateway ``validate_missing`` refusal envelope.

    The envelope shape follows the spec in
    ``docs/architecture/gateway-envelope.md``.  Clients branch on ``ok`` +
    ``code``; the ``use`` / ``args`` fields name the tool to call with which
    arguments to satisfy the gate.
    """
    return {
        "ok": False,
        "code": "validate_missing",
        "gate": "linear_write_validation",
        "use": "docs_validate_linear_issue",
        "args": {"title": title, "description": description},
        "hint": (
            "Call docs_validate_linear_issue(title, description) and confirm "
            "agent_ready=true before calling save_issue. "
            "The sentinel expires after 30 minutes."
        ),
        "bypass_env": "TAPPS_LINEAR_SKIP_VALIDATE",
        "logged_to": ".tapps-mcp/.bypass-log.jsonl",
    }


def payload_mismatch_envelope(title: str, description: str) -> dict[str, Any]:
    """Return the ``payload_mismatch`` refusal envelope (TAP-6924).

    Fired when a fresh validation exists but was recorded for a different
    ``(title, description)`` payload than the one handed to
    ``docs_save_linear_issue``. Distinct from ``validate_missing`` so the
    agent (and logs) can tell "never validated" apart from "validated the
    wrong thing".
    """
    return {
        "ok": False,
        "code": "payload_mismatch",
        "gate": "linear_write_validation",
        "use": "docs_validate_linear_issue",
        "args": {"title": title, "description": description},
        "hint": (
            "The title/description passed to docs_save_linear_issue do not match "
            "the payload docs_validate_linear_issue last approved. Call "
            "docs_validate_linear_issue with this exact title and description, "
            "confirm agent_ready=true, then retry docs_save_linear_issue."
        ),
        "bypass_env": "TAPPS_LINEAR_SKIP_VALIDATE",
        "logged_to": ".tapps-mcp/.bypass-log.jsonl",
    }


def gate_linear_save(
    project_dir: Path,
    title: str,
    description: str,
) -> dict[str, Any] | None:
    """Check the linear-write gate (TAP-6924: keyed on payload, not just time).

    Returns:
        ``None`` when the gate passes — the caller should proceed to
        ``mcp__plugin_linear_linear__save_issue``.
        A ``validate_missing`` refusal envelope when there is no fresh
        validation at all.
        A ``payload_mismatch`` refusal envelope when a fresh validation
        exists but was recorded for a different payload.

    Bypass:
        Set ``TAPPS_LINEAR_SKIP_VALIDATE=1`` in the environment to skip the
        sentinel check.  Bypasses are logged by the bash hook;
        the server-side path just passes through silently.
    """
    if os.environ.get("TAPPS_LINEAR_SKIP_VALIDATE"):
        return None
    status = check_payload_sentinel(project_dir, title, description)
    if status == "mismatch":
        return payload_mismatch_envelope(title, description)
    if status != "ok":
        return validate_missing_envelope(title, description)
    return None

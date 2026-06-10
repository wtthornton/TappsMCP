"""TAP-2009: Server-side Linear write gate — sentinel I/O and refusal envelope.

``docs_validate_linear_issue`` writes ``.tapps-mcp/.linear-validate-sentinel``
when ``agent_ready=true``. ``docs_save_linear_issue`` reads that sentinel
(within ``_SENTINEL_MAX_AGE_S``, matching the PreToolUse hook) before allowing
a Linear ``save_issue`` call to proceed.

Claude Code's ``tapps-post-docs-validate.sh`` PostToolUse hook writes the same
file for defence-in-depth; the server-side write is the primary path for clients
without PostToolUse hooks (Cursor, VS Code, CI).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

# Sentinel TTL — must match tapps-pre-linear-write.sh
_SENTINEL_MAX_AGE_S: int = 1800  # 30 minutes

# Sentinel path relative to project root (written by tapps-post-docs-validate.sh)
_SENTINEL_REL: str = ".tapps-mcp/.linear-validate-sentinel"


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


def gate_linear_save(
    project_dir: Path,
    title: str,
    description: str,
) -> dict[str, Any] | None:
    """Check the linear-write gate.

    Returns:
        ``None`` when the gate passes — the caller should proceed to
        ``mcp__plugin_linear_linear__save_issue``.
        A ``validate_missing`` refusal envelope when the gate fires.

    Bypass:
        Set ``TAPPS_LINEAR_SKIP_VALIDATE=1`` in the environment to skip the
        sentinel check.  Bypasses are logged by the bash hook;
        the server-side path just passes through silently.
    """
    if os.environ.get("TAPPS_LINEAR_SKIP_VALIDATE"):
        return None
    if not check_validate_sentinel(project_dir):
        return validate_missing_envelope(title, description)
    return None

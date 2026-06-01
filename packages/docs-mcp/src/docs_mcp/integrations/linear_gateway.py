"""TAP-2009: Server-side refusal envelope for the Linear write gate.

Checks that ``docs_validate_linear_issue`` has been called recently (within
``_SENTINEL_MAX_AGE_S`` seconds, matching the PreToolUse hook) before allowing
a Linear ``save_issue`` call to proceed.

This module reads the file-sentinel written by
``.claude/hooks/tapps-post-docs-validate.sh`` and either signals that the
gate passes (returning ``None``) or produces the standard ``validate_missing``
refusal envelope for the caller to surface.

This provides defence-in-depth alongside the bash hook: when the hook is
absent (other MCP clients, CI, read-only Claude Code configs) the server-side
Python check still enforces the contract.
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

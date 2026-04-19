"""Stable agent identity persisted to ``.tapps-mcp/agent.id``.

Replaces the PID-based fallback (``f"agent-{os.getpid()}"``) that changed on
every MCP server restart, causing Hive memory attribution drift and duplicate
agent registrations.

Final agent_id shape::

    f"{project_slug}-{uuid_hex_8}"

where ``project_slug`` is ``settings.memory.project_id`` when set, else the
project root directory name; and ``uuid_hex_8`` is the first 8 hex chars of a
UUID4 persisted to ``{project_root}/.tapps-mcp/agent.id`` on first call.

See TAP-518.
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from tapps_core.config.settings import TappsMCPSettings

logger = structlog.get_logger(__name__)

_AGENT_ID_RELATIVE_PATH = Path(".tapps-mcp") / "agent.id"
_UUID_SHORT_LEN = 8
_SLUG_INVALID_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def _slugify(value: str) -> str:
    """Reduce a string to a safe agent-id prefix (alnum/dash/underscore)."""
    cleaned = _SLUG_INVALID_RE.sub("-", value).strip("-_")
    return cleaned or "tapps-mcp"


def _project_slug(settings: TappsMCPSettings) -> str:
    """Derive the project-name prefix for the agent id.

    Prefers ``settings.memory.project_id`` (the registered tapps-brain slug);
    falls back to the project root directory name.
    """
    memory = getattr(settings, "memory", None)
    project_id = str(getattr(memory, "project_id", "") or "").strip()
    if project_id:
        return _slugify(project_id)
    root = Path(getattr(settings, "project_root", Path.cwd()))
    return _slugify(root.name)


def _read_uuid(path: Path) -> str | None:
    """Return the persisted UUID hex (stripped), or None if unreadable/empty."""
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return raw or None


def _write_uuid(path: Path, value: str) -> None:
    """Persist *value* to *path*, creating the parent directory as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value + "\n", encoding="utf-8")


def get_stable_agent_id(settings: TappsMCPSettings) -> str:
    """Return the stable agent id, honouring ``CLAUDE_AGENT_ID`` overrides.

    Precedence:

    1. ``CLAUDE_AGENT_ID`` environment variable (unchanged from prior behaviour).
    2. ``f"{project_slug}-{uuid8}"`` with UUID persisted to
       ``{project_root}/.tapps-mcp/agent.id``.

    The file is created on first call. Subsequent calls read the same UUID so
    the agent id survives MCP server restarts.
    """
    override = os.environ.get("CLAUDE_AGENT_ID", "").strip()
    if override:
        return override

    project_root = Path(getattr(settings, "project_root", Path.cwd()))
    id_path = project_root / _AGENT_ID_RELATIVE_PATH

    uuid_hex = _read_uuid(id_path)
    if uuid_hex is None:
        uuid_hex = uuid.uuid4().hex
        try:
            _write_uuid(id_path, uuid_hex)
            logger.info(
                "agent_identity.created",
                path=str(id_path),
            )
        except OSError as exc:
            # Read-only FS or permission denied — fall back to an in-memory
            # UUID so the caller still gets a non-PID identifier for this
            # process. It won't persist, but it won't collide with other
            # concurrent sessions either.
            logger.warning(
                "agent_identity.persist_failed",
                path=str(id_path),
                error=str(exc),
            )

    short = uuid_hex[:_UUID_SHORT_LEN]
    return f"{_project_slug(settings)}-{short}"


__all__ = ["get_stable_agent_id"]

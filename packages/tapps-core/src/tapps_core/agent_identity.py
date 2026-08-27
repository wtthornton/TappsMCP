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
import time
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

# TAP-5893: a racing first-caller can observe the winner's ``agent.id`` in the
# microsecond window between ``O_CREAT | O_EXCL`` creating it and the winner
# writing its bytes. Re-read on a short bounded backoff rather than minting a
# divergent id.
_CREATE_RACE_ATTEMPTS = 5
_CREATE_RACE_BACKOFF_SECONDS = 0.01


def is_real_writable_root(project_root: object) -> bool:
    """Return True only when *project_root* is a real, absolute filesystem path.

    TAP-4573 guard. Production callers always resolve ``project_root`` to an
    absolute path (explicit arg, ``TAPPS_MCP_PROJECT_ROOT`` env, or ``cwd``).
    A bare ``MagicMock()`` coerces via ``os.fspath`` to the *relative* string
    ``MagicMock/mock.project_root/<id>`` (verified empirically), so ~70 test
    call sites that pass unspec'd mocks were causing real ``mkdir`` trees under
    the pytest CWD (the repo root). Rejecting non-absolute / non-coercible
    roots blocks that leak at the single production write path without touching
    the tests, and is a no-op for every real deployment (roots are absolute).
    """
    try:
        raw = os.fspath(project_root)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return False
    return Path(raw).is_absolute()


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


def _write_uuid(path: Path, value: str) -> bool:
    """Create *path* holding *value*, atomically and only when it is absent.

    TAP-5893 / TAP-6081. ``os.open`` with ``O_CREAT | O_EXCL`` is the POSIX
    atomic create-if-absent: exactly one concurrent caller creates the file and
    every other one raises :exc:`FileExistsError`. A plain ``write_text``
    read-then-write let N first-callers each mint and persist their own UUID,
    last writer winning while the losers kept ids that no longer matched disk.

    ``os.replace`` (the primitive behind :class:`AtomicJsonCache`) is the wrong
    tool here: it publishes unconditionally, so racing callers would still
    clobber each other's id. Exclusive creation is the stronger guarantee, and
    the file is written once and never rewritten, so there is no torn-rewrite
    case left for a temp-and-replace to protect.

    Returns:
        ``True`` when this caller created the file, ``False`` when another
        caller won the race and its id should be read instead.

    Raises:
        OSError: the parent directory or the file could not be created
            (read-only filesystem, EACCES/EPERM). The caller falls back to a
            non-persisted id.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(value + "\n")
    return True


def _await_persisted_uuid(path: Path) -> str | None:
    """Re-read *path* on a short backoff, for the caller that lost the race.

    Returns the winner's UUID, or ``None`` if it never became readable within
    :data:`_CREATE_RACE_ATTEMPTS` tries (the file exists but stayed empty or
    unreadable).
    """
    for attempt in range(_CREATE_RACE_ATTEMPTS):
        existing = _read_uuid(path)
        if existing is not None:
            return existing
        time.sleep(_CREATE_RACE_BACKOFF_SECONDS * (attempt + 1))
    return None


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

    raw_root = getattr(settings, "project_root", Path.cwd())

    # TAP-4573: never mkdir/write under a non-real (mock- or relative-coerced)
    # project_root. A bare MagicMock() coerces to a relative "MagicMock/..."
    # path, so writing it would create a real tree in the pytest CWD. Skip the
    # persistence attempt but still return a valid in-memory agent id.
    if not is_real_writable_root(raw_root):
        return f"{_project_slug(settings)}-{uuid.uuid4().hex[:_UUID_SHORT_LEN]}"

    project_root = Path(raw_root)
    id_path = project_root / _AGENT_ID_RELATIVE_PATH

    uuid_hex = _read_uuid(id_path)
    if uuid_hex is None:
        minted = uuid.uuid4().hex
        try:
            created = _write_uuid(id_path, minted)
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
            uuid_hex = minted
        else:
            if created:
                uuid_hex = minted
                logger.info(
                    "agent_identity.created",
                    path=str(id_path),
                )
            else:
                # TAP-5893: another first-caller created the file between our
                # read and our create. Converge on its id instead of persisting
                # a second one.
                uuid_hex = _await_persisted_uuid(id_path)
                if uuid_hex is None:
                    logger.warning(
                        "agent_identity.race_read_failed",
                        path=str(id_path),
                    )
                    uuid_hex = minted

    short = uuid_hex[:_UUID_SHORT_LEN]
    return f"{_project_slug(settings)}-{short}"


__all__ = ["get_stable_agent_id", "is_real_writable_root"]

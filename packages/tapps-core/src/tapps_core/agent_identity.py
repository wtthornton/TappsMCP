"""Stable, logical agent identity (Ruling 9, TAP-6701).

Replaces both the PID-based fallback (``f"agent-{os.getpid()}"``, which
changed on every MCP server restart) and the later per-checkout
``f"{project_slug}-{uuid_hex_8}"`` shape (TAP-518/TAP-5893), which minted a
distinct id — persisted to ``{project_root}/.tapps-mcp/agent.id`` — for every
git worktree of the same project. Ruling 9 requires a *logical* name: two
worktrees of the same project must resolve to the same ``X-Agent-Id`` so
tapps-brain attributes their writes to one tenant instead of fragmenting
memory across per-checkout hashes.

Final agent_id resolution, no filesystem I/O:

1. ``CLAUDE_AGENT_ID`` environment variable override.
2. ``settings.memory.brain_project_id`` (the registered tapps-brain slug,
   also sent as ``X-Project-Id`` — see :mod:`tapps_core.brain_auth`).
3. ``settings.memory.project_id`` (auto-derived from ``brain_project_id``
   when either is set; kept as a fallback for the disagreement case).
4. The project root directory name, as a last resort when neither is
   configured — best-effort only; distinct worktree directory names still
   diverge here, which is why (2)/(3) are the ones a multi-worktree project
   should configure in ``.tapps-mcp.yaml``.

``.tapps-mcp/agent.id`` is no longer read, written, or consulted by this
resolution. ``_write_uuid`` stays in this module — it is a generic atomic
create-if-absent primitive independently exercised by
``test_shared_state_atomic_writers.py`` (TAP-6081) and its own race test
below — but nothing in this module calls it anymore.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tapps_core.config.settings import TappsMCPSettings

_SLUG_INVALID_RE = re.compile(r"[^a-zA-Z0-9_-]+")


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
    """Derive the logical project slug the agent id is built from (Ruling 9).

    Prefers ``settings.memory.brain_project_id`` — the field actually sent as
    the ``X-Project-Id`` header (``brain_auth.build_brain_headers``) — over
    ``settings.memory.project_id`` so the two agree with what the brain
    already associates the write with. Falls back to the project root
    directory name only when neither is configured.
    """
    memory = getattr(settings, "memory", None)
    brain_project_id = str(getattr(memory, "brain_project_id", "") or "").strip()
    if brain_project_id:
        return _slugify(brain_project_id)
    project_id = str(getattr(memory, "project_id", "") or "").strip()
    if project_id:
        return _slugify(project_id)
    root = Path(getattr(settings, "project_root", Path.cwd()))
    return _slugify(root.name)


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


def get_stable_agent_id(settings: TappsMCPSettings) -> str:
    """Return the stable, logical agent id (Ruling 9), honouring ``CLAUDE_AGENT_ID``.

    Precedence:

    1. ``CLAUDE_AGENT_ID`` environment variable.
    2. :func:`_project_slug` — ``brain_project_id``, then ``project_id``,
       then the project root directory name.

    Pure and deterministic: no filesystem I/O, no persisted per-checkout
    state. Two worktrees of the same project sharing the same
    ``brain_project_id``/``project_id`` resolve to the *same* id — the
    cross-checkout invariant TAP-518's old uuid8-suffix design violated.
    """
    override = os.environ.get("CLAUDE_AGENT_ID", "").strip()
    if override:
        return override
    return _project_slug(settings)


__all__ = ["get_stable_agent_id", "is_real_writable_root"]

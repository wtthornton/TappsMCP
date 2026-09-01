"""Ownership guard, archive/prune and atomic promote for handoff writes (TAP-6871).

``.tapps-mcp/session-handoff.md`` used to be a blind truncating write: whoever
saved last replaced every other concurrent program's cold-start channel, and
nothing in the artifact let the read side notice. This module supplies the two
halves of the fix.

* **Identity from the artifact.** The incumbent is read before it is replaced
  and fingerprinted as ``{program, updated, linear_p0, title}``. A write whose
  identity differs from a *recent* incumbent is ``foreign``; an incumbent whose
  identity cannot be established at all reports ``"unknown"`` rather than
  passing silently as "no conflict".
* **Never a lossy or half-written replacement.** The incumbent is archived on
  every write, conflict or not, and the replacement is promoted with
  ``os.replace`` from a temp file in the *same* directory, so the file at the
  handoff path is always one complete document.

Identity is the ``**Program:**`` header (TAP-6872), never the ``# `` title. The
title is still fingerprinted and reported, because it is what names the other
program in a refusal, but it does not decide: two programs under one generic
heading are different programs, and one program that renumbers its heading
between saves is still itself.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import structlog

from tapps_mcp.tools.handoff_schema import handoff_path, parse_handoff_markdown

_logger = structlog.get_logger(__name__)

ARCHIVE_KEEP = 20
"""How many archived handoffs survive a prune, newest first."""

_ARCHIVE_RELATIVE = Path(".tapps-mcp") / "handoffs" / "archive"
_DEFAULT_ARCHIVE_LABEL = "default"

# The de-facto program name in every handoff this repo has written. ``## Done``
# does not match: the marker must be followed by whitespace, not another ``#``.
_TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)

ConflictMode = Literal["off", "warn", "block"]
Foreign = bool | Literal["unknown"]


def handoff_archive_dir(project_root: Path) -> Path:
    """The single site that names the handoff archive directory."""
    return project_root / _ARCHIVE_RELATIVE


@dataclass(frozen=True)
class HandoffIdentity:
    """What a handoff file says about who owns it."""

    program: str | None = None
    title: str | None = None
    updated: datetime | None = None
    linear_p0: str | None = None

    @property
    def owner(self) -> str:
        """The best available name for whoever wrote this handoff."""
        return self.program or self.title or "unknown"

    def as_payload(self) -> dict[str, Any]:
        updated = (
            self.updated.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            if self.updated is not None
            else None
        )
        return {
            "program": self.program,
            "title": self.title,
            "updated": updated,
            "linear_p0": self.linear_p0,
        }


@dataclass
class HandoffGuardResult:
    """Outcome of a guarded handoff write."""

    path: Path
    conflict: dict[str, Any] | None = None


def conflict_status(payload: dict[str, Any] | None) -> str:
    """Classify a guard conflict report for a response envelope.

    The counterpart of
    :func:`~tapps_mcp.tools.handoff_write.best_effort_status` for the third
    thing :class:`~tapps_mcp.tools.handoff_write.HandoffWriteResult` carries.
    A conflict is not a best-effort sub-result — the write completed either
    way — so it gets its own vocabulary rather than being forced into
    ``ok``/``skipped``/``failed``:

    * ``off`` — ``handoff_conflict_mode=off``; the guard archived the incumbent
      and deliberately reported nothing. Absence of a signal, not a clean write.
    * ``clear`` — the guard ran and found no foreign incumbent.
    * ``unknown`` — an incumbent was replaced whose ownership could not be
      established (see :func:`classify_foreign`). Every handoff written before
      TAP-6872 lacks the header, so this is the ordinary legacy case and is
      reported without being treated as a displacement.
    * ``overwritten`` — a *named* different program's recent handoff was
      archived and replaced. The only value that warrants degrading the
      envelope, and the only one ``block`` mode refuses on.
    """
    if not payload:
        return "off"
    foreign = payload.get("foreign")
    if foreign is True:
        return "overwritten"
    if foreign is False:
        return "clear"
    return "unknown"


def conflict_advisory(payload: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    """Classify a conflict report and say what the agent should do about it.

    Returns ``(status, warnings, next_steps)``. Both lists are empty unless the
    status is ``overwritten``: that is the one value naming a specific program
    whose recent handoff this write archived, so it is the one value that has
    something to tell the agent.

    The prose is built from the same payload the response carries under
    ``conflict``, so the sentence and the machine-readable record can never
    disagree. It lives here rather than at the response site because the shape
    of the payload is this module's to know.
    """
    status = conflict_status(payload)
    if status != "overwritten":
        return status, [], []
    previous = payload.get("previous") or {}
    program = previous.get("program") or "an unidentified program"
    archived_to = payload.get("archived_to")
    where = f" — its copy is at {archived_to}" if archived_to else ""
    forced = " (forced)" if payload.get("forced") else ""
    return (
        status,
        [f"Replaced the handoff of {program}{forced}{where}"],
        [
            "Confirm that program is not still running before you continue; "
            "restore its handoff from the archived copy if it is."
        ],
    )


class HandoffOwnerConflictError(Exception):
    """A ``block``-mode write would have overwritten another program's handoff.

    Carries an Agent Gateway refusal envelope (docs/architecture/gateway-envelope.md)
    so the MCP and CLI surfaces hand the agent a machine-readable ``code`` and the
    exact retry rather than a stringified traceback.
    """

    def __init__(self, path: Path, previous: HandoffIdentity, slot: str | None) -> None:
        self.path = path
        self.previous = previous
        hint = (
            f"{path} belongs to {previous.owner!r} (title: {previous.title!r}, "
            f"updated {previous.as_payload()['updated']}). Refusing to overwrite it "
            "under handoff_conflict_mode=block. Retry with "
            'slot="<your-program>" to write your own handoff, or pass force=true '
            "to overwrite it (the incumbent is archived first either way)."
        )
        self.envelope: dict[str, Any] = {
            "ok": False,
            "code": "handoff_owner_conflict",
            "gate": "handoff_ownership_guard",
            "hint": hint,
            "extra": {
                "path": str(path),
                "slot": slot,
                "previous": previous.as_payload(),
            },
        }
        super().__init__(hint)


def identity_from_markdown(markdown: str) -> HandoffIdentity:
    """Fingerprint a handoff body: program, title, updated, Linear P0."""
    doc = parse_handoff_markdown(markdown)
    title_match = _TITLE_RE.search(markdown)
    return HandoffIdentity(
        program=doc.program,
        title=title_match.group(1).strip() if title_match else None,
        updated=doc.updated,
        linear_p0=doc.linear_p0,
    )


def read_handoff_identity(path: Path) -> HandoffIdentity | None:
    """Fingerprint the file at *path*, or ``None`` when there is nothing there.

    A file that is not valid UTF-8 is not a handoff anybody wrote through this
    tool, but it is still somebody's bytes: it comes back as an identity that
    states nothing, which classifies as ``"unknown"`` and is archived rather
    than silently replaced.
    """
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        _logger.warning("handoff_previous_undecodable", path=str(path))
        return HandoffIdentity()
    return identity_from_markdown(text)


def classify_foreign(
    previous: HandoffIdentity | None,
    incoming: HandoffIdentity,
    *,
    window_hours: int,
    now: datetime | None = None,
) -> Foreign:
    """Decide whether *incoming* would overwrite somebody else's live handoff.

    Three answers, and the middle one is the point:

    * ``False`` — both sides state the same ``**Program:**``, or the incumbent
      is older than the conflict window and nobody is still reading it.
    * ``True`` — both sides state a program, they differ, and the incumbent is
      recent. This is the only answer ``block`` mode refuses on.
    * ``"unknown"`` — the question cannot be answered: either side is missing
      the header, or the incumbent has no ``Updated`` line so the window cannot
      be applied. Reported and archived, never blocked; every handoff written
      before TAP-6872 lacks the header, and none of them may start refusing
      writes.

    Identity is the header alone. Falling back to a title compare when it is
    absent looks like a safe default and is not: it answers ``False`` for two
    different programs that share a generic heading — the exact silent
    overwrite this guard exists to stop — and ``True`` for one program that put
    a round number in its own. ``"unknown"`` and "the titles happened to match"
    are different answers, so they get different values.
    """
    if previous is None:
        return False
    if previous.program is None or incoming.program is None:
        return "unknown"
    if previous.program == incoming.program:
        return False
    if previous.updated is None:
        return "unknown"
    clock = now if now is not None else datetime.now(UTC)
    if clock - previous.updated > timedelta(hours=window_hours):
        return False
    return True


def _archive_target(archive_dir: Path, slot: str | None) -> Path:
    """``<UTC>-<slot|default>.md``, disambiguated so an archive never clobbers one.

    Microsecond precision plus a ``+n`` counter: two writes inside the same
    second are exactly the case the archive exists to make recoverable, so the
    second one must not overwrite the first.
    """
    label = slot or _DEFAULT_ARCHIVE_LABEL
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    candidate = archive_dir / f"{stamp}-{label}.md"
    counter = 1
    while candidate.exists():
        candidate = archive_dir / f"{stamp}+{counter}-{label}.md"
        counter += 1
    return candidate


def archive_incumbent(project_root: Path, path: Path, slot: str | None) -> Path:
    """Move the incumbent aside by rename, before anything else is written.

    A rename rather than a copy: the incumbent is never unlinked while its
    replacement is only half-written, and the move costs one inode update.
    """
    archive_dir = handoff_archive_dir(project_root)
    archive_dir.mkdir(parents=True, exist_ok=True)
    target = _archive_target(archive_dir, slot)
    # ``Path.replace`` *is* ``os.replace(self, target)`` — same atomic syscall,
    # spelled the way this repo's other atomic writers spell it
    # (tapps_core/adaptive/persistence.py). Not a substitution for ``os.rename``,
    # which raises FileExistsError on Windows when the target exists.
    path.replace(target)
    return target


def prune_archive(archive_dir: Path, keep: int = ARCHIVE_KEEP) -> list[Path]:
    """Delete all but the *keep* newest archives, returning what was removed.

    Names are UTC-prefixed, so a reverse lexicographic sort is a reverse
    chronological sort without stat-ing every file.
    """
    if not archive_dir.is_dir():
        return []
    archives = sorted(archive_dir.glob("*.md"), reverse=True)
    pruned = archives[keep:]
    for path in pruned:
        path.unlink()
    return pruned


def _write_temp(path: Path, markdown: str) -> Path:
    """Write *markdown* to a durable temp file in *path*'s own directory.

    Same directory because the promote raises ``OSError(EXDEV)`` across
    filesystems rather than degrading to a non-atomic copy — the co-location is
    what keeps the promote from raising, not what makes it atomic. ``delete=False``
    because the file must outlive the context manager: it is promoted, not read.
    """
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(markdown)
        handle.flush()
        os.fsync(handle.fileno())
        temp_name = handle.name
    return Path(temp_name)


def _fsync_directory(directory: Path) -> None:
    """Make the rename itself durable, not just the bytes it points at.

    POSIX only: Windows cannot open a directory for reading, and offers no
    equivalent call.
    """
    if os.name == "nt":  # pragma: no cover - POSIX-only durability step
        return
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _restore_after_failed_promote(
    temp: Path,
    path: Path,
    archived_to: Path | None,
) -> None:
    """Undo a half-finished write so the handoff path never holds a partial file.

    Called only from the failure path, and never swallows anything: the original
    ``OSError`` is re-raised by the caller, and a failure to restore propagates
    on top of it rather than being hidden.
    """
    if temp.exists():
        temp.unlink()
    if archived_to is not None and archived_to.is_file() and not path.exists():
        archived_to.replace(path)


def resolve_conflict_settings(
    project_root: Path,
    mode: ConflictMode | None,
    window_hours: int | None,
) -> tuple[ConflictMode, int]:
    """Fill in whichever of mode / window the caller did not state."""
    if mode is not None and window_hours is not None:
        return mode, window_hours
    from tapps_core.config.settings import load_settings

    settings = load_settings(project_root)
    return (
        mode if mode is not None else settings.handoff_conflict_mode,
        window_hours if window_hours is not None else settings.handoff_conflict_window_hours,
    )


def guarded_write(
    project_root: Path,
    markdown: str,
    *,
    slot: str | None = None,
    owner: str | None = None,
    mode: ConflictMode | None = None,
    window_hours: int | None = None,
    force: bool = False,
) -> HandoffGuardResult:
    """Read the incumbent, archive it, then promote *markdown* atomically.

    ``owner`` states the incoming program when the body's ``**Program:**``
    header does not, or overrides it when it does (spec §2.2). It substitutes
    for one field of the incoming fingerprint and nothing else: the comparison
    in :func:`classify_foreign`, the archive, and the promote are unchanged.

    Raises:
        HandoffOwnerConflictError: under ``block`` when the incumbent is a
            recent handoff belonging to a different program and ``force`` is
            not set. Nothing is touched: the incumbent stays byte-identical and
            no archive is written.
    """
    resolved_mode, resolved_window = resolve_conflict_settings(project_root, mode, window_hours)
    path = handoff_path(project_root, slot)
    path.parent.mkdir(parents=True, exist_ok=True)

    previous = read_handoff_identity(path)
    incoming = identity_from_markdown(markdown)
    if owner is not None:
        incoming = replace(incoming, program=owner)
    foreign = classify_foreign(
        previous,
        incoming,
        window_hours=resolved_window,
    )

    # ``previous is not None`` is implied by ``foreign is True``; stating it
    # keeps the narrowing in the type system rather than in an ``assert`` that
    # ``python -O`` would strip.
    if resolved_mode == "block" and foreign is True and previous is not None and not force:
        raise HandoffOwnerConflictError(path, previous, slot)

    archived_to: Path | None = None
    if previous is not None:
        archived_to = archive_incumbent(project_root, path, slot)
        prune_archive(handoff_archive_dir(project_root))

    temp = _write_temp(path, markdown)
    try:
        temp.replace(path)
    except OSError:
        _restore_after_failed_promote(temp, path, archived_to)
        raise
    _fsync_directory(path.parent)

    if resolved_mode == "off":
        # Archive only, no signal — the setting's whole purpose.
        return HandoffGuardResult(path=path)

    conflict: dict[str, Any] = {
        "foreign": foreign,
        "mode": resolved_mode,
        "window_hours": resolved_window,
        "forced": force and foreign is True,
        "previous": previous.as_payload() if previous is not None else None,
        "archived_to": str(archived_to) if archived_to is not None else None,
    }
    if foreign is not False:
        _logger.warning(
            "handoff_owner_conflict",
            path=str(path),
            foreign=foreign,
            archived_to=conflict["archived_to"],
        )
    return HandoffGuardResult(path=path, conflict=conflict)


__all__ = [
    "ARCHIVE_KEEP",
    "ConflictMode",
    "Foreign",
    "HandoffGuardResult",
    "HandoffIdentity",
    "HandoffOwnerConflictError",
    "archive_incumbent",
    "classify_foreign",
    "conflict_advisory",
    "conflict_status",
    "guarded_write",
    "handoff_archive_dir",
    "identity_from_markdown",
    "prune_archive",
    "read_handoff_identity",
    "resolve_conflict_settings",
]

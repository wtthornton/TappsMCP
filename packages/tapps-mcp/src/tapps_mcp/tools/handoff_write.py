"""Atomic session handoff write: file + brain mirror + schema lint (TAP-3792)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC
from pathlib import Path
from typing import Any

import structlog

from tapps_mcp.tools.handoff_guard import (
    ConflictMode,
    HandoffGuardResult,
    guarded_write,
)
from tapps_mcp.tools.handoff_schema import (
    SESSION_HANDOFF_MEMORY_KEY,
    HandoffDocument,
    HandoffLintResult,
    empty_parse_error,
    handoff_sections_from_doc,
    handoff_size_report,
    lint_handoff,
    parse_handoff_markdown,
)

_logger = structlog.get_logger(__name__)

_HANDOFF_TAGS = ["handoff", "cross-session"]


class HandoffWriteError(Exception):
    """Raised when handoff schema lint fails with blocking errors."""

    def __init__(self, errors: list[str], warnings: list[str] | None = None) -> None:
        self.errors = errors
        self.warnings = warnings or []
        super().__init__("; ".join(errors))


@dataclass
class HandoffWriteResult:
    """Outcome of a handoff write operation."""

    file_path: str
    lint: HandoffLintResult
    doc: HandoffDocument
    brain_mirror: dict[str, Any] | None = None
    session_end: dict[str, Any] | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    conflict: dict[str, Any] | None = None


def _git_context_sync(project_root: Path) -> dict[str, str]:
    """Best-effort git sha/branch for handoff metadata."""
    from tapps_mcp.tools.subprocess_runner import run_command

    ctx: dict[str, str] = {}
    try:
        branch = run_command(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(project_root),
            timeout=5,
        )
        if branch.returncode == 0:
            ctx["git_branch"] = branch.stdout.strip()
        sha = run_command(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(project_root),
            timeout=5,
        )
        if sha.returncode == 0:
            ctx["git_sha"] = sha.stdout.strip()
    except (OSError, RuntimeError, ValueError) as exc:
        _logger.debug("handoff_git_context_failed", error=str(exc))
    return ctx


def build_handoff_metadata(doc: HandoffDocument, git_ctx: dict[str, str]) -> dict[str, Any]:
    """Structured metadata attached to the brain mirror entry."""
    meta: dict[str, Any] = {"handoff_sections": handoff_sections_from_doc(doc)}
    if doc.updated is not None:
        meta["updated_at"] = doc.updated.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    if doc.linear_p0:
        meta["linear_p0"] = doc.linear_p0
    meta.update(git_ctx)
    return meta


async def mirror_handoff_to_brain(
    markdown: str,
    metadata: dict[str, str],
    *,
    bridge: Any | None = None,
) -> dict[str, Any]:
    """Mirror full handoff markdown to brain under ``session-handoff`` key."""
    # The cap is a known constant, so an over-cap body is decidable here rather
    # than something to learn from a bad_request after the round-trip. Deciding
    # it up front means the caller always gets the size, the cap and the section
    # to shorten — including when the bridge is unreachable and would have
    # queued the doomed value instead of rejecting it (TAP-6444).
    size = handoff_size_report(markdown)
    if size.over:
        return {
            "success": False,
            "error": "value_over_cap",
            "detail": size.message(),
            "value_length": size.length,
            "max_value_length": size.cap,
            "largest_section": size.largest_section,
        }

    if bridge is None:
        from tapps_core.brain_bridge import BRAIN_PROFILE_SERVER, create_brain_bridge
        from tapps_core.config.settings import load_settings

        settings = load_settings()
        bridge = create_brain_bridge(settings, default_profile=BRAIN_PROFILE_SERVER)

    if bridge is None:
        return {"success": False, "skipped": True, "reason": "bridge_unavailable"}

    details_json = json.dumps(metadata) if metadata else ""
    kwargs: dict[str, Any] = {}
    if details_json:
        kwargs["details_json"] = details_json

    try:
        result = await bridge.save(
            SESSION_HANDOFF_MEMORY_KEY,
            markdown,
            tier="context",
            tags=_HANDOFF_TAGS,
            **kwargs,
        )
    finally:
        if hasattr(bridge, "close"):
            bridge.close()

    payload: dict[str, Any] = (
        result if isinstance(result, dict) else {"key": SESSION_HANDOFF_MEMORY_KEY}
    )
    # Sizes travel with the payload so a rejection is self-explaining. The
    # brain caps a memory value, and the handoff template routinely produces
    # bodies past it; without these the caller sees only "bad_request".
    payload.setdefault("value_length", len(markdown))
    payload.setdefault("max_value_length", size.cap)
    payload.setdefault("success", "error" not in payload)
    return payload


def best_effort_status(payload: dict[str, Any] | None) -> str:
    """Classify a best-effort sub-result as ``ok``, ``skipped`` or ``failed``.

    ``skipped`` means the work was never attempted — typically no bridge was
    configured, an expected offline state rather than a failure. ``failed``
    means it was attempted and rejected, so whatever it promised does not
    exist even though the surrounding operation completed.

    Shared by the handoff's brain mirror and session-end results: both are
    documented best-effort, both surface outages in their result dict rather
    than raising, and both were previously embedded in a plain success
    envelope where a caller could not see they had failed (TAP-5656).
    """
    if payload is None or payload.get("skipped"):
        return "skipped"
    if payload.get("error") or payload.get("success") is False:
        return "failed"
    return "ok"


def write_handoff_file(
    project_root: Path,
    markdown: str,
    *,
    slot: str | None = None,
    conflict_mode: ConflictMode | None = None,
    conflict_window_hours: int | None = None,
    force: bool = False,
) -> HandoffGuardResult:
    """Persist canonical handoff markdown under ``.tapps-mcp/``.

    Delegates to :func:`~tapps_mcp.tools.handoff_guard.guarded_write`, which
    archives the incumbent and promotes the replacement with ``os.replace``.
    The blind ``write_text`` this replaced could both silently destroy another
    program's handoff and, on a crash mid-write, leave a truncated one
    (TAP-6871).
    """
    return guarded_write(
        project_root,
        markdown,
        slot=slot,
        mode=conflict_mode,
        window_hours=conflict_window_hours,
        force=force,
    )


async def write_handoff(
    project_root: Path,
    markdown: str,
    *,
    mirror_brain: bool = True,
    run_session_end: bool = False,
    session_start_iso: str = "",
    fail_on_lint_errors: bool = True,
    conflict_mode: ConflictMode | None = None,
    conflict_window_hours: int | None = None,
    force: bool = False,
) -> HandoffWriteResult:
    """Write handoff file, optionally mirror to brain and close session lifecycle."""
    doc = parse_handoff_markdown(markdown)
    lint = lint_handoff(doc)
    # A zero-section parse is refused whatever ``fail_on_lint_errors`` says:
    # there is nothing to persist, and writing it would replace the previous
    # handoff with a file continue-session reads back as empty (TAP-6493).
    if empty_parse_error(doc) is not None:
        raise HandoffWriteError(lint.errors, lint.warnings)
    if fail_on_lint_errors and not lint.ok:
        raise HandoffWriteError(lint.errors, lint.warnings)

    written = write_handoff_file(
        project_root,
        markdown,
        conflict_mode=conflict_mode,
        conflict_window_hours=conflict_window_hours,
        force=force,
    )
    git_ctx = _git_context_sync(project_root)
    metadata = build_handoff_metadata(doc, git_ctx)

    brain_result: dict[str, Any] | None = None
    if mirror_brain:
        brain_result = await mirror_handoff_to_brain(markdown, metadata)

    session_end_result: dict[str, Any] | None = None
    if run_session_end:
        from tapps_mcp.tools.session_end_helpers import (
            run_session_end as _run_session_end,
        )

        session_end_result = await _run_session_end(
            session_start_iso,
            project_root=project_root,
        )

    return HandoffWriteResult(
        file_path=str(written.path),
        lint=lint,
        doc=doc,
        brain_mirror=brain_result,
        session_end=session_end_result,
        metadata=metadata,
        conflict=written.conflict,
    )


def write_handoff_sync(
    project_root: Path,
    markdown: str,
    **kwargs: Any,
) -> HandoffWriteResult:
    """Synchronous wrapper for :func:`write_handoff`."""
    import asyncio

    return asyncio.run(write_handoff(project_root, markdown, **kwargs))


__all__ = [
    "HandoffWriteError",
    "HandoffWriteResult",
    "build_handoff_metadata",
    "mirror_handoff_to_brain",
    "write_handoff",
    "write_handoff_file",
    "write_handoff_sync",
]

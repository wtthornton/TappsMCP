"""Atomic session handoff write: file + brain mirror + schema lint (TAP-3792)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC
from pathlib import Path
from typing import Any

import structlog

from tapps_mcp.tools.handoff_schema import (
    SESSION_HANDOFF_MEMORY_KEY,
    HandoffDocument,
    HandoffLintResult,
    handoff_path,
    handoff_sections_from_doc,
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

    if isinstance(result, dict):
        return result
    return {"key": SESSION_HANDOFF_MEMORY_KEY, "success": True}


def write_handoff_file(project_root: Path, markdown: str) -> Path:
    """Persist canonical handoff markdown under ``.tapps-mcp/``."""
    path = handoff_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return path


async def write_handoff(
    project_root: Path,
    markdown: str,
    *,
    mirror_brain: bool = True,
    run_session_end: bool = False,
    session_start_iso: str = "",
    fail_on_lint_errors: bool = True,
) -> HandoffWriteResult:
    """Write handoff file, optionally mirror to brain and close session lifecycle."""
    doc = parse_handoff_markdown(markdown)
    lint = lint_handoff(doc)
    if fail_on_lint_errors and not lint.ok:
        raise HandoffWriteError(lint.errors, lint.warnings)

    path = write_handoff_file(project_root, markdown)
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
        file_path=str(path),
        lint=lint,
        doc=doc,
        brain_mirror=brain_result,
        session_end=session_end_result,
        metadata=metadata,
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

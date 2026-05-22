"""CLAUDE.md validation and section-aware smart-merge (TAP-2334).

Parallel to :mod:`agents_md`. Adds a top-level version stamp so
``tapps_upgrade`` can detect stale consumer CLAUDE.md files and trigger
the smart-merge that refreshes canonical TAPPS content while leaving
user customizations untouched.

Stamp shape::

    <!-- tapps-claude-version: X.Y.Z -->

The canonical TAPPS content lives inside a marker-wrapped block managed
by :mod:`tapps_obligations_block`. Section-aware replacement of that
content is delegated to the existing marker logic — the whole block is
swapped in on refresh, so the per-``## `` sections inside the block do
not need to be split apart here.

Canonical sections (shipped inside the marker block, replaced wholesale):
    - ``## Tapps Rules``
    - ``## Recommended Tool Call Obligations``
    - ``## Memory System``
    - ``## Quality Gate Behavior``
    - ``## Upgrade & Rollback``

User-owned content (preserved verbatim outside the marker block):
    Anything else — file preamble, project-specific notes, additional
    H1/H2 sections, the Karpathy guidelines block (managed by its own
    BEGIN/END markers).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from tapps_mcp import __version__

EXPECTED_SECTIONS: list[str] = [
    "Tapps Rules",
    "Recommended Tool Call Obligations",
    "Memory System",
    "Quality Gate Behavior",
    "Upgrade & Rollback",
]

_VERSION_RE = re.compile(r"<!--\s*tapps-claude-version:\s*([\d.]+)\s*-->")
_OBLIGATIONS_BEGIN_PREFIX = "<!-- BEGIN: tapps-obligations"
_OBLIGATIONS_END_MARKER = "<!-- END: tapps-obligations -->"


class ClaudeValidation:
    """Result of validating an existing CLAUDE.md file."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.existing_version = self._extract_version()
        self.has_obligations_block = _OBLIGATIONS_BEGIN_PREFIX in content
        self.sections_found, self.sections_missing = self._check_sections()

    def _extract_version(self) -> str | None:
        match = _VERSION_RE.search(self.content)
        return match.group(1) if match else None

    def _check_sections(self) -> tuple[list[str], list[str]]:
        body = self.content
        if self.has_obligations_block:
            begin = body.find(_OBLIGATIONS_BEGIN_PREFIX)
            end = body.find(_OBLIGATIONS_END_MARKER, begin) if begin != -1 else -1
            if begin != -1 and end != -1:
                body = body[begin:end]
        found = [s for s in EXPECTED_SECTIONS if f"## {s}" in body]
        missing = [s for s in EXPECTED_SECTIONS if f"## {s}" not in body]
        return found, missing

    @property
    def is_up_to_date(self) -> bool:
        """True when stamp matches, obligations block is present, and no canonical
        section is missing inside that block."""
        return (
            self.existing_version == __version__
            and self.has_obligations_block
            and not self.sections_missing
        )

    @property
    def needs_stamp(self) -> bool:
        """True for legacy consumers with no top-level stamp."""
        return self.existing_version is None

    @property
    def needs_update(self) -> bool:
        return not self.is_up_to_date

    def to_dict(self) -> dict[str, Any]:
        return {
            "existing_version": self.existing_version,
            "current_version": __version__,
            "has_obligations_block": self.has_obligations_block,
            "sections_found": self.sections_found,
            "sections_missing": self.sections_missing,
            "is_up_to_date": self.is_up_to_date,
            "needs_stamp": self.needs_stamp,
        }


def _ensure_stamp(content: str, *, version: str = __version__) -> tuple[str, str]:
    """Idempotently add or rewrite the top-level CLAUDE.md version stamp.

    Returns ``(new_content, action)`` where *action* is one of
    ``"unchanged"``, ``"added"``, ``"updated"``.
    """
    match = _VERSION_RE.search(content)
    if match is None:
        stamp = f"<!-- tapps-claude-version: {version} -->\n"
        return stamp + content, "added"
    if match.group(1) == version:
        return content, "unchanged"
    new = _VERSION_RE.sub(f"<!-- tapps-claude-version: {version} -->", content, count=1)
    return new, "updated"


def _refresh_obligations_block(
    existing_content: str,
    obligations_content: str,
) -> tuple[str, str]:
    """Refresh the marker-wrapped TAPPS obligations block in *existing_content*.

    Returns ``(new_content, change_label)`` describing what happened. User
    content outside the markers is preserved verbatim.
    """
    from tapps_mcp.pipeline.tapps_obligations_block import (
        _find_block_span,
        _find_legacy_tapps_section,
        wrap_with_markers,
    )

    new_block = wrap_with_markers(obligations_content)
    span = _find_block_span(existing_content)
    if span is not None:
        begin, end = span
        if existing_content[begin:end] == new_block:
            return existing_content, "unchanged_obligations_block"
        updated = existing_content[:begin] + new_block + existing_content[end:]
        return updated, "refreshed_obligations_block"

    legacy = _find_legacy_tapps_section(existing_content)
    if legacy is not None:
        begin, end = legacy
        head = existing_content[:begin].rstrip()
        tail = existing_content[end:].lstrip("\n")
        pieces = [head, new_block] if head else [new_block]
        if tail:
            pieces.append(tail)
        updated = "\n\n".join(pieces)
        if not updated.endswith("\n"):
            updated += "\n"
        return updated, "migrated_legacy_tapps_section"

    sep = "\n\n" if existing_content.rstrip() == existing_content.rstrip("\n") else "\n"
    updated = f"{existing_content.rstrip()}{sep}{new_block}\n"
    return updated, "appended_obligations_block"


def merge_claude_md(
    existing_content: str,
    obligations_content: str,
) -> tuple[str, list[str]]:
    """Smart-merge an existing CLAUDE.md with the latest TAPPS content.

    *obligations_content* is the unwrapped TAPPS-rules body (what
    :func:`load_platform_rules` returns). The merge refreshes the
    marker-wrapped block in-place and rewrites the top-of-file stamp to
    match the current package version. Everything outside the markers is
    preserved verbatim.

    Returns ``(merged_content, changes)``.
    """
    changes: list[str] = []
    body, block_change = _refresh_obligations_block(existing_content, obligations_content)
    if block_change != "unchanged_obligations_block":
        changes.append(block_change)

    body, stamp_action = _ensure_stamp(body)
    if stamp_action == "added":
        changes.append("added_version_marker")
    elif stamp_action == "updated":
        changes.append("updated_version_marker")

    return body, changes


def render_fresh_claude_md(obligations_content: str) -> str:
    """Return the content for a fresh CLAUDE.md (no existing file)."""
    from tapps_mcp.pipeline.tapps_obligations_block import wrap_with_markers

    return f"<!-- tapps-claude-version: {__version__} -->\n{wrap_with_markers(obligations_content)}\n"


def validate_claude_md(claude_path: Path) -> ClaudeValidation:
    """Validate an existing CLAUDE.md file."""
    content = claude_path.read_text(encoding="utf-8")
    return ClaudeValidation(content)


def update_claude_md(
    claude_path: Path,
    obligations_content: str,
    *,
    overwrite: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Update an existing CLAUDE.md (or create one).

    Returns ``(action, detail_dict)`` where *action* is one of:
        ``"created"``       — file did not exist; wrote fresh stamped content.
        ``"validated"``     — file exists, stamp matches, nothing to do.
        ``"updated"``       — smart-merge applied; canonical block refreshed,
                              user content preserved.
        ``"overwritten"``   — caller passed ``overwrite=True``; full rewrite.
        ``"needs-stamp"``   — legacy consumer with no stamp; stamp added and
                              obligations block refreshed (user content
                              outside the markers untouched).
    """
    detail: dict[str, Any] = {"version": __version__}

    if not claude_path.exists():
        content = render_fresh_claude_md(obligations_content)
        claude_path.write_text(content, encoding="utf-8")
        detail["changes"] = ["created"]
        detail["validation"] = ClaudeValidation(content).to_dict()
        return "created", detail

    existing = claude_path.read_text(encoding="utf-8")
    validation = ClaudeValidation(existing)
    detail["validation"] = validation.to_dict()

    if overwrite:
        # Force the merge even when the stamp matches. Surrounding user
        # content outside the marker block is still preserved — overwrite
        # rewrites the TAPPS section, not the whole file. (Use
        # render_fresh_claude_md directly for a true full overwrite.)
        merged, changes = merge_claude_md(existing, obligations_content)
        claude_path.write_text(merged, encoding="utf-8")
        detail["changes"] = changes or ["forced_refresh"]
        return "overwritten", detail

    if validation.is_up_to_date:
        detail["changes"] = []
        return "validated", detail

    merged, changes = merge_claude_md(existing, obligations_content)
    claude_path.write_text(merged, encoding="utf-8")
    detail["changes"] = changes

    if validation.needs_stamp:
        return "needs-stamp", detail
    return "updated", detail


__all__ = [
    "EXPECTED_SECTIONS",
    "ClaudeValidation",
    "merge_claude_md",
    "render_fresh_claude_md",
    "update_claude_md",
    "validate_claude_md",
]

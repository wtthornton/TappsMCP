"""Marker-wrapped TAPPS obligations block in CLAUDE.md (TAP-970).

The block is the platform-rules content that ``tapps_init`` writes into
``CLAUDE.md``. By wrapping it in two HTML comment markers, ``tapps_upgrade``
can refresh the obligations surgically while leaving consumer
customizations outside the markers intact.

Reference pattern: ``karpathy_block.py`` (which does the same for AGENTS.md).
The two implementations are intentionally similar so a future refactor could
share infrastructure.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

from tapps_mcp import __version__

if TYPE_CHECKING:
    from pathlib import Path


Action = Literal["created", "refreshed", "migrated", "unchanged", "appended"]

MARKER_BEGIN_PREFIX = "<!-- BEGIN: tapps-obligations"
MARKER_END = "<!-- END: tapps-obligations -->"

_VERSION_RE = re.compile(r"<!--\s*BEGIN:\s*tapps-obligations\s+v([\d.]+)\s*-->")


def _find_block_span(content: str) -> tuple[int, int] | None:
    """Return ``(begin, end_exclusive)`` for the marker-wrapped block.

    The slice ``content[begin:end]`` covers BEGIN marker through END marker
    inclusive, so callers can replace it wholesale.
    """
    begin = content.find(MARKER_BEGIN_PREFIX)
    if begin == -1:
        return None
    end_idx = content.find(MARKER_END, begin)
    if end_idx == -1:
        return None
    return begin, end_idx + len(MARKER_END)


def _extract_version(content: str) -> str | None:
    match = _VERSION_RE.search(content)
    return match.group(1) if match else None


def wrap_with_markers(obligations: str, *, version: str = __version__) -> str:
    """Return *obligations* wrapped in BEGIN/END markers stamped with *version*."""
    body = obligations.strip("\n")
    return (
        f"<!-- BEGIN: tapps-obligations v{version} -->\n"
        f"{body}\n"
        f"{MARKER_END}"
    )


def _find_legacy_tapps_section(content: str) -> tuple[int, int] | None:
    """Return ``(begin, end_exclusive)`` for an unmarked legacy TAPPS section.

    Matches ``# TAPPS Quality Pipeline`` (with optional trailing words like
    ``- MANDATORY``) at the start of a line, and stretches to the next
    top-level ``# `` heading or end-of-file. Returns ``None`` if no such
    section exists. Used for the one-time migration path that auto-wraps
    a pre-marker installation.
    """
    pattern = re.compile(r"^#\s+TAPPS\s+Quality\s+Pipeline\b.*$", re.MULTILINE)
    match = pattern.search(content)
    if match is None:
        return None
    begin = match.start()
    next_h1 = re.compile(r"^#\s+(?!TAPPS\s+Quality\s+Pipeline)", re.MULTILINE)
    next_match = next_h1.search(content, pos=match.end())
    end = next_match.start() if next_match else len(content)
    return begin, end


def install_or_refresh(
    path: Path,
    obligations: str,
    *,
    dry_run: bool = False,
    version: str = __version__,
) -> Action:
    """Install or refresh the TAPPS obligations block in *path*.

    - File missing: writes a fresh CLAUDE.md containing only the markered block
      (action: ``"created"``).
    - File exists with markers: replaces the block content if it differs from
      *obligations* (``"refreshed"``); returns ``"unchanged"`` if identical.
    - File exists with an unmarked legacy ``# TAPPS Quality Pipeline`` section:
      replaces that section with the markered block (``"migrated"``). Custom
      lines outside the section are preserved.
    - File exists without TAPPS content: appends the markered block after a
      blank line (``"appended"``).

    When ``dry_run=True`` the action is computed without touching the file.
    """
    new_block = wrap_with_markers(obligations, version=version)

    if not path.exists():
        if not dry_run:
            path.write_text(new_block + "\n", encoding="utf-8")
        return "created"

    original = path.read_text(encoding="utf-8")
    span = _find_block_span(original)

    if span is not None:
        begin, end = span
        if original[begin:end] == new_block:
            return "unchanged"
        updated = original[:begin] + new_block + original[end:]
        action: Action = "refreshed"
    else:
        legacy = _find_legacy_tapps_section(original)
        if legacy is not None:
            begin, end = legacy
            head = original[:begin].rstrip()
            tail = original[end:].lstrip("\n")
            pieces = [head, new_block] if head else [new_block]
            if tail:
                pieces.append(tail)
            updated = "\n\n".join(pieces)
            if not updated.endswith("\n"):
                updated += "\n"
            action = "migrated"
        else:
            separator = "\n\n" if original.rstrip() == original.rstrip("\n") else "\n"
            updated = f"{original.rstrip()}{separator}{new_block}\n"
            action = "appended"

    if not dry_run:
        path.write_text(updated, encoding="utf-8")
    return action


__all__ = [
    "Action",
    "MARKER_BEGIN_PREFIX",
    "MARKER_END",
    "install_or_refresh",
    "wrap_with_markers",
]

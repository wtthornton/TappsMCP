"""Marker-wrapped managed block for multi-file skills (orchestration-prompt).

Most platform skills ship a single ``SKILL.md`` that ``generate_skills`` skips
on upgrade to preserve customizations. That all-or-nothing rule is wrong for a
skill like ``orchestration-prompt``, which has a large platform-canonical body
*and* per-project customizations (fleet manifest refs, observed-failure
examples, run-as specifics) interwoven by consumers.

This module gives such skills a surgical smart-merge: the platform body lives
inside two HTML-comment markers; ``tapps_upgrade`` refreshes only that block and
preserves everything outside it (the project region) verbatim.

Reference pattern: ``tapps_obligations_block.py`` / ``karpathy_block.py`` — the
three are intentionally similar so a future refactor can share infrastructure.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

from tapps_mcp import __version__

if TYPE_CHECKING:
    from pathlib import Path

Action = Literal["created", "refreshed", "migrated", "unchanged"]

MARKER_BEGIN_PREFIX = "<!-- BEGIN: tapps-skill"
MARKER_END = "<!-- END: tapps-skill -->"

# Heading that introduces the preserved project region on a legacy migration.
PROJECT_REGION_HEADING = (
    "<!-- tapps-skill-project-customizations: preserved from the pre-marker "
    "version — review and trim any content the managed block above now covers -->"
)

_VERSION_RE = re.compile(r"<!--\s*BEGIN:\s*tapps-skill\s+([\w-]+)\s+v([\d.]+)\s*-->")


def _find_block_span(content: str) -> tuple[int, int] | None:
    """Return ``(begin, end_exclusive)`` covering the BEGIN..END markers."""
    begin = content.find(MARKER_BEGIN_PREFIX)
    if begin == -1:
        return None
    end_idx = content.find(MARKER_END, begin)
    if end_idx == -1:
        return None
    return begin, end_idx + len(MARKER_END)


def wrap_with_markers(body: str, skill_name: str, *, version: str = __version__) -> str:
    """Return *body* wrapped in BEGIN/END markers stamped with skill + version."""
    inner = body.strip("\n")
    return f"{MARKER_BEGIN_PREFIX} {skill_name} v{version} -->\n{inner}\n{MARKER_END}"


def install_or_refresh_skill(
    path: Path,
    body: str,
    skill_name: str,
    *,
    dry_run: bool = False,
    version: str = __version__,
) -> Action:
    """Install or surgically refresh the managed block in a skill's ``SKILL.md``.

    - **File missing** → write a fresh file containing only the markered block
      (``"created"``).
    - **Markers present** → replace the block if it differs (``"refreshed"``),
      else ``"unchanged"``. Content outside the markers is preserved verbatim.
    - **Markers absent (legacy hand-authored copy)** → keep the old content as a
      preserved project region *below* the fresh managed block (``"migrated"``).
      Nothing is lost; the operator trims the duplicated region afterwards.

    ``dry_run=True`` computes the action without writing.
    """
    new_block = wrap_with_markers(body, skill_name, version=version)

    if not path.exists():
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
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
        # Legacy unmarked skill: preserve the whole prior body as a project region.
        preserved = original.strip("\n")
        updated = f"{new_block}\n\n{PROJECT_REGION_HEADING}\n\n{preserved}\n"
        action = "migrated"

    if not dry_run:
        path.write_text(updated, encoding="utf-8")
    return action


__all__ = [
    "MARKER_BEGIN_PREFIX",
    "MARKER_END",
    "PROJECT_REGION_HEADING",
    "Action",
    "install_or_refresh_skill",
    "wrap_with_markers",
]

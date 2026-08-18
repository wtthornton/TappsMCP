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

# A SKILL.md's YAML frontmatter: ``---`` on line 1, keys, closing ``---``.
# Anchored at the start of the string on purpose — Claude Code only parses
# frontmatter that begins at byte 0, so anything matched here is by definition
# the block that must stay first in the file (see :func:`split_frontmatter`).
_FRONTMATTER_RE = re.compile(r"\A---\r?\n.*?\r?\n---[ \t]*\r?\n?", re.DOTALL)


def split_frontmatter(text: str) -> tuple[str, str]:
    """Split *text* into ``(frontmatter, remainder)``.

    ``frontmatter`` keeps its ``---`` delimiters and trailing newline, and is
    ``""`` when *text* does not open with a frontmatter block. Anything a skill
    generator prepends — an engagement note, a managed-block marker — has to go
    into ``remainder``, never in front of ``frontmatter``: Claude Code reads
    frontmatter only when the opening ``---`` is the first byte of the file, so
    a single line above it silently drops ``name``, ``description``,
    ``allowed-tools`` and the rest, and the skill stops auto-triggering.
    """
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return "", text
    return match.group(0), text[match.end() :]


def prepend_below_frontmatter(content: str, prefix: str) -> str:
    """Insert *prefix* directly under *content*'s frontmatter, not above it.

    Returns *content* unchanged when *prefix* is empty. When *content* has no
    frontmatter the prefix goes first, matching the naive concatenation this
    replaces. Leading blank lines on the remainder are dropped so the prefix's
    own trailing newlines set the spacing.
    """
    if not prefix:
        return content
    frontmatter, rest = split_frontmatter(content)
    if not frontmatter:
        return f"{prefix}{content}"
    return f"{frontmatter}{prefix}{rest.lstrip('\n')}"


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
    """Return *body* as ``frontmatter + BEGIN..END block``, frontmatter first.

    The markers wrap only the prose below the frontmatter. Wrapping the whole
    body — frontmatter included — pushed the opening ``---`` off line 1 and made
    every generated skill unparseable.
    """
    frontmatter, rest = split_frontmatter(body)
    inner = rest.strip("\n")
    block = f"{MARKER_BEGIN_PREFIX} {skill_name} v{version} -->\n{inner}\n{MARKER_END}"
    return f"{frontmatter}{block}"


def install_or_refresh_skill(
    path: Path,
    body: str,
    skill_name: str,
    *,
    dry_run: bool = False,
    version: str = __version__,
) -> Action:
    """Install or surgically refresh the managed block in a skill's ``SKILL.md``.

    - **File missing** → write frontmatter followed by the markered block
      (``"created"``).
    - **Markers present** → replace the block if it differs (``"refreshed"``),
      else ``"unchanged"``. Content outside the markers is preserved verbatim,
      except the leading frontmatter, which the platform owns and rewrites.
    - **Markers absent (legacy hand-authored copy)** → keep the old content as a
      preserved project region *below* the fresh managed block (``"migrated"``).
      Nothing is lost; the operator trims the duplicated region afterwards.

    The written file always starts with ``---``. A refresh that finds the marker
    on line 1 (the pre-fix layout, where the frontmatter was wrapped *inside*
    the block) heals itself here: the stale block carries the old frontmatter
    away with it and the new frontmatter lands first.

    ``dry_run=True`` computes the action without writing.
    """
    frontmatter, new_block = split_frontmatter(wrap_with_markers(body, skill_name, version=version))

    if not path.exists():
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(frontmatter + new_block + "\n", encoding="utf-8")
        return "created"

    original = path.read_text(encoding="utf-8")
    span = _find_block_span(original)

    if span is not None:
        begin, end = span
        # Whatever sits above the block minus its own frontmatter: project
        # content the operator put there, which survives the refresh.
        _, head = split_frontmatter(original[:begin])
        updated = frontmatter + head + new_block + original[end:]
        if updated == original:
            return "unchanged"
        action: Action = "refreshed"
    else:
        # Legacy unmarked skill: preserve the whole prior body as a project region.
        preserved = original.strip("\n")
        updated = f"{frontmatter}{new_block}\n\n{PROJECT_REGION_HEADING}\n\n{preserved}\n"
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
    "prepend_below_frontmatter",
    "split_frontmatter",
    "wrap_with_markers",
]

"""CLAUDE.md / Cursor rule bootstrap and Markdown section surgery.

Split out of :mod:`~tapps_mcp.pipeline.init` (TAP-5733); the names here are
re-exported from that module so existing call sites keep working.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tapps_mcp.prompts.prompt_loader import load_platform_rules

if TYPE_CHECKING:
    from pathlib import Path


def _bootstrap_claude(
    project_root: Path,
    overwrite: bool = False,
    engagement_level: str = "medium",
) -> str:
    """Create or refresh the marker-wrapped TAPPS obligations in CLAUDE.md.

    Returns ``'created'``, ``'updated'``, ``'unchanged'``, ``'needs-stamp'``,
    or ``'skipped'``.

    TAP-970: refreshes a ``<!-- BEGIN: tapps-obligations vX.Y.Z -->`` /
    ``<!-- END: tapps-obligations -->`` region surgically. On a legacy
    consumer with an unmarked ``# TAPPS Quality Pipeline`` section, the
    section is wrapped in markers as a one-time migration. Custom lines
    outside the markers always survive. ``overwrite=True`` rewrites the
    file with just the markered block + stamp.

    TAP-2334: a top-level ``<!-- tapps-claude-version: X.Y.Z -->`` stamp is
    added (or refreshed) so ``tapps_upgrade`` can detect stale consumer
    CLAUDE.md files and skip the merge when nothing has changed. See
    :mod:`claude_md` for the section-aware merge.
    """
    from tapps_mcp.pipeline.claude_md import update_claude_md

    claude_md = project_root / "CLAUDE.md"
    content = load_platform_rules("claude", engagement_level=engagement_level)
    action, _detail = update_claude_md(claude_md, content, overwrite=overwrite)
    if action == "validated":
        return "unchanged"
    if action == "overwritten":
        return "updated"
    return action


def _split_by_h1_headings(content: str) -> list[tuple[str, str]]:
    """Split Markdown content by ``# `` (H1) headings.

    Returns a list of ``(heading_line, body)`` tuples.  Content before the
    first H1 heading is captured with an empty ``heading_line``.  Only
    top-level ``# `` headings act as boundaries -- ``##``, ``###`` etc.
    are treated as regular body content.

    The *heading_line* includes the trailing newline (if present) so that
    reassembly via simple concatenation preserves the original whitespace.
    """
    import re

    sections: list[tuple[str, str]] = []
    current_heading = ""
    current_lines: list[str] = []

    for line in content.splitlines(keepends=True):
        if re.match(r"^# ", line):
            # Flush previous section
            if current_lines or current_heading:
                sections.append((current_heading, "".join(current_lines)))
            current_heading = line
            current_lines = []
        else:
            current_lines.append(line)

    # Flush last section
    if current_lines or current_heading:
        sections.append((current_heading, "".join(current_lines)))

    return sections


def _replace_tapps_section(existing: str, new_tapps_content: str) -> str:
    """Replace the TAPPS section in an existing CLAUDE.md.

    Finds the ``# TAPPS Quality Pipeline`` heading and replaces everything
    from that heading to the next top-level heading (or end of file) with
    *new_tapps_content*.

    Uses :func:`_split_by_h1_headings` for robust heading-based splitting
    instead of fragile regex matching.
    """
    sections = _split_by_h1_headings(existing)

    tapps_idx: int | None = None
    for idx, (heading, _body) in enumerate(sections):
        if heading.startswith("# TAPPS Quality Pipeline"):
            tapps_idx = idx
            break

    if tapps_idx is None:
        # No TAPPS heading found -- append fresh content
        return existing.rstrip() + "\n\n" + new_tapps_content

    # Rebuild: sections before TAPPS + new content + sections after TAPPS
    before_parts: list[str] = []
    for heading, body in sections[:tapps_idx]:
        before_parts.append(heading + body)
    before = "".join(before_parts).rstrip()

    after_parts: list[str] = []
    for heading, body in sections[tapps_idx + 1 :]:
        after_parts.append(heading + body)
    after = "".join(after_parts).lstrip("\n")

    parts = [before, new_tapps_content] if before else [new_tapps_content]
    if after:
        parts.append(after)
    return "\n\n".join(parts)


def _bootstrap_cursor(
    project_root: Path,
    overwrite: bool = False,
    engagement_level: str = "medium",
) -> str:
    """Create or update Cursor pipeline rule file.

    Returns ``'created'``, ``'updated'``, or ``'skipped'``.
    """
    content = load_platform_rules("cursor", engagement_level=engagement_level)
    rules_path = project_root / ".cursor" / "rules" / "tapps-pipeline.mdc"
    rules_path.parent.mkdir(parents=True, exist_ok=True)

    if rules_path.exists() and not overwrite:
        return "skipped"

    action = "updated" if rules_path.exists() else "created"
    rules_path.write_text(content, encoding="utf-8")
    return action

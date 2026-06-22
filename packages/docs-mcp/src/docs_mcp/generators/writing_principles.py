"""Shared technical-writing principles for DocsMCP generators.

Anthropic knowledge-work-plugins ``documentation`` skill parity: reader-first prose
guidance appended to narrative generators (README merge preserves human sections).
"""

from __future__ import annotations

WRITING_PRINCIPLES: tuple[str, ...] = (
    "Write for the reader — state who this is for and what they need first.",
    "Lead with the most useful information — do not bury the lede.",
    "Show, do not tell — prefer commands, code examples, and concrete steps.",
    "Keep it current — outdated docs are worse than no docs; regenerate after API changes.",
    "Link, do not duplicate — reference other docs instead of copying long passages.",
)

_WRITING_NOTES_MARKER_BEGIN = "<!-- docsmcp:begin:writing-notes -->"
_WRITING_NOTES_MARKER_END = "<!-- docsmcp:end:writing-notes -->"


def writing_principles_block(*, as_comment: bool = False) -> str:
    """Return a markdown block with the standard writing principles."""
    bullets = "\n".join(f"- {p}" for p in WRITING_PRINCIPLES)
    body = f"## Writing notes\n\n{bullets}\n"
    if as_comment:
        return f"{_WRITING_NOTES_MARKER_BEGIN}\n{body}{_WRITING_NOTES_MARKER_END}\n"
    return body + "\n"


def append_writing_principles(content: str, *, as_comment: bool = False) -> str:
    """Append writing principles when not already present."""
    if _WRITING_NOTES_MARKER_BEGIN in content or "## Writing notes" in content:
        return content
    block = writing_principles_block(as_comment=as_comment)
    trimmed = content.rstrip()
    return f"{trimmed}\n\n{block}"

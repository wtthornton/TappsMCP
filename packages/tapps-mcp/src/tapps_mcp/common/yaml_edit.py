"""Comment-preserving edits to a YAML config file.

``yaml.safe_load`` → mutate → ``yaml.dump`` silently destroys every comment in
the file. For ``.tapps-mcp.yaml`` that is real data loss: the comments are where
a project records *why* a setting is set — why ``skill_count_max`` exceeds the
stock ceiling, why a file is in ``upgrade_skip_files`` and what must happen
before it is removed. Values survive the round-trip; the reasoning does not, and
what is left is a bare number nobody dares change.

:func:`update_yaml_preserving_comments` rewrites only the blocks it is asked to
change and leaves the rest of the file byte-for-byte intact.

Scope: top-level keys of a mapping document, which is all ``.tapps-mcp.yaml``
needs. Editing a nested key is not supported — pass the whole top-level block.
"""

from __future__ import annotations

from typing import Any

import yaml

__all__ = ["render_top_level_entry", "update_yaml_preserving_comments"]


def _is_indented(line: str) -> bool:
    return line[:1] in (" ", "\t")


def _top_level_key(line: str) -> str | None:
    """Return the key when *line* opens a top-level mapping entry, else None.

    Indented lines belong to a parent block, and a ``#`` line is a comment —
    neither starts a top-level entry, and matching them would corrupt the file.
    """
    if not line.strip() or _is_indented(line) or line.lstrip().startswith("#"):
        return None
    key, sep, _ = line.partition(":")
    if not sep:
        return None
    key = key.strip()
    # Quoted keys are legal YAML; normalise so callers can pass the bare name.
    if len(key) >= 2 and key[0] == key[-1] and key[0] in ("'", '"'):
        key = key[1:-1]
    return key or None


def _block_extent(lines: list[str], start: int) -> int:
    """Index one past the last line belonging to the entry opened at *start*.

    A block runs to the next line that is neither indented nor blank. Trailing
    blank lines are excluded so a comment sitting between two entries stays
    attached to the entry it documents rather than being swallowed.
    """
    end = start + 1
    last_content = end
    while end < len(lines):
        line = lines[end]
        if line.strip() and not _is_indented(line):
            break
        end += 1
        if line.strip():
            last_content = end
    return last_content


def render_top_level_entry(key: str, value: Any) -> list[str]:
    """Render ``key: value`` as YAML lines, without a trailing newline."""
    dumped = yaml.dump({key: value}, default_flow_style=False, sort_keys=False)
    return dumped.rstrip("\n").split("\n")


def update_yaml_preserving_comments(text: str, updates: dict[str, Any]) -> str:
    """Return *text* with each of *updates* applied, keeping all comments.

    Existing top-level keys are replaced in place, so surrounding comments and
    key order are preserved. New keys are appended. A document that is empty or
    not a mapping is rendered fresh — there is nothing to preserve.
    """
    if not updates:
        return text

    if not text.strip():
        rendered = [
            line for key, value in updates.items() for line in render_top_level_entry(key, value)
        ]
        return "\n".join(rendered) + "\n"

    lines = text.splitlines()
    remaining = dict(updates)

    index = 0
    out: list[str] = []
    while index < len(lines):
        key = _top_level_key(lines[index])
        if key is not None and key in remaining:
            end = _block_extent(lines, index)
            out.extend(render_top_level_entry(key, remaining.pop(key)))
            index = end
            continue
        out.append(lines[index])
        index += 1

    for key, value in remaining.items():
        if out and out[-1].strip():
            pass  # keep a single newline between entries; no blank-line padding
        out.extend(render_top_level_entry(key, value))

    return "\n".join(out) + "\n"

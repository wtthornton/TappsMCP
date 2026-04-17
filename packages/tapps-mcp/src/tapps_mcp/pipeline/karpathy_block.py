"""Install, refresh, and inspect the vendored Karpathy guidelines block.

The block is a fixed chunk of markdown (vendored under
``prompts/karpathy_guidelines.md``) that `tapps_init` appends to AGENTS.md
and `tapps_upgrade` refreshes in place. Both operations key off two HTML
comment markers so we can rewrite between them without touching anything
outside — and so `tapps_doctor` can report whether the block is present
and pinned to the current source SHA.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

from tapps_mcp.prompts.prompt_loader import (
    KARPATHY_GUIDELINES_MARKER_BEGIN,
    KARPATHY_GUIDELINES_MARKER_END,
    KARPATHY_GUIDELINES_SOURCE_SHA,
    load_karpathy_guidelines,
)

if TYPE_CHECKING:
    from pathlib import Path


Action = Literal["added", "refreshed", "unchanged", "skipped_file_missing"]
DoctorState = Literal["ok", "stale", "missing", "file_absent"]

_SHA_RE = re.compile(r"<!--\s*BEGIN:\s*karpathy-guidelines\s+([0-9a-f]{7,40})\b")


def _find_block_span(content: str) -> tuple[int, int] | None:
    """Return ``(begin_idx, end_idx_exclusive)`` for the block, or ``None``.

    ``begin_idx`` points at the start of the BEGIN marker; ``end_idx`` is
    just past the END marker so ``content[begin:end]`` is the full block.
    Matching uses the marker *prefix* up to the SHA placeholder, so blocks
    vendored under older SHAs are still found (and thus refreshable).
    """
    begin_prefix = "<!-- BEGIN: karpathy-guidelines"
    begin = content.find(begin_prefix)
    if begin == -1:
        return None
    end_marker_idx = content.find(KARPATHY_GUIDELINES_MARKER_END, begin)
    if end_marker_idx == -1:
        return None
    return begin, end_marker_idx + len(KARPATHY_GUIDELINES_MARKER_END)


def _extract_sha(content: str) -> str | None:
    """Return the SHA recorded in the BEGIN marker, or ``None`` if absent."""
    match = _SHA_RE.search(content)
    return match.group(1) if match else None


def install_or_refresh(path: Path, *, dry_run: bool = False) -> Action:
    """Install the Karpathy block into *path*, or refresh an outdated copy.

    - If *path* does not exist: returns ``"skipped_file_missing"``.
    - If the block is absent: appends it after a blank line; returns ``"added"``.
    - If the block exists with the current SHA and identical content:
      returns ``"unchanged"``.
    - Otherwise: replaces the block between its markers; returns ``"refreshed"``.

    When ``dry_run=True``, computes the outcome without touching the file.
    """
    if not path.exists():
        return "skipped_file_missing"

    original = path.read_text(encoding="utf-8")
    new_block = load_karpathy_guidelines()
    span = _find_block_span(original)

    if span is None:
        separator = (
            "" if original.endswith("\n\n") else ("\n" if original.endswith("\n") else "\n\n")
        )
        updated = f"{original}{separator}{new_block}\n"
        action: Action = "added"
    else:
        begin, end = span
        existing_block = original[begin:end]
        if existing_block == new_block:
            return "unchanged"
        updated = original[:begin] + new_block + original[end:]
        action = "refreshed"

    if not dry_run:
        path.write_text(updated, encoding="utf-8")
    return action


def check(path: Path) -> dict[str, str | None]:
    """Return a doctor-style report on the block in *path*.

    Keys:
        state: ``"ok"`` | ``"stale"`` | ``"missing"`` | ``"file_absent"``
        current_sha: SHA recorded in the file's marker, or ``None``
        expected_sha: The currently vendored SHA
        hint: Human-readable next-step suggestion (always present)
    """
    expected = KARPATHY_GUIDELINES_SOURCE_SHA
    if not path.exists():
        return {
            "state": "file_absent",
            "current_sha": None,
            "expected_sha": expected,
            "hint": f"{path.name} not found — run tapps_init to create it.",
        }

    content = path.read_text(encoding="utf-8")
    if _find_block_span(content) is None:
        return {
            "state": "missing",
            "current_sha": None,
            "expected_sha": expected,
            "hint": "Karpathy guidelines block not found — run tapps_upgrade to install it.",
        }

    current = _extract_sha(content)
    if current and expected.startswith(current):
        return {
            "state": "ok",
            "current_sha": current,
            "expected_sha": expected,
            "hint": "Karpathy guidelines block is up to date.",
        }
    return {
        "state": "stale",
        "current_sha": current,
        "expected_sha": expected,
        "hint": "Karpathy guidelines block is pinned to an older SHA — run tapps_upgrade to refresh.",
    }


__all__ = [
    "KARPATHY_GUIDELINES_MARKER_BEGIN",
    "KARPATHY_GUIDELINES_MARKER_END",
    "KARPATHY_GUIDELINES_SOURCE_SHA",
    "Action",
    "DoctorState",
    "check",
    "install_or_refresh",
]

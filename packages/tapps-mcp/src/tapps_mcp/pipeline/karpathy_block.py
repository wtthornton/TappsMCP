"""Install, refresh, and inspect the vendored Karpathy guidelines block.

The block is a fixed chunk of markdown (vendored under
``prompts/karpathy_guidelines.md``) that `tapps_init` appends to AGENTS.md
and `tapps_upgrade` refreshes in place. Both operations key off two HTML
comment markers so we can rewrite between them without touching anything
outside — and so `tapps_doctor` can report whether the block is present
and pinned to the current source SHA.

When ``.cursor/rules/`` exists, the same content is also installed as
``.cursor/rules/karpathy-guidelines.mdc`` (upstream Cursor packaging from
``forrestchang/andrej-karpathy-skills``).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

from tapps_mcp.prompts.prompt_loader import (
    KARPATHY_CURSOR_RULE_REL,
    KARPATHY_GUIDELINES_MARKER_BEGIN,
    KARPATHY_GUIDELINES_MARKER_END,
    KARPATHY_GUIDELINES_SOURCE_SHA,
    load_karpathy_cursor_rule,
    load_karpathy_guidelines,
)

if TYPE_CHECKING:
    from pathlib import Path


Action = Literal["added", "refreshed", "unchanged", "skipped_file_missing"]
CursorAction = Literal[
    "added",
    "refreshed",
    "unchanged",
    "skipped_no_cursor",
    "removed",
    "skipped_file_missing",
]
DoctorState = Literal["ok", "stale", "missing", "file_absent", "skipped_no_cursor"]

_SHA_RE = re.compile(r"<!--\s*BEGIN:\s*karpathy-guidelines\s+([0-9a-f]{7,40})\b")
_CURSOR_SHA_RE = re.compile(r"<!--\s*karpathy-guidelines-sha:\s*([0-9a-f]{7,40})\s*-->")


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


def has_block(path: Path) -> bool:
    """Return True when *path* exists and contains a Karpathy guidelines block."""
    if not path.is_file():
        return False
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return _find_block_span(content) is not None


def remove_block(path: Path, *, dry_run: bool = False) -> Action:
    """Remove the Karpathy block from *path* if present.

    Returns ``"unchanged"`` when the file or block is missing, otherwise
    ``"refreshed"`` after stripping the block (reuses Action literals).
    """
    if not path.is_file():
        return "skipped_file_missing"
    original = path.read_text(encoding="utf-8")
    span = _find_block_span(original)
    if span is None:
        return "unchanged"
    begin, end = span
    before = original[:begin].rstrip("\n")
    after = original[end:].lstrip("\n")
    if before and after:
        updated = f"{before}\n\n{after}"
    elif before:
        updated = f"{before}\n"
    else:
        updated = f"{after}" if after.endswith("\n") or not after else f"{after}\n"
    if not dry_run:
        path.write_text(updated, encoding="utf-8")
    return "refreshed"


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


def cursor_rule_path(project_root: Path) -> Path:
    """Return the absolute path of the Cursor Karpathy rule."""
    return project_root / KARPATHY_CURSOR_RULE_REL


def _cursor_rules_dir_present(project_root: Path) -> bool:
    return (project_root / ".cursor" / "rules").is_dir()


def install_or_refresh_cursor_rule(
    project_root: Path,
    *,
    dry_run: bool = False,
) -> CursorAction:
    """Install or refresh ``.cursor/rules/karpathy-guidelines.mdc``.

    Skips when ``.cursor/rules/`` is absent (does not create a Cursor tree
    solely for Karpathy). Creates the rule file when the rules dir exists.
    """
    if not _cursor_rules_dir_present(project_root):
        return "skipped_no_cursor"

    target = cursor_rule_path(project_root)
    new_content = load_karpathy_cursor_rule()
    if target.is_file():
        existing = target.read_text(encoding="utf-8")
        if existing == new_content:
            return "unchanged"
        action: CursorAction = "refreshed"
    else:
        action = "added"

    if not dry_run:
        target.write_text(new_content, encoding="utf-8")
    return action


def remove_cursor_rule(project_root: Path, *, dry_run: bool = False) -> CursorAction:
    """Remove the Cursor Karpathy rule if present."""
    target = cursor_rule_path(project_root)
    if not target.is_file():
        return "skipped_file_missing"
    if not dry_run:
        target.unlink()
    return "removed"


def check_cursor_rule(project_root: Path) -> dict[str, str | None]:
    """Doctor-style report for the Cursor Karpathy ``.mdc`` rule."""
    expected = KARPATHY_GUIDELINES_SOURCE_SHA
    if not _cursor_rules_dir_present(project_root):
        return {
            "state": "skipped_no_cursor",
            "current_sha": None,
            "expected_sha": expected,
            "hint": "No .cursor/rules/ directory — Cursor rule not applicable.",
        }

    target = cursor_rule_path(project_root)
    if not target.is_file():
        return {
            "state": "missing",
            "current_sha": None,
            "expected_sha": expected,
            "hint": (
                f"{KARPATHY_CURSOR_RULE_REL} not found — run tapps_upgrade to install it."
            ),
        }

    content = target.read_text(encoding="utf-8")
    match = _CURSOR_SHA_RE.search(content)
    current = match.group(1) if match else None
    if current and expected.startswith(current):
        return {
            "state": "ok",
            "current_sha": current,
            "expected_sha": expected,
            "hint": "Cursor Karpathy rule is up to date.",
        }
    return {
        "state": "stale",
        "current_sha": current,
        "expected_sha": expected,
        "hint": (
            "Cursor Karpathy rule is pinned to an older SHA — run tapps_upgrade to refresh."
        ),
    }


__all__ = [
    "KARPATHY_CURSOR_RULE_REL",
    "KARPATHY_GUIDELINES_MARKER_BEGIN",
    "KARPATHY_GUIDELINES_MARKER_END",
    "KARPATHY_GUIDELINES_SOURCE_SHA",
    "Action",
    "CursorAction",
    "DoctorState",
    "check",
    "check_cursor_rule",
    "cursor_rule_path",
    "has_block",
    "install_or_refresh",
    "install_or_refresh_cursor_rule",
    "remove_block",
    "remove_cursor_rule",
]

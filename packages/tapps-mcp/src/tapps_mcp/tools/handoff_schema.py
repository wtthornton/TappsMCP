"""Parse and lint ``.tapps-mcp/session-handoff.md`` (TAP-3573)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_HANDOFF_RELATIVE = Path(".tapps-mcp") / "session-handoff.md"
SESSION_HANDOFF_MEMORY_KEY = "session-handoff"
_UPDATED_RE = re.compile(r"^\*\*Updated:\*\*\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_LINEAR_P0_RE = re.compile(r"^\*\*Linear P0:\*\*\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_SECTION_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_PLACEHOLDER_UPDATED = frozenset({"<iso-8601 utc from date -u>", "t00:00:00z"})
_IGNORE_BULLETS = frozenset({"none", "n/a", "...", "—", "-", "tbd"})


@dataclass
class HandoffDocument:
    """Structured view of a session handoff markdown file."""

    updated: datetime | None = None
    linear_p0: str | None = None
    done: list[str] = field(default_factory=list)
    open_items: list[str] = field(default_factory=list)
    next_p0: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    verify: list[str] = field(default_factory=list)
    success_criterion: list[str] = field(default_factory=list)
    raw_text: str = ""


@dataclass
class HandoffLintResult:
    """Lint outcome for a handoff document."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def handoff_path(project_root: Path) -> Path:
    return project_root / _HANDOFF_RELATIVE


def _normalize_header(name: str) -> str:
    return name.strip().lower()


def _section_key(header: str) -> str | None:
    norm = _normalize_header(header)
    if norm == "done":
        return "done"
    if norm == "open":
        return "open"
    if norm in {"next (p0)", "next", "p0"}:
        return "next_p0"
    if norm == "blockers":
        return "blockers"
    if norm == "verify":
        return "verify"
    if norm in {"success criterion", "success criteria"}:
        return "success_criterion"
    return None


def _is_real_bullet(line: str) -> bool:
    stripped = line.strip().lstrip("-* ").strip()
    if not stripped:
        return False
    lowered = stripped.lower()
    if lowered in _IGNORE_BULLETS:
        return False
    if stripped.startswith("<") and stripped.endswith(">"):
        return False
    return not stripped.endswith("...")


def _extract_bullets(block: str) -> list[str]:
    items: list[str] = []
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line.startswith(("-", "*")):
            continue
        bullet = line.lstrip("-* ").strip()
        if _is_real_bullet(bullet):
            items.append(bullet)
    return items


def _parse_updated(raw: str) -> datetime | None:
    value = raw.strip()
    if not value:
        return None
    lowered = value.lower()
    if lowered in _PLACEHOLDER_UPDATED or value.startswith("<"):
        return None
    try:
        ts = datetime.fromisoformat(value)
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts


def _parse_linear_p0(raw: str) -> str | None:
    value = raw.strip()
    if not value or value.lower() in {"none", "n/a", "..."}:
        return None
    if value.startswith("<") and value.endswith(">"):
        return None
    return value


def parse_handoff_markdown(text: str) -> HandoffDocument:
    """Parse handoff markdown into structured sections."""
    doc = HandoffDocument(raw_text=text)
    updated_match = _UPDATED_RE.search(text)
    if updated_match:
        doc.updated = _parse_updated(updated_match.group(1))
    linear_match = _LINEAR_P0_RE.search(text)
    if linear_match:
        doc.linear_p0 = _parse_linear_p0(linear_match.group(1))

    sections = _SECTION_RE.split(text)
    # split returns [preamble, h1, body1, h2, body2, ...]
    idx = 1
    while idx + 1 < len(sections):
        header = sections[idx]
        body = sections[idx + 1]
        key = _section_key(header)
        if key == "done":
            doc.done = _extract_bullets(body)
        elif key == "open":
            doc.open_items = _extract_bullets(body)
        elif key == "next_p0":
            doc.next_p0 = _extract_bullets(body)
        elif key == "blockers":
            doc.blockers = _extract_bullets(body)
        elif key == "verify":
            doc.verify = _extract_bullets(body)
        elif key == "success_criterion":
            doc.success_criterion = _extract_bullets(body)
        idx += 2
    return doc


# A success criterion that CLAIMS achievement ("MET", "criterion is met.")
# while Open items remain is contradictory — that is what this warning catches.
# Word-boundary match: the previous bare substring check tripped on ordinary
# words containing "met" ("geometry >= 0.65", "metrics"). Forward-looking
# conditional phrasing ("is met when X passes") describes the target, not a
# claim, so "met" followed by a conditional connective is excluded.
_MET_CLAIM = re.compile(r"\bmet\b(?!\s+(?:when|if|once|after|by|upon)\b)")


def lint_handoff(
    doc: HandoffDocument,
    *,
    stale_days: int = 7,
    now: datetime | None = None,
) -> HandoffLintResult:
    """Validate handoff schema; errors fail doctor, warnings are advisory."""
    result = HandoffLintResult()
    clock = now or datetime.now(tz=UTC)

    if doc.open_items and not doc.next_p0:
        result.errors.append(
            "Open items exist but Next (P0) is missing — continue-session cannot pick up work"
        )

    if doc.updated is None:
        result.warnings.append(
            "Updated timestamp missing or placeholder — run date -u +%Y-%m-%dT%H:%M:%SZ"
        )
    else:
        age = clock - doc.updated
        if age > timedelta(days=stale_days):
            result.warnings.append(f"Handoff Updated is older than {stale_days} days")

    success_text = " ".join(doc.success_criterion).lower()
    if doc.open_items and _MET_CLAIM.search(success_text):
        result.warnings.append("Success criterion says MET but Open items remain")

    return result


def handoff_sections_from_doc(doc: HandoffDocument) -> dict[str, Any]:
    """Structured section pointers for brain mirror / memory get consumers."""
    updated_at: str | None = None
    if doc.updated is not None:
        updated_at = doc.updated.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "updated_at": updated_at,
        "linear_p0": doc.linear_p0,
        "done": doc.done,
        "open": doc.open_items,
        "next_p0": doc.next_p0,
        "blockers": doc.blockers,
        "verify": doc.verify,
        "success_criterion": doc.success_criterion,
    }


def load_and_lint_handoff(project_root: Path) -> tuple[HandoffDocument | None, HandoffLintResult]:
    """Load handoff file if present and lint it."""
    path = handoff_path(project_root)
    if not path.is_file():
        return None, HandoffLintResult()
    text = path.read_text(encoding="utf-8")
    doc = parse_handoff_markdown(text)
    return doc, lint_handoff(doc)


__all__ = [
    "SESSION_HANDOFF_MEMORY_KEY",
    "HandoffDocument",
    "HandoffLintResult",
    "handoff_path",
    "handoff_sections_from_doc",
    "lint_handoff",
    "load_and_lint_handoff",
    "parse_handoff_markdown",
]

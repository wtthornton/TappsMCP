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

# The headings the parser understands, in template order. Quoted back at the
# author when nothing parsed, so a miss names the target set and not just the
# failure (TAP-6493).
RECOGNIZED_SECTION_HEADINGS: tuple[str, ...] = (
    "Done",
    "Open",
    "Next (P0)",
    "Blockers",
    "Changed files",
    "Verify",
    "Success criterion",
    "Cumulative",
)

# ``HandoffDocument`` attributes that hold parsed bullets, template order.
_SECTION_FIELDS: tuple[str, ...] = (
    "done",
    "open_items",
    "next_p0",
    "blockers",
    "changed_files",
    "verify",
    "success_criterion",
    "cumulative",
)


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
    changed_files: list[str] = field(default_factory=list)
    cumulative: list[str] = field(default_factory=list)
    recognized_headings: list[str] = field(default_factory=list)
    unrecognized_headings: list[str] = field(default_factory=list)
    section_lengths: dict[str, int] = field(default_factory=dict)
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
    """Map a ``##`` heading to a handoff section key.

    TAP-5362: any heading that begins with ``next`` (after normalize) maps to
    ``next_p0``, so suffixes like ``Next (P0 -> Production)`` are recognized.
    """
    norm = _normalize_header(header)
    if norm == "done":
        return "done"
    if norm == "open":
        return "open"
    # Bare "p0" kept for legacy templates; "next…" covers Next / Next (P0) / suffixes.
    if norm == "p0" or norm.startswith("next"):
        return "next_p0"
    if norm == "blockers":
        return "blockers"
    if norm == "verify":
        return "verify"
    if norm in {"success criterion", "success criteria"}:
        return "success_criterion"
    # Both carry a parenthetical suffix in the shipped template, so match on
    # the prefix rather than the whole heading.
    if norm.startswith("changed files"):
        return "changed_files"
    if norm.startswith("cumulative"):
        return "cumulative"
    return None


def _near_miss_next_headers(text: str) -> list[str]:
    """Return ``##`` headers that look like Next but did not map to ``next_p0``."""
    misses: list[str] = []
    for match in _SECTION_RE.finditer(text):
        header = match.group(1).strip()
        norm = _normalize_header(header)
        if _section_key(header) is not None:
            continue
        if "next" in norm or "p0" in norm:
            misses.append(header)
    return misses


# TAP-5669: marker and content are separated by one regex — a character-class
# lstrip("-* ") ate the opening ** of bold bullets, startswith(("-","*"))
# made numbered items invisible (blinding the P0 gate below), and a leading
# ``**bold**`` paragraph counted as a bullet. The marker must be followed by
# whitespace; content comes from the capture group untouched.
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(\S.*)$")


def _is_real_bullet(content: str) -> bool:
    """Judge bullet *content* (marker already removed) — no re-stripping."""
    if content.lower() in _IGNORE_BULLETS:
        return False
    if content.startswith("<") and content.endswith(">"):
        return False
    return not content.endswith("...")


def _extract_bullets(block: str) -> list[str]:
    items: list[str] = []
    for raw_line in block.splitlines():
        match = _BULLET_RE.match(raw_line)
        if match is None:
            continue
        bullet = match.group(1).strip()
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
        header = sections[idx].strip()
        body = sections[idx + 1]
        key = _section_key(header)
        # Every block is measured, recognized or not: an unrecognized heading
        # still consumes the brain value budget, so the over-cap message has
        # to be able to point at it (TAP-6444).
        doc.section_lengths[header] = doc.section_lengths.get(header, 0) + len(body)
        if key is None:
            doc.unrecognized_headings.append(header)
        else:
            doc.recognized_headings.append(header)
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
        elif key == "changed_files":
            doc.changed_files = _extract_bullets(body)
        elif key == "cumulative":
            doc.cumulative = _extract_bullets(body)
        idx += 2
    return doc


def populated_sections(doc: HandoffDocument) -> list[str]:
    """Section field names that parsed to at least one real bullet."""
    return [name for name in _SECTION_FIELDS if getattr(doc, name)]


def empty_parse_error(doc: HandoffDocument) -> str | None:
    """Describe a handoff that parsed to zero populated sections (TAP-6493).

    An unrecognized heading drops its bullets silently, so a handoff written
    against the wrong template parses to nothing, satisfies every other lint
    rule vacuously, and is written and mirrored as if it held work. The three
    causes need three different fixes, so they get three different messages:
    headings the parser did not recognize, recognized headings holding only
    placeholders, and no ``##`` headings at all.
    """
    if populated_sections(doc):
        return None
    expected = ", ".join(RECOGNIZED_SECTION_HEADINGS)
    if doc.unrecognized_headings:
        quoted = ", ".join(repr(header) for header in doc.unrecognized_headings)
        return (
            f"Handoff parsed to zero populated sections — unrecognized headings {quoted} "
            f"were dropped; expected one of: {expected}"
        )
    if doc.recognized_headings:
        quoted = ", ".join(repr(header) for header in doc.recognized_headings)
        return (
            f"Handoff parsed to zero populated sections — headings {quoted} are recognized "
            "but hold no content (only placeholders such as 'none', 'tbd' or '...'); "
            "fill at least one section"
        )
    return (
        "Handoff parsed to zero populated sections — no '## ' headings found; "
        f"expected one of: {expected}"
    )


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

    # First rule, because every rule below it is vacuously satisfied by an
    # all-empty parse: 'Open items exist but Next is missing' cannot fire when
    # Open itself parsed to nothing (TAP-6493).
    empty = empty_parse_error(doc)
    if empty is not None:
        result.errors.append(empty)

    if doc.open_items and not doc.next_p0:
        near_misses = _near_miss_next_headers(doc.raw_text)
        if near_misses:
            quoted = ", ".join(repr(h) for h in near_misses)
            result.errors.append(
                "Open items exist but Next section is unrecognized "
                f"(saw {quoted}) — use a heading that begins with Next"
            )
        else:
            # Covers both absent Next headers and Next present with only
            # placeholder bullets (none/n/a) filtered out by the parser.
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

    # The handoff template naturally produces bodies past the brain's per-value
    # cap, and the mirror then fails after the file has already been written.
    # Warn while the draft can still be shortened rather than at save time.
    size = handoff_size_report(doc.raw_text, doc=doc)
    if size.over:
        result.warnings.append(size.message())

    return result


def _brain_max_value_length() -> int:
    """The brain's per-value character cap (best-effort)."""
    try:
        from tapps_brain.models import MAX_VALUE_LENGTH
    except ImportError:  # pragma: no cover - brain always installed in practice
        return 4096
    return int(MAX_VALUE_LENGTH)


@dataclass(frozen=True)
class HandoffSizeReport:
    """How a handoff body measures against the brain's per-value cap."""

    length: int
    cap: int
    section_lengths: dict[str, int]

    @property
    def over(self) -> bool:
        return self.length > self.cap

    @property
    def over_by(self) -> int:
        return max(0, self.length - self.cap)

    @property
    def largest_section(self) -> tuple[str, int] | None:
        """The heading with the most body characters, or ``None`` if unsectioned."""
        if not self.section_lengths:
            return None
        return max(self.section_lengths.items(), key=lambda item: item[1])

    def message(self) -> str:
        """One line naming the actual size, the cap, and what to shorten."""
        largest = self.largest_section
        target = (
            f"shorten '## {largest[0]}' ({largest[1]} chars, the largest section)"
            if largest is not None
            else "shorten the body"
        )
        return (
            f"Handoff is {self.length} chars, {self.over_by} over the brain value cap "
            f"of {self.cap} — the cross-session mirror is rejected until it fits; "
            f"{target}."
        )


def handoff_size_report(
    markdown: str,
    *,
    doc: HandoffDocument | None = None,
    cap: int | None = None,
) -> HandoffSizeReport:
    """Measure a handoff body against the brain value cap, section by section."""
    parsed = doc if doc is not None else parse_handoff_markdown(markdown)
    return HandoffSizeReport(
        length=len(markdown),
        cap=_brain_max_value_length() if cap is None else cap,
        section_lengths=dict(parsed.section_lengths),
    )


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
        "changed_files": doc.changed_files,
        "cumulative": doc.cumulative,
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
    "RECOGNIZED_SECTION_HEADINGS",
    "SESSION_HANDOFF_MEMORY_KEY",
    "HandoffDocument",
    "HandoffLintResult",
    "HandoffSizeReport",
    "empty_parse_error",
    "handoff_path",
    "handoff_sections_from_doc",
    "handoff_size_report",
    "lint_handoff",
    "load_and_lint_handoff",
    "parse_handoff_markdown",
    "populated_sections",
]

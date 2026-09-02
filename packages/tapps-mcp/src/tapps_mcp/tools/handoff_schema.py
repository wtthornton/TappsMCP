"""Parse and lint ``.tapps-mcp/session-handoff.md`` (TAP-3573)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_HANDOFF_RELATIVE = Path(".tapps-mcp") / "session-handoff.md"
_HANDOFF_SLOT_DIR = Path(".tapps-mcp") / "handoffs"
_SLOT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
SESSION_HANDOFF_MEMORY_KEY = "session-handoff"
SESSION_HANDOFF_SLOT_PREFIX = f"{SESSION_HANDOFF_MEMORY_KEY}."
_PROGRAM_RE = re.compile(r"^\*\*Program:\*\*\s*(.+)$", re.IGNORECASE | re.MULTILINE)
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

    program: str | None = None
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


class InvalidHandoffSlotError(ValueError):
    """A handoff slot failed validation, before any path was written.

    Carries an Agent Gateway refusal envelope (docs/architecture/gateway-envelope.md)
    so the MCP and CLI surfaces can hand the agent a machine-readable ``code``
    instead of a stringified traceback.
    """

    def __init__(self, slot: str, reason: str, hint: str) -> None:
        self.slot = slot
        self.reason = reason
        self.envelope: dict[str, Any] = {
            "ok": False,
            "code": "invalid_handoff_slot",
            "gate": "handoff_slot_validation",
            "hint": hint,
            "extra": {"slot": slot, "reason": reason},
        }
        super().__init__(hint)


def validate_handoff_slot(slot: str) -> str:
    """First of two defences: the allowlist that states the slot policy.

    Rejects anything containing ``/``, ``.`` or ``..`` before the value can
    reach ``Path``, so traversal never becomes a path-join question.
    """
    if _SLOT_RE.match(slot) is None:
        raise InvalidHandoffSlotError(
            slot,
            "failed_allowlist",
            "Handoff slot must match ^[a-z0-9][a-z0-9-]{0,47}$ — lowercase letters, "
            "digits and dashes, starting with a letter or digit, at most 48 characters. "
            'Try slot="my-program".',
        )
    return slot


def _assert_slot_contained(candidate: Path, project_root: Path, slot: str) -> None:
    """Second of two defences: containment, checked after the join.

    Independent of :func:`validate_handoff_slot` on purpose. The allowlist is
    the policy and could be loosened; this check is what still holds if it is,
    and it is the only one that sees a symlinked ``handoffs/`` directory, which
    no regex can inspect.

    ``is_relative_to`` is purely lexical — on a non-resolved path it answers
    ``True`` for ``handoffs/../../../outside/x.md``. Both sides are therefore
    resolved first. Two anchors are needed and neither is redundant:
    the project root catches a ``handoffs/`` symlinked outside the repo (whose
    own ``resolve()`` would happily contain the target), and the slot directory
    catches a shallow ``../`` that stays inside the repo.
    """
    resolved = candidate.resolve()
    if not resolved.is_relative_to(project_root.resolve()):
        raise InvalidHandoffSlotError(
            slot,
            "escapes_project_root",
            f"Handoff slot {slot!r} resolves to {resolved}, outside the project root. "
            "Check whether .tapps-mcp/handoffs is a symlink.",
        )
    if not resolved.is_relative_to((project_root / _HANDOFF_SLOT_DIR).resolve()):
        raise InvalidHandoffSlotError(
            slot,
            "escapes_slot_dir",
            f"Handoff slot {slot!r} resolves to {resolved}, outside {_HANDOFF_SLOT_DIR}.",
        )


def handoff_path(project_root: Path, slot: str | None = None) -> Path:
    """The single site that names a handoff file.

    No slot returns the path this repo has always used. A slot namespaces the
    handoff under ``.tapps-mcp/handoffs/`` so concurrent programs stop
    overwriting one another (TAP-6870).
    """
    if slot is None:
        return project_root / _HANDOFF_RELATIVE
    validate_handoff_slot(slot)
    candidate = project_root / _HANDOFF_SLOT_DIR / f"{slot}.md"
    _assert_slot_contained(candidate, project_root, slot)
    return candidate


def handoff_memory_key(slot: str | None = None) -> str:
    """The single site that names a handoff's brain row.

    No slot returns :data:`SESSION_HANDOFF_MEMORY_KEY` unchanged, so the ~35
    repos that never pass a slot keep writing the row they already have.

    A slot is joined with a **dot**. The brain validates every ``MemoryEntry.key``
    against ``^[a-z0-9][a-z0-9._-]{0,127}$`` server-side, so the ``:`` this
    originally used produced a key no production write could store (TAP-6873).
    A dot also reverse-parses exactly — :func:`validate_handoff_slot` forbids
    dots in a slot, so ``key.split(".", 1)`` cannot be ambiguous — and matches
    the compound keys the rest of the codebase already writes
    (``mission.<id>.<run>.<kind>``, ``audit.coverage.<path>``).
    """
    if slot is None:
        return SESSION_HANDOFF_MEMORY_KEY
    validate_handoff_slot(slot)
    return f"{SESSION_HANDOFF_SLOT_PREFIX}{slot}"


def is_session_handoff_key(key: str) -> bool:
    """Whether *key* names a handoff row — the default one or any slot.

    Replaces the ``key == SESSION_HANDOFF_MEMORY_KEY`` equality that gated
    handoff enrichment: under it a slotted row silently came back without its
    ``handoff_sections`` and ``handoff_metadata`` (TAP-6873). Anchored on the
    prefix *including* its dot, so neighbouring keys such as
    ``session-handoffs`` do not match.
    """
    return key == SESSION_HANDOFF_MEMORY_KEY or key.startswith(SESSION_HANDOFF_SLOT_PREFIX)


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


def _parse_program(raw: str) -> str | None:
    """The program that owns this handoff, or ``None`` when it is not stated.

    An unedited ``<program or campaign name>`` placeholder is *not* an identity:
    two agents that both left it would otherwise read as the same program and
    the ownership guard would wave the overwrite through (TAP-6872).
    """
    value = raw.strip()
    if not value or value.lower() in _IGNORE_BULLETS:
        return None
    if value.startswith("<") and value.endswith(">"):
        return None
    return value


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
    program_match = _PROGRAM_RE.search(text)
    if program_match:
        doc.program = _parse_program(program_match.group(1))
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


def load_and_lint_handoff(
    project_root: Path,
    slot: str | None = None,
) -> tuple[HandoffDocument | None, HandoffLintResult]:
    """Load handoff file if present and lint it.

    The path comes from :func:`handoff_path`, never from a literal composed
    here — the read side and the write side must agree on what a slot names.
    """
    path = handoff_path(project_root, slot)
    if not path.is_file():
        return None, HandoffLintResult()
    text = path.read_text(encoding="utf-8")
    doc = parse_handoff_markdown(text)
    return doc, lint_handoff(doc)


def _handoff_row(path: Path, slot: str | None, now: datetime) -> dict[str, Any]:
    """One enumerated handoff, described from the document itself."""
    doc = parse_handoff_markdown(path.read_text(encoding="utf-8"))
    updated: str | None = None
    age_hours: float | None = None
    if doc.updated is not None:
        updated = doc.updated.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        age_hours = (now - doc.updated).total_seconds() / 3600.0
    return {
        "slot": slot,
        "path": str(path),
        "program": doc.program,
        "updated": updated,
        "linear_p0": doc.linear_p0,
        "age_hours": age_hours,
    }


def list_handoffs(project_root: Path, *, now: datetime | None = None) -> list[dict[str, Any]]:
    """Every live handoff in *project_root*, newest first.

    The **single enumeration site**: the continue-session skill, the
    ``handoff list`` CLI and ``fleet_audit`` all read this rather than each
    globbing ``handoffs/`` for itself. A second glob is the restatement
    :func:`handoff_path` exists to prevent, one directory up.

    Covers the default file plus one row per ``handoffs/<slot>.md``. The
    archive is excluded structurally, not by a name filter: it lives at
    ``handoffs/archive/`` and the glob below is non-recursive, so a superseded
    handoff can never be offered as a live one.

    Rows carry ``{slot, path, program, updated, linear_p0, age_hours}``. There
    is deliberately no ``git_sha``: the only source for it is the ``**Git:**``
    header, whose parsing spec §6 places out of scope for this program, and a
    key that is permanently ``None`` reads as data while carrying none.
    """
    clock = now if now is not None else datetime.now(tz=UTC)
    rows: list[dict[str, Any]] = []

    default = handoff_path(project_root)
    if default.is_file():
        rows.append(_handoff_row(default, None, clock))

    slot_dir = project_root / _HANDOFF_SLOT_DIR
    if slot_dir.is_dir():
        for path in sorted(slot_dir.glob("*.md")):
            if path.is_file():
                rows.append(_handoff_row(path, path.stem, clock))

    # ``updated`` is optional, so it cannot be the sort key on its own. A
    # handoff that never stated one sorts last rather than crashing the sort or
    # jumping the queue on a falsy comparison.
    rows.sort(key=lambda row: (row["updated"] is not None, row["updated"] or ""), reverse=True)
    return rows


__all__ = [
    "RECOGNIZED_SECTION_HEADINGS",
    "SESSION_HANDOFF_MEMORY_KEY",
    "SESSION_HANDOFF_SLOT_PREFIX",
    "HandoffDocument",
    "HandoffLintResult",
    "HandoffSizeReport",
    "InvalidHandoffSlotError",
    "empty_parse_error",
    "handoff_memory_key",
    "handoff_path",
    "handoff_sections_from_doc",
    "handoff_size_report",
    "is_session_handoff_key",
    "lint_handoff",
    "list_handoffs",
    "load_and_lint_handoff",
    "parse_handoff_markdown",
    "populated_sections",
    "validate_handoff_slot",
]

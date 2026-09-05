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
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from tapps_mcp import __version__
from tapps_mcp.pipeline.skill_asset_policy import policy_header

if TYPE_CHECKING:
    from pathlib import Path

Action = Literal["created", "refreshed", "migrated", "unchanged"]

# A finding's kind discriminates a genuine conflict (``contradiction``) from a
# harmless restatement (``near_duplicate``, not currently produced by any
# detector below but reserved so the two are never conflated in code or in a
# response payload).
FindingKind = Literal["contradiction", "near_duplicate"]

MARKER_BEGIN_PREFIX = "<!-- BEGIN: tapps-skill"
MARKER_END = "<!-- END: tapps-skill -->"

UPGRADE_POLICY_OVERWRITE_MARKER = "upgrade-policy: overwrite"

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


def extract_block(content: str) -> str | None:
    """Return the ``BEGIN..END`` managed-block substring, or ``None`` if absent.

    Shared by doctor's content-fingerprint checks (TAP-6948, TAP-6944) so the
    span logic lives in one place instead of each caller re-deriving it from
    :data:`MARKER_BEGIN_PREFIX` / :data:`MARKER_END`.
    """
    span = _find_block_span(content)
    if span is None:
        return None
    begin, end = span
    return content[begin:end]


def normalize_block_version(block: str) -> str:
    """Blank the version stamp in a managed block's BEGIN marker.

    A smart-merge block is unconditionally refreshed on every
    ``generate_skills`` run, so a bare version bump between releases is not
    itself staleness — the content-fingerprint checks in
    :mod:`tapps_mcp.distribution.doctor_skills` compare blocks after this
    normalization so they catch real drift without flagging every project
    that hasn't re-run ``tapps-mcp upgrade`` since the last patch release.
    """
    return _VERSION_RE.sub(lambda m: f"<!-- BEGIN: tapps-skill {m.group(1)} vX -->", block)


_BULLET_RE = re.compile(r"^[ \t]*[-*][ \t]+\S.*$", re.MULTILINE)
_MARKDOWN_EMPHASIS_RE = re.compile(r"[*_`]")
_NON_WORD_RE = re.compile(r"[^\w\s]")
_WHITESPACE_RE = re.compile(r"\s+")

_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "is",
        "are",
        "at",
        "by",
        "as",
        "that",
        "this",
        "it",
        "its",
        "be",
        "with",
        "not",
        "no",
        "never",
        "always",
        "from",
        "into",
        "than",
        "then",
        "when",
        "which",
        "each",
        "any",
        "all",
        "one",
    }
)

# Two bullets that share at least this fraction of their significant words
# (relative to the smaller bullet) are "about the same thing." Below it they
# are treated as unrelated, which is what lets a genuinely new project-region
# rule pass through acceptance criterion 3 without ever being compared.
_SUBJECT_OVERLAP_THRESHOLD = 0.3
# Above this Jaccard similarity, two same-subject bullets are a restatement
# (near_duplicate), not a conflict — the discriminator between "adds detail"
# and "disagrees."
_NEAR_DUPLICATE_JACCARD = 0.7


def bullet_spans(text: str) -> list[tuple[int, int, str]]:
    """Return ``(start, end, raw_line)`` for every top-level ``-``/``*`` bullet."""
    return [(m.start(), m.end(), m.group(0)) for m in _BULLET_RE.finditer(text)]


def normalize_bullet_text(raw: str) -> str:
    """Collapse a bullet line to comparable prose: no marker, markup, or case."""
    stripped = re.sub(r"^[ \t]*[-*][ \t]+", "", raw)
    stripped = _MARKDOWN_EMPHASIS_RE.sub("", stripped)
    stripped = _NON_WORD_RE.sub(" ", stripped.lower())
    return _WHITESPACE_RE.sub(" ", stripped).strip()


def significant_words(normalized: str) -> frozenset[str]:
    return frozenset(w for w in normalized.split(" ") if len(w) >= 3 and w not in _STOPWORDS)


def line_number(content: str, offset: int) -> int:
    return content.count("\n", 0, offset) + 1


@dataclass(frozen=True)
class Contradiction:
    """A managed-block bullet and a project-region bullet that disagree.

    ``kind`` is always ``"contradiction"`` here — see :data:`FindingKind`.
    Both anchors are reported; the check never decides which side is right.
    """

    managed_text: str
    managed_line: int
    project_text: str
    project_line: int
    kind: FindingKind = "contradiction"


def find_contradictions(content: str) -> list[Contradiction]:
    """Flag managed-block / project-region bullets that share a subject but disagree.

    Deterministic and reproducible from *content*'s bytes alone — no model call.
    A project-region bullet whose significant words don't overlap any
    managed-block bullet (a genuinely new rule) is never compared, so it never
    flags. A near-identical restatement (Jaccard >= 0.7) is treated as
    agreement, not conflict. Returns ``[]`` when *content* has no managed
    block. Never resolves a conflict — both sides are reported for a human (or
    a later adjudication step) to decide.
    """
    span = _find_block_span(content)
    if span is None:
        return []
    begin, end = span

    managed_bullets = [
        (begin + s, begin + e, raw) for s, e, raw in bullet_spans(content[begin:end])
    ]
    project_bullets = [(s, e, raw) for s, e, raw in bullet_spans(content[:begin])]
    project_bullets += [(end + s, end + e, raw) for s, e, raw in bullet_spans(content[end:])]

    findings: list[Contradiction] = []
    for m_start, _m_end, m_raw in managed_bullets:
        m_words = significant_words(normalize_bullet_text(m_raw))
        if not m_words:
            continue
        for p_start, _p_end, p_raw in project_bullets:
            p_norm = normalize_bullet_text(p_raw)
            if p_norm == normalize_bullet_text(m_raw):
                continue
            p_words = significant_words(p_norm)
            if not p_words:
                continue
            shared = m_words & p_words
            if not shared:
                continue
            overlap = len(shared) / min(len(m_words), len(p_words))
            if overlap < _SUBJECT_OVERLAP_THRESHOLD:
                continue
            jaccard = len(shared) / len(m_words | p_words)
            if jaccard >= _NEAR_DUPLICATE_JACCARD:
                continue
            findings.append(
                Contradiction(
                    managed_text=m_raw.strip(),
                    managed_line=line_number(content, m_start),
                    project_text=p_raw.strip(),
                    project_line=line_number(content, p_start),
                )
            )
    return findings


Region = Literal["managed_block", "project_region"]


@dataclass(frozen=True)
class PromoteOutcome:
    """Result of a :func:`promote_rule` call."""

    accepted: bool
    region: Region
    reason: str
    generator_file: str | None = None


def resolve_region(content: str, offset: int) -> Region:
    span = _find_block_span(content)
    if span is not None:
        begin, end = span
        if begin <= offset < end:
            return "managed_block"
    return "project_region"


def promote_rule(content: str, insertion_offset: int, *, generator_file: str) -> PromoteOutcome:
    """Guard a promotion's destination before it is written anywhere.

    A promotion moves a rule out of a skill file to a more durable home. Two
    destinations are unsafe regardless of what the caller intended:

    - **Inside the managed block** — the next ``tapps_upgrade`` regenerates
      that span from *generator_file* and silently erases the promoted rule.
    - **Anywhere in a file marked** ``upgrade-policy: overwrite`` — the whole
      file is replaced wholesale on upgrade, so no position in it is safe.

    Promoting to a point below the END marker (or anywhere outside the block
    in a non-overwrite file) is accepted and reports ``region="project_region"``.
    Resolves the region from :func:`_find_block_span`'s existing marker spans;
    never auto-resolves a refusal.
    """
    if UPGRADE_POLICY_OVERWRITE_MARKER in content:
        region = resolve_region(content, insertion_offset)
        return PromoteOutcome(
            accepted=False,
            region=region,
            reason=(
                f"promotion refused: this file carries {UPGRADE_POLICY_OVERWRITE_MARKER!r} — "
                "the whole file is replaced wholesale on the next tapps_upgrade, so no "
                "position in it survives. Fold the change upstream into the generator instead."
            ),
            generator_file=generator_file,
        )

    region = resolve_region(content, insertion_offset)
    if region == "managed_block":
        return PromoteOutcome(
            accepted=False,
            region=region,
            reason=(
                "promotion refused: the insertion point falls inside the managed block, "
                "where it will be silently erased on the next tapps_upgrade. Promote it "
                f"into {generator_file} instead — the upstream generator that produces "
                "this block."
            ),
            generator_file=generator_file,
        )

    return PromoteOutcome(
        accepted=True,
        region="project_region",
        reason="promoted below the END marker; this region survives every tapps_upgrade.",
        generator_file=None,
    )


def wrap_with_markers(body: str, skill_name: str, *, version: str = __version__) -> str:
    """Return *body* as ``frontmatter + BEGIN..END block``, frontmatter first.

    The markers wrap only the prose below the frontmatter. Wrapping the whole
    body — frontmatter included — pushed the opening ``---`` off line 1 and made
    every generated skill unparseable.

    TAP-6598: the managed-block policy note (:func:`policy_header`) is emitted
    as the first line inside the block, directly after BEGIN. It is baked in
    here rather than left to each caller so every skill routed through this
    function warns that edits inside the block are lost on the next
    ``tapps_upgrade`` — there is no call site that can forget it.
    """
    frontmatter, rest = split_frontmatter(body)
    inner = rest.strip("\n")
    header = policy_header("managed_block")
    block = f"{MARKER_BEGIN_PREFIX} {skill_name} v{version} -->\n{header}\n\n{inner}\n{MARKER_END}"
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
        # Legacy unmarked skill: preserve the prior body as a project region,
        # minus its own frontmatter — frontmatter is platform-owned and already
        # rewritten above (mirrors the marker-present branch's split_frontmatter
        # call), so a stale ``tools:`` grant from before TAP-6497 does not
        # survive the migration.
        _, legacy_body = split_frontmatter(original)
        preserved = legacy_body.strip("\n")
        updated = f"{frontmatter}{new_block}\n\n{PROJECT_REGION_HEADING}\n\n{preserved}\n"
        action = "migrated"

    if not dry_run:
        path.write_text(updated, encoding="utf-8")
    return action


# TAP-6854 criterion 5 ("the learnings.md ceiling is enforced by a check, not
# by prose"). The orchestration-prompt SKILL.md body (platform_skill_orchestration.py)
# tells the agent "Past roughly 120 bullets or 40 KB, merge overlapping lines" —
# prose only, nothing ever measured it. TAP-6861 (branch tap-6861-skill-learnings,
# PR #345, unmerged at the time this was written) ships a fuller learnings.md audit
# — near-duplicate detection, contradiction detection, single-home verification —
# built on bullet_spans()/Region primitives this branch does not have. Pulling that
# whole module in would mean depending on unmerged code at runtime, which this fix
# does not do. This is the minimal standalone half: the same two thresholds the
# prose names, measured from file bytes alone, with no other dependency. Once
# TAP-6861 lands, this should be replaced by (or delegate to) its size_finding().
LEARNINGS_CEILING_BYTES = 40_000
LEARNINGS_CEILING_BULLETS = 120

# A top-level bullet: a line starting with "- " at column 0. Continuation text
# and nested detail lines are indented, so they are not counted — this matches
# how the prose instruction ("120 bullets") reads: one bullet per lesson.
_TOP_LEVEL_BULLET_RE = re.compile(r"^- ", re.MULTILINE)


@dataclass(frozen=True)
class LearningsSizeFinding:
    """``learnings.md`` byte size and top-level bullet count against the ceiling.

    ``bytes_over``/``bullets_over`` (TAP-6857 box 3) distinguish which ceiling
    actually breached — a file 1 byte over on bytes and a file 3x over on
    bytes previously read identically through ``over_ceiling`` alone.
    """

    size_bytes: int
    bullet_count: int
    ceiling_bytes: int
    ceiling_bullets: int
    bytes_over: bool
    bullets_over: bool

    @property
    def over_ceiling(self) -> bool:
        return self.bytes_over or self.bullets_over

    @property
    def breached_ceiling(self) -> str:
        """Name which ceiling(s) actually breached — never both raw numbers alone."""
        if self.bytes_over and self.bullets_over:
            return "both"
        if self.bytes_over:
            return "byte ceiling"
        if self.bullets_over:
            return "bullet ceiling"
        return "none"


def learnings_size_finding(
    learnings_md: str,
    *,
    ceiling_bytes: int = LEARNINGS_CEILING_BYTES,
    ceiling_bullets: int = LEARNINGS_CEILING_BULLETS,
) -> LearningsSizeFinding:
    """Measure *learnings_md* against the ceiling the skill's own prose names.

    Flags ``over_ceiling`` when either threshold is exceeded — matching "Past
    roughly 120 bullets **or** 40 KB, merge" in the emitted SKILL.md body.
    """
    size_bytes = len(learnings_md.encode("utf-8"))
    bullet_count = len(_TOP_LEVEL_BULLET_RE.findall(learnings_md))
    return LearningsSizeFinding(
        size_bytes=size_bytes,
        bullet_count=bullet_count,
        ceiling_bytes=ceiling_bytes,
        ceiling_bullets=ceiling_bullets,
        bytes_over=size_bytes > ceiling_bytes,
        bullets_over=bullet_count > ceiling_bullets,
    )


__all__ = [
    "LEARNINGS_CEILING_BULLETS",
    "LEARNINGS_CEILING_BYTES",
    "MARKER_BEGIN_PREFIX",
    "MARKER_END",
    "PROJECT_REGION_HEADING",
    "UPGRADE_POLICY_OVERWRITE_MARKER",
    "Action",
    "Contradiction",
    "FindingKind",
    "LearningsSizeFinding",
    "PromoteOutcome",
    "Region",
    "bullet_spans",
    "extract_block",
    "find_contradictions",
    "install_or_refresh_skill",
    "learnings_size_finding",
    "line_number",
    "normalize_block_version",
    "normalize_bullet_text",
    "prepend_below_frontmatter",
    "promote_rule",
    "resolve_region",
    "significant_words",
    "split_frontmatter",
    "wrap_with_markers",
]

"""Deterministic audit / promote / verify / trim for a skill's learnings pair.

An ``orchestration-prompt``-style skill ships two files with opposite update
rules: ``SKILL.md`` (managed-block + project-region, see
:mod:`tapps_mcp.pipeline.skill_managed_block`) and ``learnings.md``
(create-only, append-only). Nothing today compares them, so they drift in
four measurable ways — the log outgrows its ceiling, durable rules pile up
in the log instead of the skill body, the same lesson gets restated, and a
promoted rule survives in both files after the move. Every check in this
module is reproducible from file bytes alone; there is no model call in the
code path (TAP-6861 out-of-scope: semantic judgement — is a lesson
generalizable, which duplicate survives — stays with the agent that consumes
these findings).

TAP-6857 ("learnings ceiling is prose, not a check") has not landed as a
standalone module at the time this was written. :data:`LEARNINGS_CEILING_BYTES`
is this module's own copy of that threshold; if TAP-6857 ships a shared
constant later, the :func:`size_finding` check should import it instead of
asserting its own.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from tapps_mcp.pipeline.skill_managed_block import (
    Contradiction,
    Region,
    bullet_spans,
    find_contradictions,
    line_number,
    normalize_bullet_text,
    resolve_region,
    significant_words,
)

# Same rationale as skill_managed_block's contradiction thresholds: bullets
# sharing at least this fraction of significant words (over the smaller
# side) are "about the same thing," and above this Jaccard they are a
# restatement rather than merely related.
_SUBJECT_OVERLAP_THRESHOLD = 0.3
_NEAR_DUPLICATE_JACCARD = 0.7

# 2026-09-01 manual pass: nlt-orchestrator's learnings.md was 103132 bytes
# against this ceiling — 2.5x over, invisible because only the bullet count
# is legible at a glance.
LEARNINGS_CEILING_BYTES = 40_000

# A learnings.md line that names where the rule lives instead of restating
# it. Matched against normalize_bullet_text() output (lowercased, punctuation
# stripped to spaces), so "SKILL.md", "skill.md §Testing", etc. all collapse
# to a "skill md" substring.
_POINTER_RE = re.compile(r"\bsee\b.*\bskill md\b")


def _bullet_similarity(raw_a: str, raw_b: str) -> tuple[float, float]:
    """Return ``(subject_overlap, jaccard)`` between two bullets' significant words.

    Both are ``0.0`` when either side has no significant words or the two
    share none. ``subject_overlap`` is shared words over the smaller side's
    count; ``jaccard`` is shared over the union.
    """
    a_words = significant_words(normalize_bullet_text(raw_a))
    b_words = significant_words(normalize_bullet_text(raw_b))
    if not a_words or not b_words:
        return 0.0, 0.0
    shared = a_words & b_words
    if not shared:
        return 0.0, 0.0
    overlap = len(shared) / min(len(a_words), len(b_words))
    jaccard = len(shared) / len(a_words | b_words)
    return overlap, jaccard


def _is_pointer_line(raw: str) -> bool:
    """Return whether *raw* only names a rule's location rather than restating it."""
    return bool(_POINTER_RE.search(normalize_bullet_text(raw)))


_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", re.MULTILINE)


def _nearest_heading_anchor(content: str, offset: int) -> str:
    """Return the nearest markdown heading at or above *offset*, or a line anchor."""
    best: str | None = None
    for match in _HEADING_RE.finditer(content):
        if match.start() > offset:
            break
        best = match.group(2).strip()
    if best is not None:
        return best
    return f"line {line_number(content, offset)}"


def bullet_content_hash(raw: str) -> str:
    """Return a stable content hash for a bullet, keyed off its normalized text.

    Used by :func:`apply_trim` to address bullets by content instead of line
    number, which shifts under every deletion (TAP-6866).
    """
    return hashlib.sha256(normalize_bullet_text(raw).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# TAP-6862: audit
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SizeFinding:
    """``learnings.md`` byte size and top-level bullet count against the ceiling."""

    bytes: int
    bullet_count: int
    ceiling_bytes: int
    over_ceiling: bool
    kind: Literal["size"] = "size"


@dataclass(frozen=True)
class AlreadyCoveredFinding:
    """A learnings bullet whose distinctive content already appears in SKILL.md."""

    learnings_text: str
    learnings_line: int
    skill_text: str
    covering_anchor: str
    kind: Literal["already_covered"] = "already_covered"


@dataclass(frozen=True)
class LearningsBulletRef:
    text: str
    line: int


@dataclass(frozen=True)
class NearDuplicateCluster:
    """A group of learnings bullets restating the same lesson."""

    members: tuple[LearningsBulletRef, ...]
    suggested_survivor_line: int
    kind: Literal["near_duplicate"] = "near_duplicate"


@dataclass(frozen=True)
class RegionFinding:
    """A bullet already present in SKILL.md, tagged by which region it lives in."""

    text: str
    line: int
    region: Region
    kind: Literal["region"] = "region"


@dataclass(frozen=True)
class AuditReport:
    size: SizeFinding
    already_covered: tuple[AlreadyCoveredFinding, ...]
    near_duplicate: tuple[NearDuplicateCluster, ...]
    contradictions: tuple[Contradiction, ...]
    region: tuple[RegionFinding, ...]


def size_finding(learnings_md: str, *, ceiling_bytes: int = LEARNINGS_CEILING_BYTES) -> SizeFinding:
    size_bytes = len(learnings_md.encode("utf-8"))
    bullet_count = len(bullet_spans(learnings_md))
    return SizeFinding(
        bytes=size_bytes,
        bullet_count=bullet_count,
        ceiling_bytes=ceiling_bytes,
        over_ceiling=size_bytes > ceiling_bytes,
    )


def _already_covered_findings(
    skill_md: str, learnings_md: str
) -> tuple[AlreadyCoveredFinding, ...]:
    skill_bullets = bullet_spans(skill_md)
    findings: list[AlreadyCoveredFinding] = []
    for l_start, _l_end, l_raw in bullet_spans(learnings_md):
        for s_start, _s_end, s_raw in skill_bullets:
            overlap, jaccard = _bullet_similarity(l_raw, s_raw)
            if overlap < _SUBJECT_OVERLAP_THRESHOLD or jaccard < _NEAR_DUPLICATE_JACCARD:
                continue
            findings.append(
                AlreadyCoveredFinding(
                    learnings_text=l_raw.strip(),
                    learnings_line=line_number(learnings_md, l_start),
                    skill_text=s_raw.strip(),
                    covering_anchor=_nearest_heading_anchor(skill_md, s_start),
                )
            )
            break  # first covering anchor is enough; don't multi-report one bullet
    return tuple(findings)


def _near_duplicate_clusters(learnings_md: str) -> tuple[NearDuplicateCluster, ...]:
    bullets = bullet_spans(learnings_md)
    n = len(bullets)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    for i in range(n):
        for j in range(i + 1, n):
            overlap, jaccard = _bullet_similarity(bullets[i][2], bullets[j][2])
            if overlap >= _SUBJECT_OVERLAP_THRESHOLD and jaccard >= _NEAR_DUPLICATE_JACCARD:
                union(i, j)

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)

    clusters: list[NearDuplicateCluster] = []
    for indices in groups.values():
        if len(indices) < 2:
            continue
        members = tuple(
            LearningsBulletRef(
                text=bullets[i][2].strip(), line=line_number(learnings_md, bullets[i][0])
            )
            for i in indices
        )
        # Deterministic survivor: most significant words (most informative),
        # tie-broken by earliest line — never a model call, never arbitrary.
        survivor_idx = max(
            indices,
            key=lambda i: (
                len(significant_words(normalize_bullet_text(bullets[i][2]))),
                -bullets[i][0],
            ),
        )
        clusters.append(
            NearDuplicateCluster(
                members=members,
                suggested_survivor_line=line_number(learnings_md, bullets[survivor_idx][0]),
            )
        )
    return tuple(clusters)


def _region_findings(skill_md: str) -> tuple[RegionFinding, ...]:
    findings = []
    for start, _end, raw in bullet_spans(skill_md):
        findings.append(
            RegionFinding(
                text=raw.strip(),
                line=line_number(skill_md, start),
                region=resolve_region(skill_md, start),
            )
        )
    return tuple(findings)


def audit(
    skill_md: str, learnings_md: str, *, ceiling_bytes: int = LEARNINGS_CEILING_BYTES
) -> AuditReport:
    """Compare *skill_md* against *learnings_md* and return every finding class.

    Performs no writes. Every field is derived from the two strings' bytes —
    no model call anywhere in this path (TAP-6862 acceptance).
    """
    return AuditReport(
        size=size_finding(learnings_md, ceiling_bytes=ceiling_bytes),
        already_covered=_already_covered_findings(skill_md, learnings_md),
        near_duplicate=_near_duplicate_clusters(learnings_md),
        contradictions=tuple(find_contradictions(skill_md)),
        region=_region_findings(skill_md),
    )


# ---------------------------------------------------------------------------
# TAP-6865: single-home verify
# ---------------------------------------------------------------------------

VerifyStatus = Literal["ok", "present_in_both", "present_in_neither"]


@dataclass(frozen=True)
class VerifyResult:
    rule_text: str
    status: VerifyStatus
    skill_anchors: tuple[int, ...]
    learnings_anchors: tuple[int, ...]


def _matching_lines(content: str, rule_raw: str, *, exclude_pointers: bool) -> tuple[int, ...]:
    lines = []
    for start, _end, raw in bullet_spans(content):
        if exclude_pointers and _is_pointer_line(raw):
            continue
        overlap, jaccard = _bullet_similarity(raw, rule_raw)
        if overlap >= _SUBJECT_OVERLAP_THRESHOLD and jaccard >= _NEAR_DUPLICATE_JACCARD:
            lines.append(line_number(content, start))
    return tuple(lines)


def verify_single_home(
    rule_texts: list[str], skill_md: str, learnings_md: str
) -> list[VerifyResult]:
    """Assert each rule in *rule_texts* lives in exactly one of the two files.

    ``present_in_both`` and ``present_in_neither`` are distinct failures — the
    former means the move never deleted the original, the latter means the
    promotion deleted the bullet without landing it. A learnings.md line that
    only names the SKILL.md section (a pointer, e.g. "see SKILL.md
    §Testing") is a reference, not a restatement, and is excluded from the
    learnings-side match so it can never itself count as the second copy.
    Reproducible from file bytes; no model call.
    """
    results: list[VerifyResult] = []
    for rule in rule_texts:
        skill_anchors = _matching_lines(skill_md, rule, exclude_pointers=False)
        learnings_anchors = _matching_lines(learnings_md, rule, exclude_pointers=True)
        in_skill = bool(skill_anchors)
        in_learnings = bool(learnings_anchors)
        status: VerifyStatus
        if in_skill and in_learnings:
            status = "present_in_both"
        elif not in_skill and not in_learnings:
            status = "present_in_neither"
        else:
            status = "ok"
        results.append(
            VerifyResult(
                rule_text=rule,
                status=status,
                skill_anchors=skill_anchors,
                learnings_anchors=learnings_anchors,
            )
        )
    return results


# ---------------------------------------------------------------------------
# TAP-6866: safe trim (content-hash addressed, all-or-nothing)
# ---------------------------------------------------------------------------

TrimAction = Literal["delete", "keep_verbatim"]


@dataclass(frozen=True)
class TrimInstruction:
    content_hash: str
    action: TrimAction


@dataclass(frozen=True)
class TrimOutcome:
    applied: bool
    reason: str
    before_bytes: int
    after_bytes: int
    before_bullet_count: int
    after_bullet_count: int
    updated_text: str | None = None


def _refused(reason: str, before_bytes: int, before_count: int) -> TrimOutcome:
    return TrimOutcome(
        applied=False,
        reason=reason,
        before_bytes=before_bytes,
        after_bytes=before_bytes,
        before_bullet_count=before_count,
        after_bullet_count=before_count,
    )


def apply_trim(learnings_md: str, plan: list[TrimInstruction]) -> TrimOutcome:
    """Apply *plan* to *learnings_md*, addressing every bullet by content hash.

    Refuses the entire apply — writing nothing — the moment any hash fails to
    resolve to exactly one current bullet. There is no partial application:
    every instruction is re-anchored against the *current* text before any
    deletion happens, so a plan computed before this call cannot go stale
    mid-apply (TAP-6866).
    """
    bullets = bullet_spans(learnings_md)
    before_bytes = len(learnings_md.encode("utf-8"))
    before_count = len(bullets)

    hash_to_spans: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
    for start, end, raw in bullets:
        hash_to_spans[bullet_content_hash(raw)].append((start, end, raw))

    to_delete: list[tuple[int, int, str]] = []
    keep_hashes: set[str] = set()
    for instruction in plan:
        matches = hash_to_spans.get(instruction.content_hash, [])
        if len(matches) != 1:
            problem = (
                "did not resolve to any bullet" if not matches else "matched more than one bullet"
            )
            return _refused(
                f"refused: content hash {instruction.content_hash} {problem} — "
                "nothing was written.",
                before_bytes,
                before_count,
            )
        if instruction.action == "delete":
            to_delete.append(matches[0])
        else:
            keep_hashes.add(instruction.content_hash)

    updated = learnings_md
    for start, end, _raw in sorted(to_delete, key=lambda span: span[0], reverse=True):
        line_end = end + 1 if end < len(updated) and updated[end] == "\n" else end
        updated = updated[:start] + updated[line_end:]

    updated_hashes = {bullet_content_hash(raw) for _, _, raw in bullet_spans(updated)}
    missing_keeps = keep_hashes - updated_hashes
    if missing_keeps:
        return _refused(
            f"internal: keep-verbatim bullet(s) {sorted(missing_keeps)} missing after "
            "apply — nothing was written.",
            before_bytes,
            before_count,
        )

    after_bullets = bullet_spans(updated)
    return TrimOutcome(
        applied=True,
        reason=f"trim applied: {len(to_delete)} bullet(s) removed.",
        before_bytes=before_bytes,
        after_bytes=len(updated.encode("utf-8")),
        before_bullet_count=before_count,
        after_bullet_count=len(after_bullets),
        updated_text=updated,
    )


__all__ = [
    "LEARNINGS_CEILING_BYTES",
    "AlreadyCoveredFinding",
    "AuditReport",
    "LearningsBulletRef",
    "NearDuplicateCluster",
    "RegionFinding",
    "SizeFinding",
    "TrimAction",
    "TrimInstruction",
    "TrimOutcome",
    "VerifyResult",
    "VerifyStatus",
    "apply_trim",
    "audit",
    "bullet_content_hash",
    "size_finding",
    "verify_single_home",
]

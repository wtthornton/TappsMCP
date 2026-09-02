"""Monotonic quality-gate ratchet (TAP-6904).

``validate_changed`` applies one absolute overall-score threshold to every
changed file — including a file that was already below that threshold long
before the current change touched it. There is no honest path to remediate
such a file: fixing it means touching it, and touching it re-triggers the
same absolute failure. This module is that remediation path. It is opt-in
(``baseline_ref`` empty/unset is a no-op — see :func:`apply_ratchet_to_gate`)
and it only ever relaxes the *overall-score* failure, never a category
minimum, the complexity ceiling, or the security floor.

Three rules, checked in this order:

1. **Materially new code.** No recognisable ancestor at ``baseline_ref``
   -> the absolute threshold applies. New code is never grandfathered.
   Rule 1 keys on *content identity*, not on the path (TAP-6922): see
   :data:`SAME_FILE_SIMILARITY_PCT` and :func:`_resolve_baseline_content`.
2. **Passing file.** At or above threshold at ``baseline_ref`` -> the
   absolute threshold applies. A passing file may never fall below the bar
   through this path.
3. **Legacy-debt file.** Below threshold at ``baseline_ref`` -> passes only
   if the current score is not lower than the baseline score. Holding or
   improving passes; dropping further still fails, and the drop is reported.

Rule 1 keys on content, not on the path (TAP-6922). A path lookup answers
"is this a new *path*", which is the wrong question in both directions:
replacing every line of a below-threshold file leaves the path resolvable,
so brand-new code inherited the old content's low baseline; and moving a
below-threshold file makes its path unresolvable, so unchanged code was
thrown back onto the absolute bar this module exists to remove. One number,
:data:`SAME_FILE_SIMILARITY_PCT`, governs both directions.

Monotonicity: ``baseline_ref`` is always the merge-target ref (e.g. the PR's
base SHA), so the score this module compares against is whatever the
*previous* merge left behind. An improving PR raises that floor for the
merge target; the next PR's ``git show <new-base>:<path>`` then returns the
already-improved content, so rule 3 compares against the raised floor. A
file cannot ratchet downward in small steps because each step is judged
against a baseline that already includes the prior step's improvement.
"""

from __future__ import annotations

import collections
import dataclasses
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import structlog

_logger = structlog.get_logger(__name__)

RULE_NEW_FILE = "new_file_absolute"
RULE_MATERIALLY_NEW_CONTENT = "materially_new_content_absolute"
RULE_PASSING_AT_BASE = "passing_at_base_absolute"
RULE_BASE_SCORE_UNAVAILABLE = "base_score_unavailable_absolute"
RULE_RATCHET_HOLD_OR_IMPROVE = "ratchet_hold_or_improve"
RULE_RATCHETED_FAIL = "ratcheted_fail_regression"

SAME_FILE_SIMILARITY_PCT = 50
"""The one number rule 1 keys on: a file is *the same file* as its baseline
ancestor when at least this much of it is shared with that ancestor.

Used in both directions, which is the whole point — the two rule-1 holes
TAP-6922 closed pointed opposite ways precisely because path identity gave
the two directions different answers:

* **Moved file.** Handed to git as ``--find-renames=50%``, so git's own
  rename detector decides whether a path that vanished at the baseline is
  the ancestor of a path that appeared. Reusing git means there is one
  rename-similarity implementation in the system, not two.
* **Rewritten file.** Compared against :func:`_shared_fraction`, so a path
  that still resolves at the baseline but whose content no longer descends
  from it is judged as what it is: new code.

50 is not an arbitrary knob, and changing it is not a tuning exercise. It is
the only value at which the two directions are complements rather than
leaving a gap — at any ``t > 50`` a file with similarity between ``100 - t``
and ``t`` is simultaneously "not a rename" (so a *move* would be thrown onto
the absolute bar) and "not a rewrite" (so a *rewrite* would keep its stale
baseline), which is exactly the pair of opposed holes this replaced. Read it
as: **half the file has to survive for it to still be the same file.**
"""


@dataclasses.dataclass(frozen=True)
class RatchetOutcome:
    """Result of judging one file's overall-score failure under the ratchet."""

    rule: str
    base_score: float | None
    current_score: float
    threshold: float
    passes: bool
    message: str
    #: Baseline path the content was compared against — ``rel_path`` normally,
    #: the pre-rename path when git resolved a move, ``None`` when rule 1 found
    #: no ancestor at all. Recorded so a ratcheted pass always says *which*
    #: file it ratcheted against.
    base_path: str | None = None
    #: Percentage of the current content that survives from ``base_path`` at the
    #: baseline, i.e. what rule 1's rewrite direction actually decided on.
    #: ``None`` when it was not computed (no ancestor, or content unreadable).
    shared_pct: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def _read_file_at_ref(repo_root: Path, baseline_ref: str, rel_path: str) -> str | None:
    """Return *rel_path*'s content at *baseline_ref*, or ``None`` if absent there.

    Uses ``git show`` rather than checking the ref out — the working tree is
    never touched, so there is nothing to restore and nothing a crash mid-run
    can corrupt.

    Decoded as UTF-8 explicitly rather than via the ambient locale: the
    ratchet's whole contract is that byte-identical content scores
    identically, and a locale-dependent decode would break that for any
    source file with a non-ASCII character.
    """
    proc = subprocess.run(
        ["git", "show", f"{baseline_ref}:{rel_path}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout


def _significant_lines(text: str) -> list[str]:
    """Whitespace-stripped, blank-dropped lines — the unit rule 1 compares.

    Stripping means an indentation-only reflow (wrapping a block in a class,
    a ``try``, or an ``if``) does not read as new content, and dropping blank
    lines keeps formatting churn out of the measure. Both choices err the
    same way: they count *more* of the file as surviving, so they make rule 1
    slower to declare code "materially new". That is the safe direction — a
    false "materially new" would throw an honest refactor back onto the
    absolute bar this module exists to remove.
    """
    return [stripped for line in text.splitlines() if (stripped := line.strip())]


def _shared_fraction(base_content: str, current_content: str) -> float:
    """Fraction of *current_content*'s significant lines that survive from *base_content*.

    Deliberately **directional**, and that is the substantive departure from
    the symmetric similarity git uses for renames. A symmetric measure — and
    equally git's ``-B`` "damage" score, which counts deletions and additions
    alike — cannot tell these two apart:

    * a 2000-line module split into four, leaving 500 unchanged lines behind
      at the original path, and
    * a 500-line module whose every line was replaced,

    because both differ from the baseline by ~75%. The first is a refactor
    this repo does routinely and must not block; the second is the cheat
    TAP-6922 closed. Asking "how much of what is *here now* came from the
    baseline" separates them: the split scores 1.0 (nothing new arrived, code
    only left), the replacement scores ~0.0.

    Multiset intersection rather than a diff: it is O(n) with no quadratic
    worst case on a large file, and it is order-insensitive, so moving a
    function within a file is correctly not "new code".
    """
    current = _significant_lines(current_content)
    if not current:
        # Nothing is here now, so nothing here is new. Whatever the change
        # was, it was not the arrival of unvetted code.
        return 1.0
    remaining = collections.Counter(_significant_lines(base_content))
    shared = 0
    for line in current:
        if remaining[line] > 0:
            remaining[line] -= 1
            shared += 1
    return shared / len(current)


class RenameIndex:
    """``current path -> baseline path`` for one ``(repo_root, baseline_ref)`` pair.

    Rename detection is git's job, not this module's: one ``git diff
    --find-renames`` gives rule 1 the same similarity definition the rest of
    the toolchain already uses, at the same
    :data:`SAME_FILE_SIMILARITY_PCT` threshold.

    **Cost.** ``evaluate_ratchet`` runs once per changed file, so the index
    must not be. Two things keep it off the per-file path:

    * One instance is built per ``validate_changed`` batch (in
      ``_execute_validation_batch``) and passed to every file, so the
      subprocess runs at most once for the whole run rather than once per
      file.
    * The map is built **lazily**, on the first path that fails to resolve at
      the baseline. A run in which nothing moved never shells out at all, and
      that is the overwhelmingly common case.

    The diff itself is bounded by the number of *changed* paths between the
    baseline and the working tree, not by the size of the repository.

    **When rename information is unavailable** — the working directory is not
    a git repo, ``baseline_ref`` does not resolve, or git declines rename
    detection because the change set exceeds ``diff.renameLimit`` — the map
    comes back empty and rule 1 falls back to the pre-TAP-6922 path lookup: a
    path absent at the baseline is treated as new. That is a *stricter*
    answer than a guess would be, and it is the behaviour that shipped
    before, so an unavailable-rename-information run can only be as harsh as
    today, never more permissive.
    """

    __slots__ = ("_baseline_ref", "_map", "_repo_root")

    def __init__(self, repo_root: Path, baseline_ref: str) -> None:
        self._repo_root = repo_root
        self._baseline_ref = baseline_ref
        self._map: dict[str, str] | None = None

    def base_path_for(self, rel_path: str) -> str | None:
        """Return the baseline path *rel_path* was moved from, or ``None``."""
        if self._map is None:
            self._map = self._build()
        return self._map.get(rel_path)

    def _build(self) -> dict[str, str]:
        proc = subprocess.run(
            [
                "git",
                "diff",
                f"--find-renames={SAME_FILE_SIMILARITY_PCT}%",
                "--diff-filter=R",
                "--name-status",
                "-z",
                self._baseline_ref,
                "--",
            ],
            cwd=self._repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if proc.returncode != 0:
            _logger.warning(
                "ratchet_rename_detection_unavailable",
                baseline_ref=self._baseline_ref,
                error=proc.stderr.strip()[:200],
            )
            return {}
        return _parse_rename_records(proc.stdout)


def _parse_rename_records(stdout: str) -> dict[str, str]:
    """Parse ``--name-status -z`` output into ``new path -> old path``.

    NUL-separated because a path may legally contain a newline or a quote;
    ``-z`` also suppresses git's path quoting, so the bytes arrive as-is.
    Rename and copy records span three fields (``R100``, old, new); anything
    else spans two, and is stepped over rather than assumed absent — the
    ``--diff-filter=R`` should leave only renames, but a parser that silently
    desynchronises on an unexpected record would mis-map paths instead of
    ignoring them.
    """
    fields = stdout.split("\0")
    records: dict[str, str] = {}
    i = 0
    while i < len(fields):
        status = fields[i]
        if not status:
            i += 1
            continue
        if status[0] in ("R", "C") and i + 2 < len(fields):
            records[fields[i + 2]] = fields[i + 1]
            i += 3
        else:
            i += 2
    return records


async def _score_base_content(path: Path, content: str, scorer: Any, quick: bool) -> float:
    """Score *content* (the file as it existed at the baseline ref) **as** ``path``.

    The bytes are written to a throwaway directory created *next to* ``path``
    — never to ``path`` itself — so a crash mid-score leaves at most an
    orphaned scratch directory, never a corrupted tracked file.

    That scratch location is not a neutral place to score from, because the
    scorer derives several *weighted* categories from the path rather than
    from the bytes:

    * ``test_coverage`` builds the module's dotted import name from the path
      relative to the project root and asks whether any test imports it. An
      extra directory segment turns ``pkg.mod`` into
      ``pkg..ratchet-base-XXXX.mod``, which nothing imports, so the 4.0
      "a test imports this module" branch is missed (TAP-6921: 107 of this
      repo's 577 source files, each losing 5.20 points of baseline).
    * ``structure`` and ``devex`` look for project markers in an ancestor
      directory. Keeping the scratch dir one level below the file's real
      parent does preserve the project-root walk for these two — that part
      of the original design is sound and measured (both categories differ
      on zero files) — but preserving the project root was never sufficient,
      because the module name is derived from the *whole* relative path.
    * The non-Python scorers additionally look for sibling manifests
      (``go.mod``, ``Cargo.toml``, ``package.json``) and sibling test files,
      none of which exist next to the scratch copy.

    So the read path and the identity path are passed separately: the tools
    run against the scratch copy (that is where the bytes are), while every
    path-derived category is told to judge the content as ``path``. What
    remains path-derived after this is only what an *external tool* resolves
    for itself from the file it is handed — ruff's ``per-file-ignores``,
    bandit/pylint per-path config. Those feed the zero-weight ``linting``
    and ``type_checking`` categories, so they cannot move the overall score
    the ratchet compares.
    """
    scratch_dir = Path(tempfile.mkdtemp(dir=path.parent, prefix=".ratchet-base-"))
    try:
        scratch_path = scratch_dir / path.name
        scratch_path.write_text(content, encoding="utf-8")
        if quick:
            from tapps_core.config.settings import load_settings
            from tapps_mcp.server_scoring_tools import score_and_scan_quick

            score_result, _sec = await score_and_scan_quick(
                scratch_path, scorer, load_settings(), identity_path=path
            )
        else:
            score_result = await scorer.score_file(scratch_path, identity_path=path)
        return round(score_result.overall_score, 2)
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)


def _read_current_content(path: Path) -> str | None:
    """Return *path*'s working-tree text, or ``None`` if it cannot be read as text."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        _logger.warning("ratchet_current_read_failed", file=str(path), error=str(exc))
        return None


def _resolve_baseline_content(
    repo_root: Path, baseline_ref: str, rel_path: str, renames: RenameIndex
) -> tuple[str | None, str | None]:
    """Find the baseline ancestor of *rel_path*: ``(content, baseline path)``.

    Rule 1's first half. The same path at the baseline is the ancestor when
    it exists; otherwise git is asked whether the path is a *move* of one
    that vanished, and the ancestor is fetched from where it used to live.
    ``(None, None)`` means no ancestor — genuinely new code.
    """
    content = _read_file_at_ref(repo_root, baseline_ref, rel_path)
    if content is not None:
        return content, rel_path
    moved_from = renames.base_path_for(rel_path)
    if moved_from is None:
        return None, None
    return _read_file_at_ref(repo_root, baseline_ref, moved_from), moved_from


async def evaluate_ratchet(
    *,
    path: Path,
    repo_root: Path,
    baseline_ref: str,
    current_score: float,
    threshold: float,
    scorer: Any,
    quick: bool,
    renames: RenameIndex | None = None,
) -> RatchetOutcome:
    """Judge one file's overall-score failure against the three ratchet rules.

    ``renames`` is the batch-wide :class:`RenameIndex`; callers that judge
    more than one file should build one and pass it to all of them. Omitting
    it is correct but costs a private index per call — see
    :class:`RenameIndex` for why that is usually still free.
    """
    try:
        rel_path = path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        rel_path = str(path)

    if renames is None:
        renames = RenameIndex(repo_root, baseline_ref)

    # ---- Rule 1: is this materially new code? --------------------------
    # Keyed on content identity, not on the path (TAP-6922). Two questions,
    # one threshold (SAME_FILE_SIMILARITY_PCT): does this content have an
    # ancestor at the baseline at all, and if so, does what is here now
    # actually descend from it?
    base_content, base_path = _resolve_baseline_content(repo_root, baseline_ref, rel_path, renames)
    if base_content is None:
        return RatchetOutcome(
            rule=RULE_NEW_FILE,
            base_score=None,
            current_score=current_score,
            threshold=threshold,
            passes=False,
            message=(
                f"no ancestor at baseline {baseline_ref!r} (absent, and not a rename of any "
                "path that vanished there): new code, absolute threshold applies"
            ),
        )

    shared_pct: float | None = None
    current_content = _read_current_content(path)
    if current_content is not None:
        shared_pct = round(_shared_fraction(base_content, current_content) * 100, 1)
        if shared_pct < SAME_FILE_SIMILARITY_PCT:
            return RatchetOutcome(
                rule=RULE_MATERIALLY_NEW_CONTENT,
                base_score=None,
                current_score=current_score,
                threshold=threshold,
                passes=False,
                base_path=base_path,
                shared_pct=shared_pct,
                message=(
                    f"only {shared_pct}% of this file survives from {base_path!r} at baseline "
                    f"{baseline_ref!r} (< {SAME_FILE_SIMILARITY_PCT}%): materially new code, "
                    "absolute threshold applies"
                ),
            )
    # current_content is None: the bytes could not be read as text, so the
    # rewrite half of rule 1 has nothing to judge. Fall back to the
    # pre-TAP-6922 behaviour — the path resolved at the baseline, so treat
    # it as the same file — rather than guessing in either direction.

    try:
        base_score = await _score_base_content(path, base_content, scorer, quick)
    except Exception as exc:  # scoring the baseline copy must never crash the gate
        _logger.warning("ratchet_base_score_failed", file=str(path), error=str(exc))
        return RatchetOutcome(
            rule=RULE_BASE_SCORE_UNAVAILABLE,
            base_score=None,
            current_score=current_score,
            threshold=threshold,
            passes=False,
            base_path=base_path,
            shared_pct=shared_pct,
            message=f"could not score baseline content ({exc}); absolute threshold applies",
        )

    if base_score >= threshold:
        return RatchetOutcome(
            rule=RULE_PASSING_AT_BASE,
            base_score=base_score,
            current_score=current_score,
            threshold=threshold,
            passes=False,
            base_path=base_path,
            shared_pct=shared_pct,
            message=(
                f"base score {base_score} >= threshold {threshold}: "
                "was passing at baseline, absolute threshold applies"
            ),
        )

    if current_score >= base_score:
        return RatchetOutcome(
            rule=RULE_RATCHET_HOLD_OR_IMPROVE,
            base_score=base_score,
            current_score=current_score,
            threshold=threshold,
            passes=True,
            base_path=base_path,
            shared_pct=shared_pct,
            message=(
                f"ratcheted pass: {current_score} >= baseline {base_score} "
                f"(still below threshold {threshold}, but not worse)"
                + (f" [baseline read from {base_path}]" if base_path != rel_path else "")
            ),
        )

    return RatchetOutcome(
        rule=RULE_RATCHETED_FAIL,
        base_score=base_score,
        current_score=current_score,
        threshold=threshold,
        passes=False,
        base_path=base_path,
        shared_pct=shared_pct,
        message=f"regression: {current_score} < baseline {base_score} (threshold {threshold})",
    )


async def apply_ratchet_to_gate(
    gate: Any,
    *,
    score: Any,
    path: Path,
    scorer: Any,
    quick: bool,
    baseline_ref: str,
    repo_root: Path,
    renames: RenameIndex | None = None,
) -> dict[str, Any] | None:
    """Re-judge a failing gate's overall-score failure under the ratchet.

    Mutates *gate* in place (removing the "overall" failure and flipping
    ``passed`` to ``True``) only when the ratchet approves rule 3. Every
    other absolute failure on *gate* (a category minimum, the complexity
    ceiling, the security floor) is left untouched — those are never
    ratcheted.

    Returns ``None`` (a strict no-op) when ``baseline_ref`` is empty, the
    gate already passed, or the gate's failure is not an overall-score
    failure at all — in every one of those cases nothing about *gate* is
    read or written, which is what makes the no-``baseline_ref`` path
    byte-identical to pre-ratchet behaviour. Otherwise returns the ratchet
    decision as a dict for the caller to attach to the file's result, so a
    ratcheted pass is always distinguishable from an absolute one.
    """
    if not baseline_ref or gate.passed:
        return None
    overall_failure = next((f for f in gate.failures if f.category == "overall"), None)
    if overall_failure is None:
        return None

    outcome = await evaluate_ratchet(
        path=path,
        repo_root=repo_root,
        baseline_ref=baseline_ref,
        current_score=round(score.overall_score, 2),
        threshold=overall_failure.threshold,
        scorer=scorer,
        quick=quick,
        renames=renames,
    )
    if outcome.passes:
        gate.failures = [f for f in gate.failures if f.category != "overall"]
        gate.passed = len(gate.failures) == 0
    return outcome.as_dict()

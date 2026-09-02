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

1. **New file.** Absent at ``baseline_ref`` -> the absolute threshold
   applies. New code is never grandfathered.
2. **Passing file.** At or above threshold at ``baseline_ref`` -> the
   absolute threshold applies. A passing file may never fall below the bar
   through this path.
3. **Legacy-debt file.** Below threshold at ``baseline_ref`` -> passes only
   if the current score is not lower than the baseline score. Holding or
   improving passes; dropping further still fails, and the drop is reported.

Monotonicity: ``baseline_ref`` is always the merge-target ref (e.g. the PR's
base SHA), so the score this module compares against is whatever the
*previous* merge left behind. An improving PR raises that floor for the
merge target; the next PR's ``git show <new-base>:<path>`` then returns the
already-improved content, so rule 3 compares against the raised floor. A
file cannot ratchet downward in small steps because each step is judged
against a baseline that already includes the prior step's improvement.
"""

from __future__ import annotations

import dataclasses
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import structlog

_logger = structlog.get_logger(__name__)

RULE_NEW_FILE = "new_file_absolute"
RULE_PASSING_AT_BASE = "passing_at_base_absolute"
RULE_BASE_SCORE_UNAVAILABLE = "base_score_unavailable_absolute"
RULE_RATCHET_HOLD_OR_IMPROVE = "ratchet_hold_or_improve"
RULE_RATCHETED_FAIL = "ratcheted_fail_regression"


@dataclasses.dataclass(frozen=True)
class RatchetOutcome:
    """Result of judging one file's overall-score failure under the ratchet."""

    rule: str
    base_score: float | None
    current_score: float
    threshold: float
    passes: bool
    message: str

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


async def evaluate_ratchet(
    *,
    path: Path,
    repo_root: Path,
    baseline_ref: str,
    current_score: float,
    threshold: float,
    scorer: Any,
    quick: bool,
) -> RatchetOutcome:
    """Judge one file's overall-score failure against the three ratchet rules."""
    try:
        rel_path = path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        rel_path = str(path)

    base_content = _read_file_at_ref(repo_root, baseline_ref, rel_path)
    if base_content is None:
        return RatchetOutcome(
            rule=RULE_NEW_FILE,
            base_score=None,
            current_score=current_score,
            threshold=threshold,
            passes=False,
            message=(f"absent at baseline {baseline_ref!r}: new code, absolute threshold applies"),
        )

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
            message=f"could not score baseline content ({exc}); absolute threshold applies",
        )

    if base_score >= threshold:
        return RatchetOutcome(
            rule=RULE_PASSING_AT_BASE,
            base_score=base_score,
            current_score=current_score,
            threshold=threshold,
            passes=False,
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
            message=(
                f"ratcheted pass: {current_score} >= baseline {base_score} "
                f"(still below threshold {threshold}, but not worse)"
            ),
        )

    return RatchetOutcome(
        rule=RULE_RATCHETED_FAIL,
        base_score=base_score,
        current_score=current_score,
        threshold=threshold,
        passes=False,
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
    )
    if outcome.passes:
        gate.failures = [f for f in gate.failures if f.category != "overall"]
        gate.passed = len(gate.failures) == 0
    return outcome.as_dict()

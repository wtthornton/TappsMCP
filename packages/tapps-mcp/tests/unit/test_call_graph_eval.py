"""Precision/recall regression gate for the call-graph resolver.

This is the measurement backstop for resolver work. Unlike ``test_call_graph.py``
(functional, per-edge happy-path assertions), this test scores the resolver over
a hand-labeled corpus (``call_graph_eval.GOLDEN_CASES``) and enforces a ratchet:

* Precision/recall must not drop below the current floor.
* The set of missed/spurious edges must stay a SUBSET of the documented
  ``KNOWN_DEBT_*`` sets. That lets a resolver improvement (fewer misses) pass,
  while any NEW miss/fabrication — a regression — fails.

When resolver work fixes a known-debt item, remove it from the relevant
``KNOWN_DEBT_*`` set and raise the corresponding floor. The test then locks in
the improvement.
"""

from __future__ import annotations

from pathlib import Path

from tapps_mcp.project.call_graph_eval import GOLDEN_CASES, evaluate

# Current measured floors (2026-07-08). Raise these as debt is paid down.
# History:
#   - relative-import prefix + nested-scope over-attribution fixed: p0.77->0.92, r0.83->0.92
#   - type-annotation binding (def f(x: C) / x: C = ...): corpus grown, p/r 0.93.
#     Cleared ~44% of the genuinely-fixable in-repo unresolved_static_call bucket
#     on the real repo (598->335 misses; edges 32315->34382; in_repo_gap_rate 0.61->0.51).
_PRECISION_FLOOR = 0.93
_RECALL_FLOOR = 0.93

# Documented resolver debt. Each entry is a genuine resolver limitation, not a
# fixture-labeling error (verified against the actual index). Shrink these sets
# as the resolver improves; never grow them without a deliberate justification.
KNOWN_DEBT_MISSED = {
    # Re-export chains: binds to the re-export name, not the definition site.
    # Needs a cross-file export-table pass (Python has no equivalent of the TS
    # cross-file resolution post-pass today).
    "reexport_call: pkg.app.handler -> pkg.core.engine",
}
KNOWN_DEBT_SPURIOUS = {
    # Re-export chain resolves one hop short (to the re-export module name).
    "reexport_call: pkg.app.handler -> pkg.api.engine",
}


def test_edge_precision_recall_meets_floor(tmp_path: Path) -> None:
    report = evaluate(tmp_path, GOLDEN_CASES)
    summary = report.summary()
    assert report.precision >= _PRECISION_FLOOR, summary
    assert report.recall >= _RECALL_FLOOR, summary


def test_no_new_missed_or_spurious_edges(tmp_path: Path) -> None:
    """Ratchet: failures must stay within the documented known-debt sets."""
    report = evaluate(tmp_path, GOLDEN_CASES)
    summary = report.summary()

    missed = set(summary["missed_edges"])
    spurious = set(summary["spurious_edges"])

    new_misses = missed - KNOWN_DEBT_MISSED
    new_spurious = spurious - KNOWN_DEBT_SPURIOUS

    assert not new_misses, f"New missed edges (resolver regression): {sorted(new_misses)}"
    assert not new_spurious, f"New spurious edges (resolver regression): {sorted(new_spurious)}"


def test_easy_cases_are_perfect(tmp_path: Path) -> None:
    """Non-hard cases must resolve exactly — no misses, no fabrications."""
    report = evaluate(tmp_path, GOLDEN_CASES)
    for case in report.cases:
        if case.hard:
            continue
        assert case.false_negatives == frozenset(), f"{case.name} missed {case.false_negatives}"
        assert case.false_positives == frozenset(), f"{case.name} spurious {case.false_positives}"

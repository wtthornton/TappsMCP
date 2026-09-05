# Successor story: test suite consolidation, perf-assert inventory, reduction plan

> Written by lane L12 (`tmcp-backlog-drain` wave 5) for the driver to file in Linear
> post-merge. This lane does not write Linear (lanes never write Linear — see
> `agent-scope.md` / `autonomy.md`). Title and body below are ready to paste into
> `docs_generate_story` verbatim.

## Title

Consolidate overlapping test coverage, inventory perf asserts, and plan a suite-runtime reduction

## What

Building on the count-only inventory landed in `docs/testing/suite-inventory-2026-09-05.md`
(TAP-6592/TAP-6609/TAP-5622, lane L12), this story does the three boxes TAP-6609
rescoped out of that lane:

1. Fill in the wall-time column of the existing inventory from a clean full-suite
   run (the drain program's SG-8 run, or a fresh equivalent), then identify
   overlapping/duplicate coverage clusters per directory with a per-cluster
   consolidation recommendation.
2. Inventory every wall-clock perf assertion in the unit suite (grep for
   `time.monotonic`, `time.perf_counter`, hardcoded `sleep`/timeout budgets in
   assertions, etc.) and flag each for either a marker-gated perf lane or a
   restructure to count-based/behavioral asserts. Fold in TAP-6592's own box 3
   finding: `test_save_many_collapses_50_entries_into_one_wire_round_trip` no
   longer exists in the tree as of PR #283 (verified by lane L12 via
   `grep -rn save_many_collapses_50 packages/tapps-mcp/tests/` returning nothing)
   — note that resolution here rather than re-deriving it.
3. Produce a reduction plan naming a target suite runtime and expected test
   count, and file one follow-up story per consolidation cluster identified
   in step 1.

## Where

- `docs/testing/suite-inventory-2026-09-05.md` — the count-only inventory this
  story extends with wall-time and cluster analysis.
- `pyproject.toml:234-243` — `testpaths`, `markers` (the `live_network` marker
  landed by TAP-6592 is a candidate marker-gate pattern for perf-flagged tests).
- `packages/tapps-mcp/tests/unit/test_linear_enforce_gate.py:1-60` — read-only
  reference named by the parent issue; no changes expected there in this story
  either, but worth a first look for a perf-assert example.
- `scripts/run-regression.sh:1-80` — read-only reference for how the program
  already invokes the suite.

## Why

An 11k+ test suite (13,092 measured on `ca31e2f1` per this lane's inventory) with
no per-directory runtime visibility and unknown overlap makes CI cost and local
iteration speed opaque. The count-only inventory this story builds on proves the
*shape* of the suite; this story turns that into an actionable reduction with a
committed target, so future work has a number to hold itself to instead of an
open-ended "the suite feels slow."

## Acceptance

- [ ] Wall-time column in `docs/testing/suite-inventory-2026-09-05.md` (or its
      successor) is filled in from a real full-suite run, not estimated
- [ ] Overlapping/duplicate coverage clusters are identified with a per-cluster
      consolidation recommendation
- [ ] All wall-clock perf assertions in the unit suite are inventoried and each
      is flagged for a marker-gated perf lane or a count-based restructure
- [ ] A reduction plan names a target suite runtime and expected test count
- [ ] One follow-up story is filed per consolidation cluster
- [ ] No test is deleted solely to shrink a runtime or count number — every
      removal is justified by demonstrated duplicate coverage

## Refs

TAP-6609, TAP-5841

# Test suite inventory — 2026-09-05

> TAP-6609 (rescoped, `tmcp-backlog-drain` wave 5, lane L12): a committed count-only
> inventory of the test suite, measured with `pytest --collect-only -q <dir>` on this
> lane's own branch (`tmcp-drain/l12-suite-hermeticity`, based on `origin/master`
> `ca31e2f1`). The runtime/wall-time column is **left blank here** — it is filled in
> from the drain program's single SG-8 full-suite run (the one full run this program
> allows; not run by this lane). Do not fill it from a guessed or partial number.
>
> Reproduce any row with: `uv run --project "$(git rev-parse --show-toplevel)" pytest --collect-only -q <dir> | tail -1`

## Per top-level test directory

| Directory | Test count | Command | Wall time |
|---|---|---|---|
| `packages/tapps-core/tests` | 1509 | `pytest --collect-only -q packages/tapps-core/tests` | TBD — filled from SG-8 full run |
| `packages/tapps-mcp/tests` | 8698 | `pytest --collect-only -q packages/tapps-mcp/tests` | TBD — filled from SG-8 full run |
| `packages/docs-mcp/tests` | 2885 | `pytest --collect-only -q packages/docs-mcp/tests` | TBD — filled from SG-8 full run |
| **Total** | **13092** | (sum of the three rows above) | TBD |

## Per subdivision (`unit` / `integration` / `contract`, where present)

| Directory | Test count | Command |
|---|---|---|
| `packages/tapps-core/tests/unit` | 1499 | `pytest --collect-only -q packages/tapps-core/tests/unit` |
| `packages/tapps-core/tests/integration` | 0 (directory has no collectible tests) | `pytest --collect-only -q packages/tapps-core/tests/integration` |
| `packages/tapps-core/tests/contract` | 10 | `pytest --collect-only -q packages/tapps-core/tests/contract` |
| `packages/tapps-mcp/tests/unit` | 8547 | `pytest --collect-only -q packages/tapps-mcp/tests/unit` |
| `packages/tapps-mcp/tests/integration` | 151 | `pytest --collect-only -q packages/tapps-mcp/tests/integration` |
| `packages/docs-mcp/tests/unit` | 2848 | `pytest --collect-only -q packages/docs-mcp/tests/unit` |
| `packages/docs-mcp/tests/integration` | 37 | `pytest --collect-only -q packages/docs-mcp/tests/integration` |

Subdivision rows do not sum exactly to their parent top-level row in every case
(pytest counts parametrized/collected items per directory scope; some files sit
directly under `tests/` rather than a `unit`/`integration`/`contract` child) —
each row is independently reproducible via its own command, which is the
acceptance criterion; the parent-directory row is the authoritative total for
that package.

## Notes

- Re-measured per the independent verifier's finding (this round, L12-fix-r1):
  `pytest --collect-only -q packages/tapps-core/tests packages/tapps-mcp/tests
  packages/docs-mcp/tests | tail -1` on `ca31e2f1` (this lane's own base) also
  collects `13092` — the same number as the per-directory sum above. The
  `13076` figure previously cited here as "measured on BASE_SHA" was not; it is
  the count at `7090b953`, a different commit. `ca31e2f1 → 13092`,
  head (as of this fix round) → `13093`, delta `+1` (this round's item 3 split
  one test into two while proving the same invariant; see PR #375). The prior
  sentence attributing the delta to "TAP-6592's fixes and this inventory's own
  file additions" was fabricated causal narrative and is removed.
- No test was deleted to produce this inventory.
- Overlap/redundancy clustering, wall-clock-assertion inventory, and a
  reduction plan with target runtime are **out of scope for this lane** — see
  `suite-inventory-successor.md` for the follow-up story this rescoping defers to.

# outputSchema A/B (negative finding) — tapps_quick_check (B2)

**Baseline:** `HEAD^=30149b1` (post-B1) — **HEAD:** `634ea57` (B2 candidate)

**Change:** Added `TappsQuickCheckResponse` envelope + `QuickCheckData` inner
model (`extra="allow"`), changed handler return annotation to the envelope.
Implementation [packages/tapps-mcp/src/tapps_mcp/server_scoring_tools.py](../../packages/tapps-mcp/src/tapps_mcp/server_scoring_tools.py).

## Result

| Metric | Baseline | HEAD | Delta | Decision |
|---|---:|---:|---:|---:|
| Strict accuracy | 87.5% | 87.5% | +0.0pt · | **REVERT** (<2pt rule) |
| Lenient accuracy | 91.7% | 91.7% | +0.0pt · | — |

## Per-scenario diff

- **Regression** (1): `dead_code_audit` exact → no_tool. Not a B2-targeted
  scenario — `tapps_dead_code` has no outputSchema declared in B2.
- **Improvement** (1): `memory_save_architectural_decision` no_tool → exact
  (`tapps_memory`). Also not a B2-targeted scenario.

Net offset: 0. The two flips are independent of the B2 change — they're
exactly the run-to-run LLM variance Phase A flagged at the ±4pt level
([docs/benchmarks/2026-05-20-description-eval.md](2026-05-20-description-eval.md)).

## Decision

Reverted per the Phase B per-tool rule (<2pt strict UP → revert). Revert
commit `6a84336`.

## Caveat carried into the rollup

The B2 outputSchema declaration was technically correct — `tools/list`
advertised the schema, all 108 impacted unit tests passed, the response
payload was byte-identical. The eval simply does not have the resolution
to detect a per-tool outputSchema effect at 1 scenario per tool with a
±4pt noise floor. This is information about the eval harness, not about
outputSchema.

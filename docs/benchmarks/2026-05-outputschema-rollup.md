# Phase B Rollup — outputSchema declarations on high-traffic tools

**Status:** **HALTED** after B3 due to Claude CLI Max-plan rate limiting
corrupting the A/B measurement. B4–B8 not run.

**Per-tool decision rule (from session brief):** strict accuracy moves
≥2pt UP → keep; otherwise → revert and document.

## Per-tool results

| # | Tool | Δ strict | Δ lenient | Decision | Commit |
|---|---|---:|---:|---|---|
| B1 | `tapps_session_start` | +4.2pt | +8.3pt | **KEEP** | `30149b1` |
| B2 | `tapps_quick_check` | +0.0pt | +0.0pt | revert | `634ea57` → revert `6a84336` |
| B3 | `tapps_validate_changed` | **invalid** | invalid | revert (infra) | `48839fd` → revert `467d10f` |
| B4–B8 | not run | — | — | — | — |

**Net delta from pre-Phase-B baseline (HEAD before B1 = `0b87812`):**
**+4.2pt strict** (B1 only). B2's +0.0pt and B3's invalid run produced
no surviving change.

## B1 — `tapps_session_start` (KEEP)

A/B: `0b87812` → `30149b1`. Strict 79.2% → 83.3%, lenient 83.3% → 91.7%.
Improvements: `lookup_docs_async_httpx` (no_tool → exact) and
`stats_session_review` (wrong → exact). **Neither is a B1-targeted
scenario** — B1 only declared outputSchema for `tapps_session_start`,
and the improvements are in other tools. The +4.2pt is at the Phase A
noise floor (±4pt at 24 scenarios). The mechanical rule still applies,
so B1 is kept; the rollup's honest framing is that the +4.2pt is
indistinguishable from LLM run-to-run variance.

## B2 — `tapps_quick_check` (REVERT)

A/B: `30149b1` → `634ea57`. Strict 87.5% → 87.5%, lenient 91.7% → 91.7%.
1 regression (`dead_code_audit` exact → no_tool) and 1 improvement
(`memory_save_architectural_decision` no_tool → exact) cancel; both
in non-B2-targeted scenarios. Per the <2pt rule → revert. Details at
[outputschema-tapps_quick_check.md](outputschema-tapps_quick_check.md).

## B3 — `tapps_validate_changed` (REVERTED — invalid A/B)

A/B: `30149b1` → `48839fd`. Reported strict 75.0% → 41.7% (-33.3pt).
**This is NOT a real description regression.** 14 of 24 HEAD-side
scenarios errored out in ~1–1.5 seconds each starting at scenario 11;
raw transcripts (`/tmp/eval-HEAD-raw/dead_code_audit.jsonl` and others)
contain `"type":"rate_limit_event"` and `"error":"rate_limit"` — the
Claude CLI Max-plan auth path returned rate-limit responses for the
remainder of the HEAD-side run.

The B3 implementation was reverted to keep `master` at the last
known-good state and to keep the eval infrastructure honest. The B3
code change itself was technically sound (mypy clean, 69 impacted unit
tests passed). It just couldn't be measured under the present harness
conditions.

## Why Phase B is halted here

The brief specifies: *"If any phase produces a NEGATIVE cumulative
eval delta, STOP and report back rather than continuing."* Cumulative
delta WITH B3 in place was -29pt strict; that's the stop signal. With
B3 reverted, cumulative is +4.2pt (B1 only), but two factors make
continuing through B4–B8 unwise:

1. **Rate limiting will continue.** The B1 + B2 + B3 runs consumed
   ~130+ `claude -p` invocations in ~1 hour. The Max-plan rate limit
   has clearly engaged; B4's A/B would produce the same pattern.
2. **Per-tool signal-to-noise is already known.** B1 (kept) and B2
   (reverted) both showed movement in non-targeted scenarios — i.e.
   the eval is variance-dominated at 1 scenario per tool. B4–B8 would
   each contribute one more noise sample.

## Recommendation

Land **Phase C first** (`--backend=api` in `scripts/eval-descriptions/run.py`
+ the `.github/workflows/eval-descriptions.yml` gate). The API backend
sidesteps the Max-plan rate limit (it bills per-request to
`ANTHROPIC_API_KEY`) and the CI gate is the actual durable measurement
infrastructure — Phase B was always going to be a one-shot per-tool
check, while Phase C compounds.

Once Phase C is in, re-run B1's A/B with `--backend=api` to confirm
the +4.2pt is real and not Phase-A-noise-floor variance. If real,
proceed through B4–B8 with the rate-limit-immune backend. If not,
revert B1 too and conclude that outputSchema does not move
first-call selection accuracy at this corpus size.

## What the unit tests still validate

The B1 unit test in
[test_output_schemas.py](../../packages/tapps-mcp/tests/unit/test_output_schemas.py)
(`TestTappsSessionStartResponse`) still asserts:

- FastMCP registers a non-empty `outputSchema` for the tool.
- The schema is permissive (`additionalProperties: true`) so the
  envelope's dynamic fields (`next_steps`, `warnings`, etc.) survive.
- Both success and error envelopes round-trip through the model with
  extras preserved.

These behaviours are deterministic and independent of the eval-harness
question of whether the agent reads the schema during tool selection.

## Process notes for future Phase-B-style work

1. **Rate-limit budget.** A single A/B is 48 `claude -p` calls.
   The Max-plan limit appears to engage around scenario 130–140 in a
   short window. Plan for ~2 A/Bs back-to-back before triggering the
   limit; space subsequent A/Bs by ≥1 hour, or use the API backend.
2. **24-scenario corpus is too small for per-tool measurement.**
   A single scenario flip = 4.17pt. The ≥2pt rule needs ~half a flip,
   which is operationally impossible. For per-tool A/B to work, either
   (a) add ≥3 scenarios per tool, or (b) measure cumulative across
   tool batches, not per-tool.
3. **Improvement attribution requires causal links.** B1's +4.2pt
   came from non-B1-targeted scenarios. Future rollups should require
   that at least one of the moved scenarios target the changed tool
   before attributing causation; otherwise log as "ambiguous variance".

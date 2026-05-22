# Phase B Rollup — outputSchema declarations on high-traffic tools

**Status:** **CLOSED** — B1 shipped as a low-risk schema declaration, B4–B8
deferred indefinitely. Phase B's per-tool A/B premise turns out to be
structurally unmeasurable in CI on the API backend (the only backend that
is rate-limit-immune); see the **API-blindness finding** below.

**Per-tool decision rule (from session brief):** strict accuracy moves
≥2pt UP → keep; otherwise → revert and document.

## Per-tool results

| # | Tool | Δ strict (CLI) | Δ strict (API re-verify) | Decision | Commit |
|---|---|---:|---:|---|---|
| B1 | `tapps_session_start` | +4.2pt | +0.0pt¹ | **KEEP** | `30149b1` |
| B2 | `tapps_quick_check` | +0.0pt | — | revert | `634ea57` → revert `6a84336` |
| B3 | `tapps_validate_changed` | **rate-limit corrupted** | — | revert (infra) | `48839fd` → revert `467d10f` |
| B4–B8 | NOT MEASURABLE² | — | — | deferred | — |

¹ API re-verify (`workflow_dispatch` run `26262008771`, 0b87812 → 30149b1
on `--backend=api`) reported +0.0pt strict — but the API backend cannot
measure outputSchema effects (see below). This neither confirms nor
refutes the CLI +4.2pt result.

² See "Why B4–B8 are deferred" below.

**Net delta from pre-Phase-B baseline (HEAD before B1 = `0b87812`):**
**+4.2pt strict on CLI / unmeasurable on API** (B1 only). The number
is honestly ambiguous; the schema declaration ships anyway because the
risk is near-zero (byte-identical response payload, all 4734 unit
tests pass) and the schema has independent value for downstream
tool-catalog consumers.

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

## API-blindness finding (added at Phase B close)

The CI gate landed in Phase C uses `--backend=api`, which converts MCP
tools to Anthropic Messages API tool format via
[`anthropic.lib.tools.mcp.mcp_tool`](https://github.com/anthropics/anthropic-sdk-python).
That wrapper takes `tool.name`, `tool.description`, and
`tool.inputSchema` — it does **not** carry `tool.outputSchema` through
to the API. The Messages API's `tools=` parameter has no outputSchema
field, so the agent never sees the declared schema during selection.

Empirical confirmation:

- **CLI A/B** (Claude Code, 2026-05-20): 0b87812 → 30149b1 = **+4.2pt
  strict**. Two scenarios flipped — both in non-B1-targeted tools.
  Most likely variance at the Phase A ±4pt noise floor; could be a
  real outputSchema effect on the catalog-level prompt; impossible
  to distinguish at n=24.
- **API A/B** (workflow_dispatch run `26262008771`, 2026-05-21):
  0b87812 → 30149b1 = **+0.0pt strict**. Identical baseline and
  HEAD on the API. **The API backend cannot see the only change B1
  made**, so this result is uninformative about B1's effect, not a
  refutation.

The beta Messages API `mcp_servers=` parameter would preserve
outputSchema by connecting directly to an MCP server, but it accepts
**URLs only** (HTTP/SSE transport); tapps-mcp is stdio-only. Adding
HTTP transport is a separate ~8–12h epic.

## Why B4–B8 are deferred

The mechanical decision rule (≥2pt strict UP → keep) requires a
measurement. With the rate-limit-immune backend (API) blind to
outputSchema, and the CLI backend rate-limited after ~130 calls/hour
(which 5 more A/Bs would re-trigger), B4–B8 have no path to a
defensible keep-or-revert decision under the original brief.

Future paths to unblock:

1. **HTTP transport for tapps-mcp + `mcp_servers=`** (8–12h).
   Reopens per-tool A/B in CI; bonus: unlocks remote-server deployments.
2. **Expand the scenario corpus to ≥5 per tool** (~4h to author).
   Raises per-tool resolution above the ±4pt noise floor and may
   make CLI-mode A/Bs reliable enough to absorb the rate-limit cost.
3. **Accept B1 as a one-off speculative declaration.**
   Skip outputSchema for B4–B8. The CI gate continues protecting
   description quality (its actual durable purpose).

This rollup chooses path 3 by default. The infrastructure built in
Phase C (CI gate, `--backend=api`, `--backend=cli` fallback) is
re-usable for paths 1 and 2 without rework.

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

## Outcome

**Phase C landed and is live in CI** (`tool-description eval` workflow,
master, `ad9354f` + `24d4b2a` + `--backend=api` with Max-plan OAuth via
`ANTHROPIC_AUTH_TOKEN` from `secrets.CLAUDE_CODE_OAUTH_TOKEN`). The CI
gate fails any push that drops strict accuracy ≥2pt on the API backend,
which protects description quality (the actual measurable dimension).

**B1's schema declaration ships.** The schema declared in
[`output_schemas.py`](../../packages/tapps-mcp/src/tapps_mcp/common/output_schemas.py)
is visible in `tools/list` for clients that read it; the unit tests
in [`TestTappsSessionStartResponse`](../../packages/tapps-mcp/tests/unit/test_output_schemas.py)
keep the contract from drifting.

**B4–B8 are not undone with a regret commit — they simply aren't done.**
If you want them later, the implementation pattern from B1, B2, and B3
(now reverted but still in git history at `48839fd`) is the template:
permissive Pydantic envelope + cast at returns + unit test.

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

# Tool-Description Eval: tool-selection accuracy A/B

**Baseline:** `cc1d340^` (`b7f0ba4`) — **HEAD:** `HEAD` (`7e31f2c`)  

**Scenarios:** 24  
**Methodology:** Each scenario runs through `claude -p` (Claude CLI OAuth) with `--strict-mcp-config`, against the live tapps-mcp MCP catalog. We capture the first MCP `tool_use` event and score against the expected tool (exact) or any acceptable alternative.

## Headline (raw)

| Metric | Baseline | HEAD | Delta |
|---|---:|---:|---:|
| Strict accuracy (exact match) | 75.0% | 66.7% | -8.3pt ↓ |
| Lenient accuracy (exact + acceptable alternative) | 79.2% | 75.0% | -4.2pt ↓ |

## Headline (noise-adjusted)

_Excludes 4 baseline errors + 4 HEAD errors_ _(typically MCP cold-start timeouts, not description regressions). Scenarios that ran successfully on both sides: 16._

| Metric | Baseline | HEAD | Delta |
|---|---:|---:|---:|
| Pass rate on common-OK scenarios | 93.8% | 87.5% | -6.2pt ↓ |

## Per-category accuracy

| Category | n | Baseline strict | HEAD strict | Δ |
|---|---:|---:|---:|---:|
| analysis | 3 | 33.3% | 100.0% | +66.7pt ↑ |
| diagnostics | 2 | 100.0% | 100.0% | +0.0pt · |
| linear | 2 | 100.0% | 100.0% | +0.0pt · |
| memory | 3 | 0.0% | 33.3% | +33.3pt ↑ |
| pipeline | 2 | 100.0% | 50.0% | -50.0pt ↓ |
| planning | 1 | 0.0% | 0.0% | +0.0pt · |
| release | 1 | 100.0% | 0.0% | -100.0pt ↓ |
| research | 3 | 100.0% | 33.3% | -66.7pt ↓ |
| security | 2 | 100.0% | 100.0% | +0.0pt · |
| validate | 5 | 100.0% | 80.0% | -20.0pt ↓ |

## True regressions (1) — signal

_Baseline picked correctly, HEAD picked wrong (excluding scenarios that errored on either side)._

| Scenario | Expected | Baseline picked | HEAD picked |
|---|---|---|---|
| `release_update_announce` | `mcp__tapps-mcp__tapps_release_update` | `mcp__tapps-mcp__tapps_release_update` (exact) | `—` (no_tool) |

## Error-introduced (4) — likely infra noise

_Baseline ran successfully; HEAD timed out. Likely MCP cold-start flake; rerun before treating as a real regression._

| Scenario | Expected | Baseline (ran OK) |
|---|---|---|
| `lookup_docs_fastapi_middleware` | `mcp__tapps-mcp__tapps_lookup_docs` | `mcp__tapps-mcp__tapps_lookup_docs` (exact) |
| `lookup_docs_pydantic_validators` | `mcp__tapps-mcp__tapps_lookup_docs` | `mcp__tapps-mcp__tapps_lookup_docs` (exact) |
| `post_edit_multi_file` | `mcp__tapps-mcp__tapps_validate_changed` | `mcp__tapps-mcp__tapps_validate_changed` (exact) |
| `session_bootstrap_first_call` | `mcp__tapps-mcp__tapps_session_start` | `mcp__tapps-mcp__tapps_session_start` (exact) |

## True improvements (0) — signal

_Baseline picked wrong, HEAD picked correctly (excluding scenarios that errored on either side)._

_None._

## Error-recovered (4) — likely infra noise

_Baseline timed out; HEAD ran. Likely the same MCP cold-start flake that hit the OTHER baseline scenarios._

| Scenario | Expected | HEAD (ran OK) |
|---|---|---|
| `circular_import_triage` | `mcp__tapps-mcp__tapps_dependency_graph` | `mcp__tapps-mcp__tapps_dependency_graph` (exact) |
| `dead_code_audit` | `mcp__tapps-mcp__tapps_dead_code` | `mcp__tapps-mcp__tapps_dead_code` (exact) |
| `memory_recall_task_start` | `mcp__tapps-mcp__tapps_memory` | `mcp__tapps-brain__memory_search` (acceptable) |
| `session_notes_scratch` | `mcp__tapps-mcp__tapps_session_notes` | `mcp__tapps-mcp__tapps_session_notes` (exact) |

## Stable failures (1)

_Scenarios that failed under BOTH baseline and HEAD — the description rewrite did not fix these. These are the highest-leverage targets for the next pass._

| Scenario | Expected | HEAD picked |
|---|---|---|
| `decompose_vague_task` | `mcp__tapps-mcp__tapps_decompose` | `—` (no_tool) |

## Reproduce

```bash
python3 scripts/eval-descriptions/compare.py cc1d340^ HEAD
```

Raw stream-json transcripts per scenario are at `/tmp/eval-<ref>-raw/<scenario_id>.jsonl` and can be re-scored offline.

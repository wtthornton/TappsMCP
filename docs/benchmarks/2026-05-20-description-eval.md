# Tool-Description Eval: tool-selection accuracy A/B

**Baseline:** `cc1d340^` (`b7f0ba4`) — **HEAD:** `HEAD` (`4c11f2f`)  

**Scenarios:** 24  
**Methodology:** Each scenario runs through `claude -p` (Claude CLI OAuth) with `--strict-mcp-config`, against the live tapps-mcp MCP catalog. We capture the first MCP `tool_use` event and score against the expected tool (exact) or any acceptable alternative.

## Headline (raw)

| Metric | Baseline | HEAD | Delta |
|---|---:|---:|---:|
| Strict accuracy (exact match) | 87.5% | 83.3% | -4.2pt ↓ |
| Lenient accuracy (exact + acceptable alternative) | 91.7% | 91.7% | +0.0pt · |

## Headline (noise-adjusted)

_Excludes 1 baseline errors + 0 HEAD errors_ _(typically MCP cold-start timeouts, not description regressions). Scenarios that ran successfully on both sides: 23._

| Metric | Baseline | HEAD | Delta |
|---|---:|---:|---:|
| Pass rate on common-OK scenarios | 95.7% | 91.3% | -4.3pt ↓ |

## Per-category accuracy

| Category | n | Baseline strict | HEAD strict | Δ |
|---|---:|---:|---:|---:|
| analysis | 3 | 100.0% | 66.7% | -33.3pt ↓ |
| diagnostics | 2 | 100.0% | 100.0% | +0.0pt · |
| linear | 2 | 100.0% | 100.0% | +0.0pt · |
| memory | 3 | 33.3% | 33.3% | +0.0pt · |
| pipeline | 2 | 100.0% | 100.0% | +0.0pt · |
| planning | 1 | 0.0% | 100.0% | +100.0pt ↑ |
| release | 1 | 100.0% | 100.0% | +0.0pt · |
| research | 3 | 100.0% | 66.7% | -33.3pt ↓ |
| security | 2 | 100.0% | 100.0% | +0.0pt · |
| validate | 5 | 100.0% | 100.0% | +0.0pt · |

## True regressions (2) — signal

_Baseline picked correctly, HEAD picked wrong (excluding scenarios that errored on either side)._

| Scenario | Expected | Baseline picked | HEAD picked |
|---|---|---|---|
| `circular_import_triage` | `mcp__tapps-mcp__tapps_dependency_graph` | `mcp__tapps-mcp__tapps_dependency_graph` (exact) | `—` (no_tool) |
| `lookup_docs_async_httpx` | `mcp__tapps-mcp__tapps_lookup_docs` | `mcp__tapps-mcp__tapps_lookup_docs` (exact) | `—` (no_tool) |

## True improvements (1) — signal

_Baseline picked wrong, HEAD picked correctly (excluding scenarios that errored on either side)._

| Scenario | Expected | Baseline picked | HEAD picked |
|---|---|---|---|
| `memory_recall_task_start` | `mcp__tapps-mcp__tapps_memory` | `—` (no_tool) | `mcp__tapps-brain__memory_search` (acceptable) |

## Error-recovered (1) — likely infra noise

_Baseline timed out; HEAD ran. Likely the same MCP cold-start flake that hit the OTHER baseline scenarios._

| Scenario | Expected | HEAD (ran OK) |
|---|---|---|
| `decompose_vague_task` | `mcp__tapps-mcp__tapps_decompose` | `mcp__tapps-mcp__tapps_decompose` (exact) |

## Reproduce

```bash
python3 scripts/eval-descriptions/compare.py cc1d340^ HEAD
```

Raw stream-json transcripts per scenario are at `/tmp/eval-<ref>-raw/<scenario_id>.jsonl` and can be re-scored offline.

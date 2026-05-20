# Tool-Description Eval: tool-selection accuracy A/B (Phase A — clean noise floor)

**Baseline:** `cc1d340^` (`b7f0ba4`) — **HEAD:** `HEAD` (`4c11f2f`)  

**Scenarios:** 24  
**Methodology:** Each scenario runs through `claude -p` (Claude CLI OAuth) with `--strict-mcp-config`, against the live tapps-mcp MCP catalog. We capture the first MCP `tool_use` event and score against the expected tool (exact) or any acceptable alternative.

**Phase A harness changes (this run):** `_SCENARIO_TIMEOUT_SECONDS` raised from 120 → 240 to absorb 30–50s MCP cold-start; one throwaway `claude -p "ping"` pre-warms the MCP catalog before the timed loop, pulling uv-venv + `.pyc` + OS-cache costs out of the first real scenario. **Result: 0 errors / 0 timeouts per side**, down from 4 per side in the [2026-05-19 baseline](2026-05-19-description-eval.md). The noise-adjusted bucket from the prior report is now empty — every scenario produced a real verdict.

## Headline (raw)

| Metric | Baseline | HEAD | Delta |
|---|---:|---:|---:|
| Strict accuracy (exact match) | 91.7% | 87.5% | -4.2pt ↓ |
| Lenient accuracy (exact + acceptable alternative) | 91.7% | 91.7% | +0.0pt · |

## Per-category accuracy

| Category | n | Baseline strict | HEAD strict | Δ |
|---|---:|---:|---:|---:|
| analysis | 3 | 100.0% | 100.0% | +0.0pt · |
| diagnostics | 2 | 100.0% | 100.0% | +0.0pt · |
| linear | 2 | 100.0% | 100.0% | +0.0pt · |
| memory | 3 | 66.7% | 33.3% | -33.3pt ↓ |
| pipeline | 2 | 100.0% | 100.0% | +0.0pt · |
| planning | 1 | 0.0% | 0.0% | +0.0pt · |
| release | 1 | 100.0% | 100.0% | +0.0pt · |
| research | 3 | 100.0% | 100.0% | +0.0pt · |
| security | 2 | 100.0% | 100.0% | +0.0pt · |
| validate | 5 | 100.0% | 100.0% | +0.0pt · |

## True regressions (1) — signal

_Baseline picked correctly, HEAD picked wrong (excluding scenarios that errored on either side)._

| Scenario | Expected | Baseline picked | HEAD picked |
|---|---|---|---|
| `session_notes_scratch` | `mcp__tapps-mcp__tapps_session_notes` | `mcp__tapps-mcp__tapps_session_notes` (exact) | `mcp__tapps-brain__brain_remember` (wrong) |

## True improvements (1) — signal

_Baseline picked wrong, HEAD picked correctly (excluding scenarios that errored on either side)._

| Scenario | Expected | Baseline picked | HEAD picked |
|---|---|---|---|
| `memory_recall_task_start` | `mcp__tapps-mcp__tapps_memory` | `—` (no_tool) | `mcp__tapps-brain__memory_search` (acceptable) |

## Stable failures (1)

_Scenarios that failed under BOTH baseline and HEAD — the description rewrite did not fix these. These are the highest-leverage targets for the next pass._

| Scenario | Expected | HEAD picked |
|---|---|---|
| `decompose_vague_task` | `mcp__tapps-mcp__tapps_decompose` | `—` (no_tool) |

## Residual LLM-level variance

The clean harness still surfaces some run-to-run flake at the agent layer (not infra). `decompose_vague_task` was `exact` in the earlier post-fix run but `no_tool` here; `session_notes_scratch` was `exact` previously, `wrong` here. Strict-accuracy ±4pt is currently within the agent's selection noise, so per-tool A/B comparisons in Phase B should use ≥2pt deltas as the kept-vs-reverted threshold, not 1pt. The eval is now infra-clean; remaining variance is something only a larger scenario corpus or repeated runs would smooth out.

## Reproduce

```bash
python3 scripts/eval-descriptions/compare.py cc1d340^ HEAD
```

Raw stream-json transcripts per scenario are at `/tmp/eval-<ref>-raw/<scenario_id>.jsonl` and can be re-scored offline.

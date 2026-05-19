# Tool-description eval harness

Measures whether changes to tapps-mcp tool descriptions actually move
tool-selection accuracy. Built per the recommendation in the
[2026-05-19 description rewrite work](../../docs/benchmarks/), distilled
from Anthropic's [Writing tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
("Evaluate description changes the same way you'd evaluate prompts").

## What it measures

For each scenario in `scenarios.yaml`, the harness:

1. Spawns a fresh `claude -p` agent in headless mode (OAuth via Claude
   Code; no `ANTHROPIC_API_KEY` plumbing — Max plan covers cost).
2. Connects the agent to the live tapps-mcp MCP catalog via
   `--strict-mcp-config --mcp-config <path>`.
3. Forbids Edit/Write/Bash/WebFetch/WebSearch via `--disallowed-tools`
   so the agent can only express its decision by calling an MCP tool.
4. Parses the streaming JSON output for the first `tool_use` event
   whose tool name starts with `mcp__`.
5. Scores against the scenario's `expected_tool` (exact match) or any
   tool in `acceptable_alternatives` (lenient match).

## Files

| File | Purpose |
|---|---|
| `scenarios.yaml` | The eval corpus. Each scenario is a user-intent prompt + expected tool. |
| `run.py` | Runs scenarios against ONE ref (or HEAD by default). Writes per-scenario JSON. |
| `compare.py` | A/B between two git refs via `git worktree`. Wraps `run.py` twice + emits diff. |
| `report.py` | Renders the comparison JSON as Markdown. Importable from `compare.py`. |

## Usage

```bash
# A/B compare a description change
python3 scripts/eval-descriptions/compare.py cc1d340^ HEAD

# Smoke test (3 scenarios, HEAD only)
python3 scripts/eval-descriptions/run.py \
    --only lookup_docs_async_httpx,post_edit_single_file,checklist_before_done \
    --output /tmp/eval-smoke.json --ref-label smoke

# Re-render report from existing JSON
python3 scripts/eval-descriptions/compare.py cc1d340^ HEAD --skip-run
```

## Adding a scenario

In `scenarios.yaml`:

```yaml
- id: snake_case_slug
  category: validate | research | security | analysis | memory | linear | pipeline | release | diagnostics | planning
  prompt: |
    User-intent in plain language. NEVER name the tool — describe the
    situation that should make the agent pick it.
  expected_tool: mcp__tapps-mcp__tapps_xxx
  acceptable_alternatives:
    - mcp__tapps-mcp__tapps_yyy
  rationale: |
    Quote the trigger clause from the tool's description that should
    fire on this prompt. Helps debug when the agent picks wrong.
```

Avoid leaking the answer into the prompt. The prompt should describe a
user's situation; the agent's job is to map situation → tool via the
description.

## Cost

On a Max-plan OAuth session, the harness is effectively free — runs
through the same authentication and quota as a normal Claude Code
session. Each scenario takes ~15–25 seconds (mostly MCP server cold
start + one agent step). A full 26-scenario A/B is ~20 minutes wall-clock.

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
# A/B compare a description change (CLI backend, Max-plan OAuth)
python3 scripts/eval-descriptions/compare.py cc1d340^ HEAD

# A/B compare using the Anthropic API directly (rate-limit-immune, CI backend)
ANTHROPIC_API_KEY=sk-ant-... python3 scripts/eval-descriptions/compare.py cc1d340^ HEAD --backend=api

# Smoke test (3 scenarios, HEAD only)
python3 scripts/eval-descriptions/run.py \
    --only lookup_docs_async_httpx,post_edit_single_file,checklist_before_done \
    --output /tmp/eval-smoke.json --ref-label smoke

# Re-render report from existing JSON
python3 scripts/eval-descriptions/compare.py cc1d340^ HEAD --skip-run
```

## Backends

| Backend | Auth | Rate limit | Best for |
|---|---|---|---|
| `--backend=cli` (default) | Claude CLI OAuth (Max plan) | ~130 calls/hour | Local-dev runs |
| `--backend=api` | `ANTHROPIC_API_KEY` env var | Per-API-key quota | CI, large A/B campaigns, rate-limit recovery |

`--backend=api` lazy-imports the `anthropic` Python SDK (a dev dep — run
`uv sync --all-packages` to install). It spawns the tapps-mcp stdio
server once per ref, lists its tool catalog, and calls
`messages.create()` per scenario with the catalog passed as `tools=`.
Tool names are prefixed with `mcp__tapps-mcp__` so scenarios.yaml
`expected_tool` values match without modification. The Anthropic
Messages API tool format does NOT include `outputSchema`, so this
backend measures description quality only — not outputSchema effects.

Default model for the API backend is `claude-sonnet-4-6`; override
with `--model`.

### Auth for `--backend=api`

The anthropic SDK accepts either credential — set whichever matches your
subscription:

| Env var | What it is | Cost | Get it from |
|---|---|---|---|
| `ANTHROPIC_AUTH_TOKEN` | Max-plan OAuth bearer | included in Max | `~/.claude/.credentials.json` on a logged-in machine |
| `ANTHROPIC_API_KEY` | Paid API key | ~$1 per A/B at Sonnet 4.6 | console.anthropic.com |

Prefer `ANTHROPIC_AUTH_TOKEN` if you already pay for Max — same
authentication path Claude Code itself uses, no double-billing. The
SDK reads either env var transparently; the eval harness only checks
that at least one is set.

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

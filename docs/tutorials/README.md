# Tutorials

Three short, copy-paste runnable walkthroughs for the most-asked starter tasks. Each ends with explicit verification steps so you know it worked.

| # | Tutorial | Time | What you'll do |
|---|---|---|---|
| 01 | [Add a new MCP tool to tapps-mcp](01-add-an-mcp-tool.md) | ~15 min | Wire a new `@mcp.tool()` end-to-end: handler, `_record_call`, checklist registration, AGENTS.md row, unit test. |
| 02 | [Run the quality pipeline against a fresh Python project](02-quality-pipeline-walkthrough.md) | ~10 min | Bootstrap with `tapps_init`, write a deliberately bad function, watch `tapps_quick_check` flag it, fix it, batch-validate, finish with the checklist. |
| 03 | [Wire tapps-brain into a Claude Code session](03-wire-tapps-brain.md) | ~20 min | Stand up the brain Docker service, set `TAPPS_BRAIN_AUTH_TOKEN`, save a memory in one session, recall it in the next. |

## Diataxis: why tutorials, not how-tos

These follow the [Diataxis](https://diataxis.fr/) tutorial conventions: **learning-oriented**, runnable end-to-end, verified at each step. They're meant for someone whose mental model of the tool is empty — not for someone who already knows what they want and needs a recipe.

For task-specific reference (the "I know what I want, just remind me how") see [docs/INDEX.md](../INDEX.md). For architectural decisions, see [docs/adr/](../adr/).

## Suggested order

1. **02** first if you've never used the tool — it's the shortest path to seeing the pipeline work.
2. **01** next if you're going to extend tapps-mcp itself (vs. just consume it).
3. **03** when you want cross-session memory. Optional — tapps-mcp works without it.

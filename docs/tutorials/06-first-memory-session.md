# Tutorial: Your first memory save and recall

**Time:** ~10 min (after [tutorial 03](03-wire-tapps-brain.md) brain wiring). **Outcome:** Save a project decision, recall it in a new chat, and know when to use CLI vs `nlt-memory` MCP.

Since v3.12.0 the standalone `tapps_memory` MCP tool was removed ([migration table](../migrations/tapps-memory-deprecation.md)). Memory still works through **BrainBridge** — either the `tapps-mcp memory` CLI or the **`nlt-memory`** MCP profile (`tapps-mcp memory search`, `tapps-mcp memory save`, handoff tools).

## Prerequisites

- tapps-brain running and `TAPPS_BRAIN_AUTH_TOKEN` set (complete [tutorial 03](03-wire-tapps-brain.md) Steps 1–4).
- TappsMCP installed: `uv tool install -e packages/tapps-mcp` from this repo, or global CLI in a consumer project.

## Step 1 — Save via CLI

From the project root:

```bash
uv run tapps-mcp memory save \
  --key tutorial-first-memory \
  --tier pattern \
  --value "Always pass explicit file_paths to tapps_validate_changed in repos with 50+ Python files."
```

**Verify:** command exits 0 and prints a JSON block with `"success": true`.

## Step 2 — Recall via CLI

```bash
uv run tapps-mcp memory search --query "validate_changed file_paths"
```

**Verify:** results include `tutorial-first-memory` with a non-zero relevance score.

## Step 3 — Save from an agent session (`nlt-memory`)

Enable **`nlt-build` + `nlt-memory`** in your MCP config (default developer bundle). Ask the agent:

```
Use tapps-mcp memory save (or the nlt-memory MCP equivalent) with key="nlt-memory-test", tier="context", value="Memory MCP profile works."
```

With `nlt-memory` enabled, the agent calls memory tools exposed on that server — not a removed `tapps_memory` tool.

**Verify:** Step 2 search also finds `nlt-memory-test` after the agent save.

## Step 4 — Cross-session handoff (optional)

For chat-to-chat continuity without hunting keys:

1. Run `/tapps-handoff-session` before ending a chat (writes `.tapps-mcp/session-handoff.md`).
2. Start a new chat and run `/tapps-continue-session`.

See [MEMORY_REFERENCE.md](../MEMORY_REFERENCE.md) for tiers, scopes, and the full 42-action surface.

## Verification summary

- [x] CLI `memory save` persists to tapps-brain.
- [x] CLI `memory search` retrieves the entry.
- [x] Agent path works with `nlt-memory` enabled (not legacy `tapps_memory` MCP).
- [x] Handoff skills available for structured session transfer.

## What you learned

| Surface | When to use |
|---------|-------------|
| `uv run tapps-mcp memory …` | Scripts, CI, agents without `nlt-memory` loaded |
| `nlt-memory` MCP server | Daily coding sessions needing recall/save/handoff tools |
| `/tapps-handoff-session` | End-of-chat structured handoff to the next session |

Do **not** add tapps-brain as a direct MCP server — bridge-only per [CONSUMER-REPO-BRAIN-WIRING.md](../operations/CONSUMER-REPO-BRAIN-WIRING.md).

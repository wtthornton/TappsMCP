# Tutorial: NLT MCP session modes

**Time:** ~10 minutes. **Outcome:** You enable the right 1–3 MCP servers for your task, verify tools appear in Cursor, and run a minimal quality pipeline without loading all six NLT servers.

## Prerequisites

- Global CLIs installed: `uv tool install --from packages/tapps-mcp tapps-mcp`
- Cursor with `.cursor/mcp.json` from `tapps-mcp init --host cursor` (or dev-repo `.cursor/bin/*-serve.sh` scripts)

## Step 1 — Understand the bundles

Read [ADR-0016](../adr/0016-needs-based-nlt-mcp-taxonomy.md). Default **developer** bundle:

| Server | Profile | Purpose |
|--------|---------|---------|
| `nlt-build` | Build | Score, gate, validate, docs lookup |
| `nlt-memory` | Memory | Search/save, session handoff |
| `nlt-linear-issues` | Linear | Backlog reads (cache-first) |

Enable **only when needed:**

- `nlt-project-docs` — doc generation / drift audit (this refresh workflow)
- `nlt-setup` — init, upgrade, doctor (short sessions)
- `nlt-release-ship` — release notes / ship gate

## Step 2 — Enable Build + Docs for a documentation pass

In `.cursor/mcp.json`, enable `nlt-build` and `nlt-project-docs`. Reload the window (`Developer: Reload Window`).

Verify in chat:

1. Call `tapps_session_start()` — should succeed from `nlt-build`
2. Call `docs_session_start()` — should succeed from `nlt-project-docs`

## Step 3 — Run a docs health check

```
docs_check_completeness()
docs_check_cross_refs(doc_dirs="docs", exclude="docs/archive")
docs_check_links(broken_only=true, summary_only=true)
```

Note scores in your session notes. Fix broken links before regenerating INDEX.

## Step 4 — Token-tight coding session

Disable all servers except `nlt-build`. Confirm `tapps_memory` is **not** in the tool list (memory lives on `nlt-memory` only).

Run after a Python edit:

```
tapps_quick_check(file_path="packages/tapps-mcp/src/tapps_mcp/server.py")
```

## Verification

- [ ] Developer bundle: ~18 eager tools, not 40+
- [ ] Build-only: no `tapps_init` / `docs_*` tools visible
- [ ] Docs pass: `docs_project_scan` returns project inventory
- [ ] Legacy IDs `nlt-code-quality` / `nlt-platform-admin` still work one release (aliases)

## Next steps

- [Documentation refresh workflow](05-docs-refresh-workflow.md)
- [Quality pipeline walkthrough](02-quality-pipeline-walkthrough.md)
- [Consumer upgrade guide](../UPGRADE_FOR_CONSUMERS.md)

# Tutorial: NLT MCP session modes

**Time:** ~10 minutes. **Outcome:** You understand the ADR-0018 **full** default, opt down to a token-tight bundle with one CLI command, and verify Cursor catalogs **listed** tools (not Claude eager counts).

## Prerequisites

- Global CLIs installed: `uv tool install --from packages/tapps-mcp tapps-mcp`
- Cursor with `.cursor/mcp.json` from `tapps-mcp init --host cursor` (or dev-repo `.cursor/bin/*-serve.sh` scripts)

## Step 1 — Understand the default and the opt-downs

Read [ADR-0018](../adr/0018-deploy-all-six-nlt-mcp-servers-by-default.md). **Install default is `full`** (all six `nlt-*` servers). Opt down for token-tight sessions:

| Bundle | Servers | Approx listed (Cursor) | Approx eager (Claude Tool Search) |
|--------|---------|------------------------|-----------------------------------|
| `full` (default) | all six | ~82 | ~24 |
| `developer` | build + memory + linear | ~39 | ~18 |
| `minimal` | build only | ~19 | ~9 |
| `docs` | build + project-docs | ~48 | ~9 |

Prompts/resources are **not** duplicated across servers: `_tapps_*` / `tapps://` live on `nlt-build`; `docs://` / `docs_workflow*` live on `nlt-project-docs`.

## Step 2 — Opt down with one command

```bash
tapps-mcp mcp-bundle set developer
# writes mcp_bundle to .tapps-mcp.yaml and rewrites host MCP configs
```

Reload MCP (`Developer: Reload Window` in Cursor). Verify:

```bash
tapps-mcp mcp-bundle show
tapps-mcp doctor --quick   # NLT row shows eager (Claude) vs listed (Cursor)
```

## Step 3 — Enable Build + Docs for a documentation pass

```bash
tapps-mcp mcp-bundle set docs
```

Reload, then in chat:

1. Call `tapps_session_start()` — from `nlt-build`
2. Call `docs_session_start()` — from `nlt-project-docs`

## Step 4 — Token-tight coding session

```bash
tapps-mcp mcp-bundle set minimal
```

Confirm `tapps_memory` is **not** in the tool list (memory lives on `nlt-memory` only).

Run after a Python edit:

```
tapps_quick_check(file_path="packages/tapps-mcp/src/tapps_mcp/server.py")
```

## Verification

- [ ] `mcp-bundle show` matches the bundle you set
- [ ] Developer: ~39 **listed** tools in Cursor (eager ~18 is Claude-only math)
- [ ] Build-only: no `tapps_init` / `docs_*` tools visible
- [ ] Docs pass: `docs_project_scan` returns project inventory
- [ ] Doctor with `mcp_bundle=full` **PASS**es NLT partial enablement
- [ ] Legacy IDs `nlt-code-quality` / `nlt-platform-admin` still work one release (aliases)

## Next steps

- [Documentation refresh workflow](05-docs-refresh-workflow.md)
- [Quality pipeline walkthrough](02-quality-pipeline-walkthrough.md)
- [Consumer upgrade guide](../UPGRADE_FOR_CONSUMERS.md)

# Brain-central doc RAG — fleet cutover runbook

Maintenance window (~30 minutes) for ADR-0014 big-bang cutover.

## Prerequisites

- tapps-brain **3.24.0+** with `docs_lookup` / `docs_warm` deployed (ADR-0015)
- `CONTEXT7_API_KEY` set on **brain** service (`docker/.env` or host env)
- `TAPPS_MCP_DOCS_VIA_BRAIN=1` on consumer machines (set via `docs_via_brain: true`
  in `.tapps-mcp.yaml` or fleet `upgrade-fleet --strip-context7-env`)

## Timeline (~30 minutes)

| Phase | Duration | Action |
|-------|----------|--------|
| Deploy brain | ~10 min | `make dev-deploy`; verify `docs_lookup` in tools/list |
| Import caches | ~5 min | `tapps-brain docs import-dir` or fleet `--import-legacy-doc-cache` |
| Upgrade consumers | ~5 min | `tapps-mcp upgrade --force`; reload MCP host |
| Verify | ~5 min | `tapps-mcp doctor`; `lookup-docs` smoke test |
| Rollback buffer | ~5 min | Keep previous brain image + `TAPPS_MCP_DOCS_VIA_BRAIN=0` handy |

## Steps

### 1. Deploy brain (~10 min)

```bash
# From tapps-brain repo — set CONTEXT7_API_KEY in docker/.env first
make dev-deploy   # or MIGRATE=1 make dev-deploy when SQL changed
make brain-smoke-live
```

Verify `docs_lookup` appears in tools/list with `X-Brain-Profile: full`.

### 2. Import legacy caches (~5 min per repo or fleet batch)

Per repo:

```bash
cd /path/to/consumer-repo
tapps-brain docs import-dir .tapps-mcp-cache
```

Fleet:

```bash
cd /path/to/tapps-mcp
tapps-mcp upgrade-fleet --import-legacy-doc-cache --strip-context7-env --force
```

### 3. Upgrade consumers (~5 min)

```bash
tapps-mcp upgrade --force --host auto
# Reload MCP host (Cursor / Claude Code)
```

Remove `TAPPS_MCP_CONTEXT7_API_KEY` from shell profile and MCP env blocks.

### 4. Verify (~5 min)

```bash
tapps-mcp doctor
tapps-mcp lookup-docs --library pytest --topic fixtures
```

Doctor should pass `legacy_doc_cache` (no doc subtrees under `.tapps-mcp-cache/`).

Optionally remove imported doc directories from `.tapps-mcp-cache/` after confirming brain hits.

### 5. Rollback (if needed)

Set `TAPPS_MCP_DOCS_VIA_BRAIN=0`, restore consumer `TAPPS_MCP_CONTEXT7_API_KEY`, run `tapps-mcp init --force`.

## Success criteria

- Two repos on the same `library+topic` share one brain cache entry
- `tapps_lookup_docs` works with no local `.tapps-mcp-cache/{library}/` trees
- Doctor green on `legacy_doc_cache`

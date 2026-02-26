# MCP Client Timeouts and Long-Running Tools

TappsMCP exposes several tools that can take 10–35+ seconds to complete. Some MCP clients (e.g. Cursor, Claude Code) enforce default timeouts that may cause "This operation was aborted" or similar errors. This document describes how to avoid timeouts and configure clients for long-running tools.

---

## Tools That Can Be Slow

| Tool | Typical duration | What drives it |
|------|------------------|----------------|
| **tapps_init** (full) | 10–35+ seconds | Project profiling, cache warming (Context7 API), expert RAG warming |
| **tapps_init** (dry_run) | ~2–5 seconds | Project profiling; skips cache/RAG and server verification |
| **tapps_init** (verify_only) | ~1–3 seconds | Server/checker detection only |
| **tapps_session_start** | ~1 second | Server info only (version, checkers, config); call tapps_project_profile for project context |
| **tapps_score_file** (full) | 3–15 seconds | Ruff, mypy, bandit, radon + AST analysis |
| **tapps_quick_check** | ~2–8 seconds | Quick score + gate + basic security |
| **tapps_validate_changed** | 5–60+ seconds | Depends on number of changed files |
| **tapps_lookup_docs** | 1–10 seconds | Context7 API or cache |
| **tapps_consult_expert** | 2–10 seconds | RAG lookup + retrieval |

---

## Recommended MCP Client Timeouts

To avoid aborts on long-running tools, configure your MCP client with adequate timeouts:

| Client | Configuration | Suggested timeout |
|--------|---------------|-------------------|
| **Cursor** | `cursor.mcp.timeout` or MCP server settings | 60–120 seconds |
| **Claude Code** | `.claude.json` MCP config | 60+ seconds (if configurable) |
| **VS Code Copilot** | MCP extension settings | 60+ seconds |

When possible, set timeouts to **at least 60 seconds** for TappsMCP so full `tapps_init` and `tapps_validate_changed` runs can complete.

---

## Lighter tapps_init Flows

If your client cannot increase timeouts, use lighter init flows:

1. **dry_run** — Preview what would be created without writing files or warming caches (~2–5s):

   ```json
   { "dry_run": true }
   ```

2. **verify_only** — Run only server verification (~1–3s):

   ```json
   { "verify_only": true }
   ```

3. **Templates only (no cache warming)** — Create files without warming Context7 cache or expert RAG:

   ```json
   {
     "warm_cache_from_tech_stack": false,
     "warm_expert_rag_from_tech_stack": false
   }
   ```

   This typically runs in ~5–15 seconds. Cache and RAG will warm on first use of `tapps_lookup_docs` or `tapps_consult_expert`.

4. **Staged init** — First call with `dry_run: true` to confirm, then a second call with `warm_cache_from_tech_stack: false` and `warm_expert_rag_from_tech_stack: false` to create files without the heaviest phases.

---

## Error Interpretation

| Error | Likely cause |
|-------|--------------|
| "This operation was aborted" | MCP client timeout (tool took longer than client’s limit) |
| "Connection closed" / "Request timeout" | MCP client or transport timeout |
| TappsMCP returns `success: false` with `errors` | Server-side error (path denied, profile failed, etc.) |

When you see "This operation was aborted", the failure is typically on the **client side** (timeout). Try a lighter flow (e.g. `dry_run` or `verify_only`) or increase the client’s MCP timeout.

---

## See Also

- [INIT_AND_UPGRADE_FEATURE_LIST.md](INIT_AND_UPGRADE_FEATURE_LIST.md) — Full tapps_init feature list
- [AGENTS.md](../AGENTS.md) — tapps_session_start vs tapps_init and workflow guidance

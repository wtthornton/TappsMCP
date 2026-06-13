# 14. Brain-central doc RAG (big-bang cutover)

Date: 2026-06-13

## Status

Proposed

## Context

Library docs live in per-repo `.tapps-mcp-cache/` (`tapps_lookup_docs`); project
memory lives in tapps-brain. Expert filesystem RAG was removed (EPIC-94).
tapps-brain is moving to a **company-wide, always-on** service — not a
single-machine optional sidecar. Agents need one knowledge plane; operators
need one shared doc index, not N repo caches.

## Decision

**One coordinated release** (brain + tapps-core + tapps-mcp). No multi-quarter
phased dual-write. Cut over in a single maintenance window.

### End state (day 1 after cutover)

| Concern | Owner | Agent surface |
|---------|-------|---------------|
| Library docs (Context7 + LlmsTxt fallback) | **tapps-brain** | `tapps_lookup_docs` (unchanged name; implementation delegates to brain) |
| Project memory | **tapps-brain** | `tapps-mcp memory` CLI + hooks (unchanged until a later unified MCP tool) |
| Session handoff | **tapps-brain** | `session-handoff` key per `project_id`; markdown file optional export only |
| Per-repo `.tapps-mcp-cache/` doc entries | **Deleted** | Migration script imports existing entries into brain, then removes doc subtrees |

Context7 API key moves to **brain service env** only. Consumer MCP configs drop
`TAPPS_MCP_CONTEXT7_API_KEY`.

### tapps-brain (prerequisite — ships first)

Add minimal surface; reuse Postgres + existing search/embeddings.

1. **`library-docs` memory group** (namespace `universal`, long TTL, tag
   `source:context7|llmstxt`).
2. **MCP tools** (profile `full` + read-only alias on `reviewer`):
   - `docs_lookup(library, topic, mode)` — cache hit in PG; on miss call
     Context7, store snippet + `context7_id`, return (deterministic body).
   - `docs_warm(libraries[])` — batch pre-fetch (replaces session-start disk warm).
3. **Config on brain**: `CONTEXT7_API_KEY`, `DOCS_CACHE_TTL`, optional LlmsTxt
   fallback flag.
4. **One-shot migrator**: `brain docs import-dir <path>` — ingest
   `{library}/{topic}.md` + sidecars from legacy `.tapps-mcp-cache/`.

No expert personas, no FAISS per project, no new agent-facing tool names on brain.

### tapps-core + tapps-mcp (same release tag)

1. **`LookupEngine.lookup()`** → HTTP `docs_lookup` on BrainBridge (delete local
   `KBCache` write path for docs; keep read-only import helper for migrator only).
2. **`tapps_lookup_docs`** — same MCP contract; `cache_hit` / `source` fields
   reflect brain response.
3. **Session start** — drop disk cache warm; call `docs_warm` on brain when
   `search_first.covered` present.
4. **Memory doc validation (Epic 62)** — validate against brain `docs_lookup`
   (no local cache).
5. **Doctor** — fail if `.tapps-mcp-cache/` contains doc entries post-cutover;
   warn if `TAPPS_MCP_CONTEXT7_API_KEY` still set on consumer MCP env.
6. **Version floor** — bump to brain release that ships `docs_lookup` (new ADR
   supersedes [0013](0013-pin-tapps-brain-version-floor-at-3240.md) when tagged).

### Consumer cutover (maintenance window, ~30 min)

```bash
# 1. Deploy new brain (with CONTEXT7_API_KEY)
# 2. Per repo:
brain docs import-dir .tapps-mcp-cache   # or fleet script
tapps-mcp upgrade --force --host auto
# 3. Reload MCP; remove TAPPS_MCP_CONTEXT7_API_KEY from mcp.json env
# 4. tapps-mcp doctor  # must pass brain docs probe
```

Fleet: extend `tapps-mcp upgrade-fleet` with `--import-legacy-doc-cache` +
`--strip-context7-env`.

### Explicitly out of scope (this bang)

- Unified `tapps_knowledge` MCP tool (later)
- Repo/code chunk RAG in brain (later epic)
- Reviving EPIC-94 expert consultation
- Offline/no-brain mode for library lookup (brain required; degraded = LlmsTxt
  only inside brain when Context7 down)

## Consequences

**Positive:** One shared doc index for the company; one ops surface; agents keep
`tapps_lookup_docs`; no per-repo cache drift; Context7 key centralized.

**Negative:** Hard dependency on brain for doc lookup; cutover requires coordinated
deploy; brief window where old tapps-mcp + new brain (or reverse) is unsupported.

**Neutral:** `tapps-mcp memory` CLI unchanged; ADR-0001 HTTP bridge becomes the
only supported transport for consumers (in-process doc path removed with cache).

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| Keep disk cache, brain for memory only | Does not scale company-wide; two planes remain |
| Gradual dual-write for quarters | Ops burden, cache drift, ambiguous `source` |
| Restore expert filesystem RAG | Non-deterministic, duplicates Context7, EPIC-94 scope |
| Context7 only in tapps-mcp forever | Wrong for fleet brain; key sprawl per laptop |

## Success criteria

- [ ] Two repos on same library+topic share one brain hit (no local doc files)
- [ ] `tapps_lookup_docs` p95 cache-hit latency ≤ prior disk cache (brain PG)
- [ ] Fleet doctor green: no doc subtrees under `.tapps-mcp-cache/`
- [ ] `tapps_session_start` `search_first` + warm via brain only

## LOE estimate

| Component | Effort |
|-----------|--------|
| tapps-brain `docs_lookup` + storage + migrator | ~1.5–2 wks |
| tapps-core bridge + LookupEngine redirect | ~3–4 days |
| tapps-mcp doctor, init, fleet, docs | ~2–3 days |
| Cutover + fleet import | ~1 day |

**Total: ~3 weeks** one squad, one release train.

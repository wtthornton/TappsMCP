# 30. Unified research entry point with brain-backed external-data cache

Date: 2026-07-17

## Status

Accepted (2026-07-17; TAP-4419 story 1)

## Context

Agents research in two modes today:

1. **Library / API docs** — `tapps_lookup_docs` (Context7-backed, `(library, topic)` key, long TTL).
2. **Open-ended / web** — Exa, Firecrawl, Tavily, etc., invoked ad hoc from skills or outside the MCP surface.

The `tapps-research` skill can only call `lookup_docs`, so web research is uncached, unrouted, and duplicated across the fleet. Putting web caching inside `lookup_docs` is wrong: its fuzzy `(library, topic)` key and slow-doc TTL misfire on volatile free-text queries. Building a tapps-mcp-owned proxy/cache would violate the brain-as-cache rule and [ADR-0014](0014-brain-central-doc-rag-big-bang.md).

## Decision

1. **`tapps_research` is the unified research front door** in tapps-mcp (thin server tool, not a skill-owned cache). It routes:
   - docs / library / API questions → existing `lookup_docs` path
   - open-ended / web / "latest" questions → brain `web_research` / `research_fetch` via BrainBridge
2. **tapps-brain owns both cache layers** for external web data:
   - raw-result cache (normalized query + source)
   - answer-level (pattern-tier) recall with freshness tiers (volatile vs evergreen)
3. **Credentials stay brain-side.** tapps-mcp holds no Exa / Firecrawl / Tavily API keys.
4. **`tapps_lookup_docs` stays doc-only.** No web search through Context7 or the docs cache.
5. **Safety:** RAG safety + SSRF / `url_guard` apply on the brain web path before cache write-through.
6. **Telemetry:** research calls record `source=docs|web|cache-hit|memory-hit` (same spirit as lookup telemetry).

## Consequences

### Positive

- One agent-facing entry point; skills stop inventing parallel research paths.
- Fleet-shared cache keys live in brain; spend and latency drop on repeated queries.
- Freshness tiers prevent serving stale volatile answers.
- Least privilege: narrow MCP processes never see search-provider secrets.

### Negative / follow-ons

- Cross-repo work: brain must ship `web_research` / `research_fetch` before the mcp router is useful (TAP-4419 stories 2–5).
- Routing heuristics (docs vs web) need tests and may need iteration.
- Brain-down degraded mode must return a clear structured error (no silent empty).

## Alternatives considered

| Option | Why rejected |
|--------|----------------|
| Cache web inside `lookup_docs` | Wrong key/TTL model; conflates docs with volatile web |
| tapps-mcp-owned Exa/Firecrawl proxy | Duplicates brain cache; puts secrets in every consumer |
| Skill-only orchestration without a server tool | Cache keys and telemetry would not be fleet-stable |

## Refs

- TAP-4419
- [ADR-0014](0014-brain-central-doc-rag-big-bang.md) (`docs_via_brain`)
- Brain-as-cache rule (external-data calls → tapps-brain)
- M4.1 `auto_save_quality` pattern-tier memory

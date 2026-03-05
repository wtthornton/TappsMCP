# Epic 54: Non-Python RAG & Custom Documentation Sources

**Priority:** P2 | **LOE:** ~1 week | **Source:** Consumer feedback v2 (ENH-5, ENH-8)

## Problem Statement

Two related issues limit TappsMCP's usefulness for non-Python projects:

1. **Expert RAG biased toward Python** (ENH-5): The expert knowledge base heavily favors Python patterns. `TECH_STACK_TO_EXPERT_DOMAINS` in `rag_warming.py` has minimal Node.js/TypeScript mappings (only `express` and `jest`). RAG results for non-Python queries return generic Docker/microservices content.

2. **No custom documentation sources** (ENH-8): When Context7 doesn't cover a library (PostgreSQL, Redis, Tailscale, InfluxDB), there's no way for users to register alternative doc sources. The only providers are Context7 and LlmsTxt.

## Stories

### Story 54.1: Expand tech stack domain mappings

**Files:** `experts/rag_warming.py`

1. Add comprehensive Node.js/TypeScript mappings to `TECH_STACK_TO_EXPERT_DOMAINS`:
   ```python
   # Node.js / TypeScript
   "nodejs": ["software-architecture", "api-design-integration"],
   "node": ["software-architecture", "api-design-integration"],
   "typescript": ["code-quality-analysis", "software-architecture"],
   "javascript": ["software-architecture"],
   "nestjs": ["api-design-integration", "software-architecture"],
   "nextjs": ["user-experience", "api-design-integration"],
   "deno": ["software-architecture"],
   "bun": ["software-architecture", "performance-optimization"],
   "prisma": ["database-data-management"],
   "drizzle": ["database-data-management"],
   "typeorm": ["database-data-management"],
   "zod": ["code-quality-analysis"],
   "vitest": ["testing-strategies"],
   "playwright": ["testing-strategies"],
   "cypress": ["testing-strategies"],
   ```
2. Add infrastructure/IoT mappings:
   ```python
   "mqtt": ["api-design-integration", "cloud-infrastructure"],
   "influxdb": ["database-data-management", "observability-monitoring"],
   "grafana": ["observability-monitoring"],
   "prometheus": ["observability-monitoring"],
   "tailscale": ["security", "cloud-infrastructure"],
   "wireguard": ["security", "cloud-infrastructure"],
   "terraform": ["cloud-infrastructure"],
   "pulumi": ["cloud-infrastructure"],
   ```
3. Ensure `tech_stack_to_expert_domains()` handles case-insensitive matching

**Acceptance criteria:**
- Node.js/TypeScript projects get relevant domain warming
- IoT/infrastructure stacks get appropriate domain coverage
- At least 20 new tech stack entries added

### Story 54.2: Add Node.js/TypeScript knowledge files

**Files:** `experts/knowledge/` (multiple domains)

1. Add knowledge files for JavaScript/TypeScript patterns:
   - `code-quality-analysis/typescript-patterns.md` — strict mode, type guards, utility types
   - `testing-strategies/nodejs-testing.md` — vitest, jest, playwright patterns
   - `api-design-integration/nodejs-api-patterns.md` — Express, Fastify, NestJS patterns
   - `software-architecture/nodejs-architecture.md` — module patterns, monorepo, event-driven
   - `security/nodejs-security.md` — npm audit, prototype pollution, dependency risks
2. Add knowledge files for infrastructure:
   - `database-data-management/timeseries-databases.md` — InfluxDB, TimescaleDB patterns
   - `cloud-infrastructure/vpn-mesh-networking.md` — Tailscale, WireGuard, zero-trust
   - `observability-monitoring/iot-observability.md` — MQTT, telemetry, edge monitoring

**Acceptance criteria:**
- At least 8 new knowledge files
- Each file has actionable guidance (not just overviews)
- RAG queries for Node.js/IoT topics return relevant chunks

### Story 54.3: Custom documentation sources in config

**Files:** `config/settings.py`, `knowledge/lookup.py`, `knowledge/providers/`

1. Add `doc_sources` field to `TappsMCPSettings`:
   ```python
   doc_sources: dict[str, DocSourceConfig] = Field(default_factory=dict)
   ```
   Where `DocSourceConfig` supports:
   ```python
   class DocSourceConfig(BaseModel):
       url: str | None = None      # Remote URL (fetched + cached)
       file: str | None = None     # Local file path (relative to project root)
       format: str = "markdown"    # "markdown" | "text"
   ```
2. In `LookupEngine.lookup()`, check `doc_sources` BEFORE the provider chain:
   - If a matching library has a local `file` source, read and return it
   - If it has a `url` source, fetch, cache in KBCache, and return
3. Cache custom URL sources same as Context7/LlmsTxt results
4. Support in `.tapps-mcp.yaml`:
   ```yaml
   doc_sources:
     redis:
       url: "https://redis.io/docs/latest/develop/"
     pgvector:
       file: "docs/pgvector-reference.md"
     internal-sdk:
       file: "docs/sdk-api.md"
   ```

**Acceptance criteria:**
- Local file doc sources work without network access
- URL doc sources are fetched and cached
- Custom sources take priority over Context7/LlmsTxt
- Invalid paths/URLs produce clear error messages

### Story 54.4: RAG retrieval weighted by project tech stack

**Files:** `experts/engine.py`, `experts/rag.py`

1. When project profile is available, boost RAG relevance scores for chunks matching the project's tech stack
2. Implement a `tech_stack_boost` multiplier (default 1.2x) applied to chunks whose domain matches `TECH_STACK_TO_EXPERT_DOMAINS` for the current project
3. Add `tech_stack_boost` to settings for configurability
4. Ensure Python-heavy chunks don't dominate results for Node.js/infra projects

**Acceptance criteria:**
- RAG results for a Node.js project prioritize JS/TS-relevant chunks
- Boost is configurable and defaults to 1.2x
- No regression for Python-only projects

## Dependencies

- Story 54.4 depends on 54.1 (domain mappings) and 54.2 (knowledge files)
- Story 54.3 is independent

## Testing

- Unit tests for new domain mappings (tech stack → domain resolution)
- Unit tests for custom doc source loading (file and URL)
- Unit tests for RAG tech stack boost scoring
- Integration test: lookup with custom file source
- Integration test: expert query for Node.js project returns relevant results

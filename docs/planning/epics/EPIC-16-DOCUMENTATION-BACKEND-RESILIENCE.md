# Epic 16: Documentation Backend Resilience (Multi-Provider)

**Status:** Partial — LookupEngine wired to provider chain (Context7 + LlmsTxt); Deepcon and Docfork providers not yet implemented
**Priority:** P0 — Critical (Context7 free tier slashed 92% in Jan 2026; single-provider dependency)
**Estimated LOE:** ~2-3 weeks (1 developer)
**Dependencies:** Epic 2 (Knowledge & Docs)
**Blocks:** None

---

## Goal

Eliminate the single-provider dependency on Context7 by implementing a multi-backend documentation lookup architecture. Add Deepcon (90% accuracy, half the tokens) and Docfork (open-source, 9,000+ libraries) as alternative backends with automatic fallback. Support llms.txt as a lightweight zero-dependency fallback layer.

## Why This Epic Exists

In January 2026, Context7 slashed its free tier by 92%:
- **Before:** ~6,000 requests/month free
- **After:** 1,000 requests/month, 60 requests/hour rate limit
- **Paid:** $7-10/month per seat

TappsMCP's `tapps_lookup_docs` and `tapps_research` tools rely entirely on Context7. This creates:

1. **Rate limit failures** — free tier users hit 60/hour limit during active sessions
2. **Single point of failure** — Context7 outage = no documentation lookup
3. **Cost barrier** — paid tier required for serious use
4. **Accuracy ceiling** — Context7 benchmarked at 65% accuracy; Deepcon achieves 90%
5. **Token waste** — Context7 averages 5,626 tokens/response; Deepcon averages 2,365

The MCP ecosystem now has several mature alternatives. A multi-backend architecture with automatic fallback provides resilience, better accuracy, and lower token usage.

## LLM Error Sources Addressed

| Error Source | How This Epic Helps |
|---|---|
| Outdated/missing docs | Multiple backends increase coverage breadth |
| Rate limit failures | Auto-fallback to next provider when rate-limited |
| Service outages | Three backends = high availability |
| Inaccurate docs | Deepcon's 90% accuracy reduces hallucination risk |
| Token waste | Deepcon uses ~58% fewer tokens than Context7 |
| Cost barrier | Docfork (open-source) and llms.txt (free) as zero-cost options |

## Acceptance Criteria

- [x] Backend abstraction: `DocumentationProvider` protocol with `resolve()` and `fetch()` methods (via `providers/` package)
- [x] Context7 backend: refactored as `Context7Provider` implementing the protocol
- [ ] Deepcon backend: new provider using Deepcon's API
- [ ] Docfork backend: new provider using Docfork's API
- [x] llms.txt backend: `LlmsTxtProvider` fetches `/llms.txt` or `/llms-full.txt` from library websites
- [x] Configurable provider order with automatic fallback on failure (Context7 then LlmsTxt)
- [ ] Circuit breaker per provider (existing pattern from `knowledge/circuit_breaker.py`)
- [ ] Metrics per provider: success rate, latency, token count
- [ ] `tapps_lookup_docs` transparently uses the best available provider
- [ ] All changes covered by unit tests
- [ ] Zero mypy/ruff errors

---

## Stories

### 16.1 — Documentation Provider Protocol

**Points:** 3
**Priority:** Critical
**Status:** Complete

Define the `DocumentationProvider` protocol that all backends implement. Refactor the existing Context7 code to be one implementation of this protocol.

**Source Files:**
- `src/tapps_mcp/knowledge/providers.py` (NEW)
- `src/tapps_mcp/knowledge/models.py`

**Tasks:**
- [x] Define `DocumentationProvider` protocol: `async def resolve(library: str) -> ResolvedLibrary | None`, `async def fetch(library_id: str, topic: str) -> str | None`, `def name() -> str`, `def is_available() -> bool`
- [ ] Define `ResolvedLibrary` model: `library_id`, `display_name`, `version`, `provider_name`
- [ ] Define `ProviderResult` model: `content`, `provider_name`, `latency_ms`, `token_estimate`, `from_cache`
- [ ] Define `ProviderConfig` model: `provider_name`, `enabled`, `priority`, `api_key`, `base_url`, `timeout`
- [ ] Add `documentation_providers: list[ProviderConfig]` to settings with sensible defaults

**Implementation Notes:**
- Use `typing.Protocol` for the provider interface — no abstract base class needed
- `ResolvedLibrary` extends the existing `CacheEntry` concept but is provider-agnostic
- Default provider order: `["deepcon", "context7", "docfork", "llms_txt"]`
- Each provider has an independent circuit breaker instance

**Definition of Done:** Provider protocol defined. Configuration model supports multiple providers with priority ordering.

---

### 16.2 — Refactor Context7 as Provider

**Points:** 3
**Priority:** Critical
**Status:** Complete

Wrap the existing `Context7Client` and `LookupEngine` into a `Context7Provider` that implements `DocumentationProvider`.

**Source Files:**
- `src/tapps_mcp/knowledge/providers/context7.py` (NEW — extracted from lookup.py)
- `src/tapps_mcp/knowledge/lookup.py`

**Tasks:**
- [x] Create `providers/` subpackage under `knowledge/`
- [x] Extract Context7-specific logic from `LookupEngine` into `Context7Provider`
- [x] `Context7Provider.resolve()` wraps `Context7Client.resolve_library()`
- [x] `Context7Provider.fetch()` wraps `Context7Client.get_library_docs()`
- [x] `Context7Provider.is_available()` checks API key + circuit breaker state
- [x] Preserve existing cache integration (cache is shared across providers)
- [x] `LookupEngine` becomes a thin orchestrator over providers + cache

**Implementation Notes:**
- This is a refactor, not a rewrite — all existing Context7 behavior preserved
- Cache layer sits above providers: check cache first, then try providers in order
- Circuit breaker per provider, not shared
- Existing tests should continue to pass with minimal changes

**Definition of Done:** Context7 works identically to before, but through the provider protocol. All existing knowledge tests pass.

---

### 16.3 — Deepcon Provider

**Points:** 5
**Priority:** Critical
**Status:** Planned

Implement the Deepcon documentation provider. Deepcon benchmarks at 90% accuracy with 2,365 average tokens (vs Context7's 65% accuracy and 5,626 tokens).

**Source Files:**
- `src/tapps_mcp/knowledge/providers/deepcon.py` (NEW)

**Tasks:**
- [ ] Research Deepcon's API: endpoint URLs, authentication, request/response format
- [ ] Implement `DeepconProvider` with `resolve()` and `fetch()` methods
- [ ] Handle authentication: API key via `TAPPS_MCP_DEEPCON_API_KEY` env var
- [ ] Handle rate limits: detect 429 responses, trigger circuit breaker
- [ ] Parse response into provider-agnostic `ProviderResult`
- [ ] Add timeout handling (default 30s)
- [ ] Add to provider registry with priority 1 (highest)

**Implementation Notes:**
- Use `httpx.AsyncClient` for HTTP calls (already a dependency)
- RAG safety check on returned content (reuse existing `rag_safety.py`)
- If Deepcon requires an MCP client connection instead of HTTP API, use `mcp.ClientSession` to connect
- Graceful degradation: if no API key configured, provider reports `is_available() = False`

**Definition of Done:** Deepcon provider resolves and fetches library documentation. Falls through to next provider on failure.

---

### 16.4 — Docfork Provider + llms.txt Fallback

**Points:** 5
**Priority:** Important
**Status:** Partial (llms.txt complete, Docfork planned)

Implement Docfork (open-source, 9,000+ libraries) and llms.txt (zero-dependency fallback) providers.

**Source Files:**
- `src/tapps_mcp/knowledge/providers/docfork.py` (NEW)
- `src/tapps_mcp/knowledge/providers/llms_txt.py` (NEW)

**Tasks:**
- [ ] Research Docfork's API: endpoint URLs, authentication (if any), request/response format
- [ ] Implement `DocforkProvider` with `resolve()` and `fetch()` methods
- [ ] Handle Docfork being open-source: support both hosted API and self-hosted URL
- [x] Implement `LlmsTxtProvider`: fetches `https://{library_domain}/llms.txt` or `/llms-full.txt`
- [x] `LlmsTxtProvider.resolve()`: map library name to known domain (e.g., "fastapi" -> "fastapi.tiangolo.com")
- [x] Maintain a mapping of popular library names to their llms.txt URLs
- [ ] Parse llms.txt Markdown format: extract relevant sections based on topic
- [ ] RAG safety check on all fetched content

**Implementation Notes:**
- Docfork uses a single API call (vs Context7's two-step resolve + fetch)
- llms.txt is the last-resort fallback — no API key, no rate limits, just HTTP GET
- llms.txt URL mapping can start small (top 50 Python libraries) and grow
- The llms.txt spec defines a structured Markdown format: `# Title`, `## Section`, `- [Link](url): description`
- For unknown libraries, try `https://docs.{library}.dev/llms.txt` and `https://{library}.readthedocs.io/llms.txt`

**Definition of Done:** Both providers work independently. llms.txt provides zero-dependency fallback for popular libraries.

---

### 16.5 — Multi-Provider Orchestration

**Points:** 5
**Priority:** Critical
**Status:** Partial (Context7 + LlmsTxt wired)

Wire the provider chain into `LookupEngine` with automatic fallback, circuit breaking, and metrics.

**Source Files:**
- `src/tapps_mcp/knowledge/lookup.py`
- `src/tapps_mcp/knowledge/providers/__init__.py` (NEW)

**Tasks:**
- [x] Refactor `LookupEngine` to iterate providers in priority order
- [x] Cache check first (shared across all providers)
- [x] On cache miss: try providers in order until one succeeds (Context7 then LlmsTxt)
- [ ] Circuit breaker per provider: open after 3 consecutive failures, half-open after 60s
- [ ] Rate limit detection: 429 status triggers immediate fallback (don't wait for timeout)
- [ ] Metrics per provider: track success_count, failure_count, avg_latency, total_tokens
- [ ] Log which provider served each request (for debugging and optimization)
- [ ] Store provider_name in cache entries (know which provider populated the cache)
- [ ] Surface provider_name in `tapps_lookup_docs` response: "Source: Deepcon (latency: 340ms)"

**Implementation Notes:**
- Existing SWR (stale-while-revalidate) cache logic preserved — stale entry returned immediately while background refresh tries providers
- Provider chain is configurable via settings: users can reorder, disable, or add providers
- If all providers fail, return stale cache entry (existing behavior) or error with details
- Metrics feed into existing `metrics/rag_metrics.py`

**Definition of Done:** `tapps_lookup_docs` transparently uses the best available provider with automatic fallback. Provider metrics are tracked.

---

### 16.6 — Tests

**Points:** 3
**Priority:** Important
**Status:** Planned

Comprehensive tests for multi-provider architecture, fallback logic, and individual providers.

**Source Files:**
- `tests/unit/test_providers.py` (NEW)
- `tests/unit/test_provider_orchestration.py` (NEW)

**Tasks:**
- [ ] Test provider protocol compliance for all four providers
- [ ] Test fallback: provider 1 fails, provider 2 succeeds
- [ ] Test circuit breaker: provider marked unhealthy after consecutive failures
- [ ] Test rate limit handling: 429 triggers immediate fallback
- [ ] Test cache interaction: cache hit skips all providers, cache miss tries in order
- [ ] Test SWR: stale entry returned immediately, background refresh uses provider chain
- [ ] Test configuration: provider reordering, disabling, custom URLs
- [ ] Test llms.txt parsing: extract relevant sections from Markdown
- [ ] Test metrics: per-provider success/failure/latency tracking
- [ ] Mock all HTTP calls (no real network in unit tests)

**Definition of Done:** ~45 new tests covering provider protocol, orchestration, fallback, and per-provider parsing. Zero mypy/ruff errors.

---

## Performance Targets

| Operation | SLA |
|---|---|
| Cache hit | < 5 ms |
| Deepcon lookup (cache miss) | < 2 s |
| Context7 lookup (cache miss) | < 3 s |
| Docfork lookup (cache miss) | < 2 s |
| llms.txt fetch | < 5 s |
| Provider fallback (one failure) | < 5 s total |
| Full chain failure to stale cache | < 1 s |

## Key Dependencies

- `httpx>=0.28.1` (already a dependency — used for all HTTP calls)
- Deepcon API (cloud service — requires API key for best accuracy)
- Docfork API (open-source — can be self-hosted)
- llms.txt standard (no dependency — just HTTP GET + Markdown parsing)
- Epic 2 (existing knowledge/cache infrastructure)

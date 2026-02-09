# Epic 2: Knowledge & Documentation Lookup

**Status:** Not Started
**Priority:** P1 — High Value (addresses #1 LLM error source: hallucinated APIs)
**Estimated LOE:** ~2 weeks (1 developer)
**Dependencies:** Epic 0 (Foundation & Security)
**Blocks:** None (can run in parallel with Epic 3 if staffing allows)

---

## Goal

Add `tapps_lookup_docs` and `tapps_validate_config` — the documentation lookup tool addresses **hallucinated APIs**, the single highest-impact LLM error source. LLMs confidently use methods that don't exist or have wrong signatures; `tapps_lookup_docs` gives them real, current documentation at the moment they're writing the call.

## LLM Error Sources Addressed

| Error Source | Tool |
|---|---|
| Hallucinated APIs | `tapps_lookup_docs` |
| Stale knowledge | `tapps_lookup_docs` |
| Unsafe config files | `tapps_validate_config` |

## 2026 Best Practices Applied

- **`httpx` with HTTP/2**: Use `httpx` (not `requests`) for Context7 API calls — async-native, HTTP/2 support, connection pooling.
- **Circuit breaker pattern**: Wrap Context7 API with circuit breaker for fail-fast when the API is down. Don't hang the MCP tool call waiting for a timeout.
- **Background cache refresh**: Stale cache entries trigger async background refresh — return stale data immediately, update in background. Never block the tool call on a cache miss refresh.
- **Cache-first architecture**: Local cache is the primary data source. API calls are for cache population and refresh only. Air-gapped environments work with bundled/cached docs.
- **Content Security Policy for RAG**: All retrieved documentation passes through `rag_safety.py` prompt injection detection before returning to the LLM. Retrieved docs are untrusted content.

## Acceptance Criteria

- [ ] `tapps_lookup_docs` resolves library names via fuzzy matching (e.g., "fastapi" → "tiangolo/fastapi")
- [ ] `tapps_lookup_docs` returns current documentation from Context7 API
- [ ] `tapps_lookup_docs` returns cached docs in < 500ms (cache hit)
- [ ] `tapps_lookup_docs` returns docs in < 5s (cache miss, API call)
- [ ] `tapps_lookup_docs` degrades gracefully without Context7 API key (uses bundled/cached docs)
- [ ] Cache warming on server startup detects project dependencies and pre-fetches docs
- [ ] Stale cache entries refresh in background without blocking tool response
- [ ] All retrieved content passes RAG safety prompt injection check
- [ ] API keys use `SecretStr` — never appear in logs or responses
- [ ] `tapps_validate_config` validates Dockerfile, docker-compose.yml against best practices
- [ ] `tapps_validate_config` auto-detects config type when `config_type: "auto"`
- [ ] Config validators support WebSocket, MQTT, InfluxDB patterns
- [ ] Unit tests ported: ~75 tests (cache ~55, validators ~30 — some overlap)
- [ ] Cross-platform: cache locking works on Windows (no `fcntl`)

---

## Stories

### 2.1 — Extract Context7 Client & Cache

**Points:** 8

Extract the full Context7 documentation lookup system from `context7/`.

**Tasks:**
- Extract core cache modules (decouple from framework config):
  - `kb_cache.py` → `tapps_mcp/knowledge/kb_cache.py` — KB cache with TTL
  - `cache_structure.py` → `cache_structure.py` — atomic writes (tempfile + os.replace)
  - `fuzzy_matcher.py` → `fuzzy_matcher.py` — library name fuzzy matching with language hints
  - `backup_client.py` → `context7_client.py` — Context7 API HTTP client (convert to httpx)
  - `circuit_breaker.py` → `circuit_breaker.py` — fail-fast wrapper
  - `lookup.py` → `lookup.py` — lookup orchestration
- Extract cache management modules (standalone):
  - `cache_warming.py`, `cache_prewarm.py` — pre-warm cache for detected deps
  - `cache_locking.py` — file-based locking (ensure Windows compat — use `filelock` package)
  - `cache_metadata.py` — cache metadata management
  - `staleness_policies.py` — per-library TTL rules
  - `refresh_queue.py` — async background cache refresh queue
  - `analytics.py` — cache hit/miss analytics
  - `cleanup.py` — cache cleanup policies
- Extract supporting modules:
  - `credential_validation.py` — API key format validation
  - `bundle_loader.py` — offline bundle loading for air-gapped environments
  - `cross_references.py` — cross-reference between docs
- Extract to project detection (shared with Epic 4):
  - `language_detector.py` → `tapps_mcp/project/language.py`
  - `library_detector.py` → `tapps_mcp/project/library_detector.py`
- Port ~55 unit tests (cache, fuzzy matching, circuit breaker)

**Definition of Done:** Context7 client fetches and caches docs. Cache hits < 500ms. Circuit breaker prevents hanging on API failures.

---

### 2.2 — Extract Config Validators

**Points:** 3

Extract configuration file validators from `agents/reviewer/`.

**Tasks:**
- Copy standalone validators:
  - `dockerfile_validator.py` → `tapps_mcp/validators/dockerfile.py`
  - `docker_compose_validator.py` → `tapps_mcp/validators/docker_compose.py`
  - `websocket_validator.py` → `tapps_mcp/validators/websocket.py`
  - `mqtt_validator.py` → `tapps_mcp/validators/mqtt.py`
  - `influxdb_validator.py` → `tapps_mcp/validators/influxdb.py`
  - `service_discovery.py` → `tapps_mcp/validators/service_discovery.py`
- Implement auto-detection of config type based on filename/content
- Port ~30 unit tests

**Definition of Done:** Validators detect issues in Dockerfiles, docker-compose, and protocol-specific configs. ~30 tests pass.

---

### 2.3 — Wire MCP Tools

**Points:** 3

Wire `tapps_lookup_docs` and `tapps_validate_config` into the MCP server.

**Tasks:**
- Implement `tapps_lookup_docs` MCP tool handler:
  - `library` parameter: library name (fuzzy matched)
  - `topic` parameter: specific topic within the library
  - Path through: fuzzy match → cache check → API call (if miss) → RAG safety filter → response
  - All retrieved content passes `rag_safety.py` before returning
  - All responses pass `governance.py` PII/secret filter
  - `elapsed_ms` and `cache_hit` in response
- Implement `tapps_validate_config` MCP tool handler:
  - `file_path` parameter: path to config file (validated against project root)
  - `config_type` parameter: auto-detect or explicit
  - Return findings with severity, line numbers, recommendations

**Definition of Done:** Both tools callable via MCP protocol. Docs returned with safety filtering. Config validation produces actionable findings.

---

### 2.4 — Cache Warming on Startup

**Points:** 2

Pre-fetch documentation for detected project dependencies on server startup.

**Tasks:**
- On server `initialize`, scan project for `requirements.txt`, `pyproject.toml`, `package.json`, etc.
- Detect dependencies using `library_detector.py`
- Queue cache warming for top N most-used libraries
- Warming runs in background — doesn't block server startup
- Log warming progress via structlog

**Definition of Done:** After startup, common project dependencies have cached docs. First `tapps_lookup_docs` call for a detected dependency is a cache hit.

---

### 2.5 — Unit Tests

**Points:** 2

Comprehensive unit tests for cache system and validators.

**Tasks:**
- Port cache tests (~30 tests): KB cache, fuzzy matching, staleness, atomic writes
- Port cache management tests (~25 tests): locking, warming, cleanup
- Port validator tests (~30 tests): Dockerfile, docker-compose, protocol validators
- Add tests for RAG safety filtering in lookup flow
- Mock Context7 API — don't require API key for unit tests
- Mock filesystem for cache locking tests

**Definition of Done:** ~75+ tests pass. Coverage ≥80%.

---

### 2.6 — Integration Tests

**Points:** 2

Integration tests with Context7 API (mocked or real with API key).

**Tasks:**
- Test: full lookup flow with mocked Context7 API
- Test: cache hit → cache miss → API call → cache write → cache hit flow
- Test: circuit breaker opens after N failures, returns cached/degraded response
- Test: air-gapped mode with bundled docs (no API key, no network)
- Test: cache warming detects deps from `pyproject.toml`

**Definition of Done:** Integration tests verify full lookup lifecycle including degraded modes.

---

## Performance Targets

| Tool | Target (p95) | Notes |
|---|---|---|
| `tapps_lookup_docs` (cache hit) | < 500ms | Local file I/O only |
| `tapps_lookup_docs` (cache miss) | < 5s | Context7 API call + cache write |
| `tapps_validate_config` | < 1s | Pattern matching, no external tools |

## Key Dependencies
- `httpx` — async HTTP client for Context7 API
- `filelock` — cross-platform file locking (replaces `fcntl` on Windows)
- `pyyaml` — YAML parsing for docker-compose validation

## Optional Dependencies
- Context7 API key — degrades to cached/bundled docs without it

# Story 75.3: Session Start Cache Directory Bootstrap

**Epic:** [EPIC-75-DOCKER-PIPELINE-RELIABILITY](../EPIC-75-DOCKER-PIPELINE-RELIABILITY.md)
**Priority:** P2 | **LOE:** 1–2 days | **Recurrence:** 3

## Problem

`tapps_session_start` reports `cache_dir: /workspace/.tapps-mcp-cache` with `exists: false, writable: false`. The cache directory is never auto-created, so:
- Every session is a cold start (no caching benefit)
- Latency varies between ~1s and ~4s unpredictably
- The `server_info_ms` component dominates (902–3217ms)

The cache directory should be created automatically on first session start so subsequent calls within the same container lifecycle benefit from cached state.

## Root Cause Analysis

1. `tapps_session_start` checks if the cache directory exists but does not create it.
2. Docker containers start with a clean filesystem each run (unless volumes are mounted for the cache path).
3. No fallback location is tried when the primary cache path is not writable.

## Tasks

- [ ] In `tapps_session_start`, after resolving `cache_dir`, call `cache_dir.mkdir(parents=True, exist_ok=True)` to auto-create it.
- [ ] If creation fails (permission error), fall back to `Path(tempfile.gettempdir()) / ".tapps-mcp-cache"` and log a warning.
- [ ] After creation, verify writability by writing a small sentinel file (`.cache-test`), then delete it.
- [ ] Report actual cache state in session start response: `cache_dir`, `exists`, `writable`, `fallback_used`.
- [ ] Add `TAPPS_CACHE_DIR` env var override so Docker compose configs can mount a persistent volume for the cache.
- [ ] Update Docker MCP templates to include a cache volume mount suggestion in comments.
- [ ] Unit tests: dir created on first call, fallback on permission error, env var override, sentinel writability check.

## Acceptance Criteria

- [ ] Cache directory exists and is writable after first `tapps_session_start` call.
- [ ] If primary path not writable, fallback to temp dir succeeds with warning.
- [ ] `TAPPS_CACHE_DIR` env var overrides default cache location.
- [ ] Session start response accurately reports cache state including `fallback_used`.
- [ ] Subsequent session starts within same container lifecycle show `exists: true, writable: true`.
- [ ] Tests cover: happy path, permission failure + fallback, env var override.

## Files (likely)

- `packages/tapps-mcp/src/tapps_mcp/server.py` (session_start cache bootstrap)
- `packages/tapps-core/src/tapps_core/config/settings.py` (cache dir resolution)
- `packages/tapps-mcp/tests/unit/test_server.py`

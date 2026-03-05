# Epic 52: Session Startup Performance

**Priority:** P2 | **LOE:** ~3-4 days | **Source:** Consumer feedback v2 (BUG-4)

## Problem Statement

`tapps_server_info` takes ~50s on first call and ~10s on subsequent calls. `tapps_session_start` consistently takes ~10s. In timeout-sensitive MCP clients (Cursor with 30s default), this causes failures or degraded UX.

**Root cause analysis:**
- `tapps_server_info` calls `detect_installed_tools()` synchronously — runs 6 tools sequentially (ruff, mypy, bandit, radon, vulture, pip-audit) with up to 20s timeout each
- An async variant `detect_installed_tools_async()` exists and is used by `tapps_session_start`, but NOT by `tapps_server_info`
- No disk-based caching — tool versions are cached in process memory only, lost on server restart
- `collect_diagnostics()` adds additional overhead (Context7 API probe, knowledge base scan)

## Stories

### Story 52.1: Disk-based tool version cache

**Files:** `tools/tool_detection.py`

1. After detecting tool versions, persist results to `.tapps-mcp/tool-versions.json` with a timestamp
2. On startup, load cached versions if the cache file is < 24 hours old
3. Background-refresh: after returning cached results, schedule an async re-detection to update the cache
4. Include a `"cached": true` flag in the response so clients know the data may be stale
5. `tapps_doctor` should always force fresh detection (bypass cache)
6. Cache file format: `{"timestamp": "...", "tools": [...], "platform": "win32"}`

**Acceptance criteria:**
- Second server start returns tool info in < 500ms (from disk cache)
- Cache auto-expires after 24 hours
- `tapps_doctor` always gets fresh results

### Story 52.2: Async `tapps_server_info`

**Files:** `server.py`

1. Convert `tapps_server_info` to use `detect_installed_tools_async()` instead of `detect_installed_tools()`
2. Run tool detection and diagnostics collection in parallel via `asyncio.gather()`
3. Target: first-call time reduced from ~50s to ~15-20s (parallel detection)
4. With disk cache (Story 52.1): subsequent calls < 500ms

**Acceptance criteria:**
- `tapps_server_info` runs tool detection in parallel
- Total first-call time reduced by at least 50%

### Story 52.3: Lazy diagnostics in session_start

**Files:** `server_pipeline_tools.py`

1. Make Context7 API probe optional in `tapps_session_start` — skip if it adds > 2s
2. Cache diagnostics results alongside tool versions
3. Add `tapps_session_start(quick=true)` parameter that skips diagnostics entirely
4. Quick mode returns only: server version, project root, quality preset, installed checkers (from cache)
5. Target: quick session start < 1s

**Acceptance criteria:**
- `tapps_session_start(quick=true)` completes in < 1s with warm cache
- Full session start still available as default
- Diagnostics results cached to disk

## Dependencies

- Story 52.2 depends on Story 52.1 for full performance benefit
- Story 52.3 depends on Story 52.1 for disk caching

## Testing

- Unit test: tool version cache write/read/expiry
- Unit test: cache bypass in doctor mode
- Unit test: async parallel detection timing
- Integration test: session_start quick mode response shape

# Epic 41: Async Upgrade Conversion & Remaining ctx Adoption

**Status:** Open
**Priority:** P3 — Low (quality-of-life improvements; deferred candidates from Epic 39)
**Estimated LOE:** ~1 week (1 developer)
**Dependencies:** Epic 39 (MCP Context Progress Adoption — shared helper in Story 39.5)
**Blocks:** None

---

## Goal

Convert `tapps_upgrade` from a synchronous function to async, enabling ctx progress notifications, and add lightweight phase-based ctx.info to `tapps_dependency_graph`. These are the two remaining tools deferred from Epic 39's scope.

## Motivation

### `tapps_upgrade`

**Current blocker:** `tapps_upgrade` is the only `def` (synchronous) tool handler among all 28 TappsMCP tools. It cannot use `await ctx.info()` or `await ctx.report_progress()` because `def` functions cannot await.

**Why convert:** `tapps_upgrade` generates 4-10+ files (AGENTS.md, platform rules, hooks, skills, subagents), creates a backup, and optionally overwrites existing files. The 5-15s runtime is long enough that users benefit from per-file "Updated {filename}" notifications.

**Risk:** The FastMCP `@mcp.tool()` decorator handles both sync and async handlers. Converting `def` to `async def` is transparent to the MCP protocol. Internal functions called by `tapps_upgrade` (`pipeline/upgrade.py`) are sync — they can remain sync since file I/O is fast.

### `tapps_dependency_graph`

**Current state:** Runs 3 sequential phases (build graph, detect cycles, calculate coupling) in 3-10s. Not truly multi-item, but users benefit from knowing which phase is active.

**Minimal adoption:** A single `ctx.info()` per phase provides useful feedback without the overhead of heartbeat progress or sidecar files.

## Acceptance Criteria

- [ ] `tapps_upgrade` converted from `def` to `async def`
- [ ] `tapps_upgrade` sends `ctx.info()` per file updated/created
- [ ] `tapps_upgrade` sends `ctx.info()` for backup creation
- [ ] `tapps_dependency_graph` sends `ctx.info()` per analysis phase
- [ ] All ctx usage follows the defensive access pattern
- [ ] Existing tests pass without modification (sync → async is transparent)
- [ ] New tests verify ctx notification content

---

## Stories

### 41.1 — Convert `tapps_upgrade` to Async

**Points:** 3

Convert `tapps_upgrade` from synchronous to asynchronous and add ctx progress notifications.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/server_pipeline_tools.py` (modify — `tapps_upgrade`)

**Tasks:**
- Change `def tapps_upgrade(...)` to `async def tapps_upgrade(...)`:
  - FastMCP handles async tools natively — no protocol-level changes needed
  - Internal sync calls (`upgrade_pipeline()`, `BackupManager`) remain sync — wrap in `await asyncio.to_thread()` if any are slow, otherwise call directly (file I/O is fast)
- Add `ctx: Context[Any, Any, Any] | None = None` parameter
- Before backup: `await emit_ctx_info(ctx, "Creating backup...")`
- After backup: `await emit_ctx_info(ctx, f"Backup created at {backup_path}")`
- Per file updated: `await emit_ctx_info(ctx, f"Updated {filename}")`
  - Thread ctx through to the upgrade functions, or collect file list and emit after each
- In `dry_run=True` mode: no ctx activity
- Verify all existing `tapps_upgrade` tests still pass (async transition should be transparent)

**Test File:**
- `packages/tapps-mcp/tests/unit/test_upgrade_ctx.py` (new)

**Tests (6):**
1. `test_ctx_info_called_per_file` — `ctx.info` called for each updated file
2. `test_ctx_info_backup_notification` — Backup creation triggers ctx.info
3. `test_ctx_noop_when_none` — No error when `ctx is None`
4. `test_ctx_noop_in_dry_run` — No ctx.info calls in dry_run mode
5. `test_ctx_info_exception_suppressed` — RuntimeError from ctx.info is swallowed
6. `test_upgrade_still_sync_compatible` — Existing sync test patterns still pass

---

### 41.2 — `tapps_dependency_graph` Phase-Based ctx.info

**Points:** 2

Add lightweight `ctx.info()` notifications at each analysis phase in `tapps_dependency_graph`.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/server_analysis_tools.py` (modify)

**Tasks:**
- Add `ctx: Context[Any, Any, Any] | None = None` parameter to `tapps_dependency_graph`
- Add three phase notifications:
  1. Before `build_import_graph()`: `ctx.info("Building import graph...")`
  2. Before `detect_cycles()` (if enabled): `ctx.info("Detecting circular imports...")`
  3. Before `calculate_coupling()` (if enabled): `ctx.info("Analyzing coupling metrics...")`
- After completion: `ctx.info(f"Analysis complete: {module_count} modules, {cycle_count} cycles")`
- Use `emit_ctx_info` from `server_helpers.py` (Story 39.5)

**Test File:**
- `packages/tapps-mcp/tests/unit/test_dep_graph_ctx.py` (new)

**Tests (5):**
1. `test_ctx_info_called_per_phase` — At least 3 ctx.info calls (build, detect, couple)
2. `test_ctx_info_skips_disabled_phases` — No cycle message when `detect_cycles=False`
3. `test_ctx_noop_when_none` — No error when `ctx is None`
4. `test_ctx_info_exception_suppressed` — RuntimeError from ctx.info is swallowed
5. `test_completion_message_includes_counts` — Final message has module and cycle counts

---

## Implementation Order

```
Epic 39 Story 39.5 (shared emit_ctx_info helper)
    ↓
41.1 (async upgrade + ctx)   — independent
41.2 (dependency_graph ctx)  — independent
```

Both stories are independent and can be implemented in parallel.

## Estimated Test Count

| Story | New Tests | Modified Tests |
|-------|-----------|---------------|
| 41.1 | 6 | 0 |
| 41.2 | 5 | 0 |
| **Total** | **11** | **0** |

## Out of Scope

- Sidecar progress files for `tapps_upgrade` or `tapps_dependency_graph` — these tools are fast enough that hook-based redundant delivery is unnecessary
- Converting other sync internal functions to async — only `tapps_upgrade` handler signature changes
- Heartbeat progress for `tapps_dependency_graph` — phases are sequential and short; per-phase ctx.info is sufficient

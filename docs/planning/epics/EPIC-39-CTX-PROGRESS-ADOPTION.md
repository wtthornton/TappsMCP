# Epic 39: MCP Context Progress Adoption

**Status:** Open
**Priority:** P2 — Medium (improves UX for long-running tools; no functional change)
**Estimated LOE:** ~1-1.5 weeks (1 developer)
**Dependencies:** None (builds on patterns established in `tapps_validate_changed`)
**Blocks:** None

---

## Goal

Adopt the MCP `ctx.info()` and `ctx.report_progress()` notification patterns across TappsMCP's long-running, multi-item tools. Currently only `tapps_validate_changed` uses these channels. This epic extends coverage to 4 additional tools where users experience a "Calculating..." spinner with no feedback for 5-60+ seconds.

## Motivation

**User problem:** When tools like `tapps_report` (project-wide scoring, 10-60s) or `tapps_init` (with cache warming, 10-35s) run, the user sees only a static spinner. There is no indication of progress, no per-item status, and no way to know if the tool is stuck or working.

**Established solution:** The `tapps_validate_changed` implementation (completed in prior work) proved three complementary notification patterns:

1. **`ctx.info()`** — Per-file log notifications that some clients render inline
2. **`ctx.report_progress(progress, total, message)`** — Count-based progress (X/Y files)
3. **Sidecar progress file** — Filesystem-based fallback for hooks

This epic applies Patterns 1 and 2 to tools where they provide the highest user benefit. Pattern 3 (sidecar) is reserved for tools where hook integration is valuable (only `tapps_report` in this epic).

## Reference

- [CTX_PATTERN_REFERENCE.md](../CTX_PATTERN_REFERENCE.md) — Standard patterns and defensive access rules
- `server_pipeline_tools.py` — Reference implementation in `tapps_validate_changed`

## Acceptance Criteria

- [ ] `tapps_report` sends `ctx.info()` per file scored and heartbeat progress during project-wide report
- [ ] `tapps_init` sends `ctx.info()` per file generated and heartbeat progress during cache/RAG warming
- [ ] `tapps_dependency_scan` sends heartbeat progress during pip-audit execution
- [ ] `tapps_dead_code` (scope=project|changed) sends `ctx.info()` per file scanned
- [ ] All ctx usage follows the defensive access pattern (null check, getattr, suppress)
- [ ] All tools gracefully degrade when `ctx is None` or client lacks method support
- [ ] Tests cover: ctx=None, ctx without method, ctx.info exception suppressed, message content

---

## Stories

### 39.1 — `tapps_report` ctx.info + Heartbeat Progress

**Points:** 5

Add per-file `ctx.info()` notifications and heartbeat progress to project-wide report generation.

**Why this tool:** `tapps_report` scores up to 20 files concurrently (default `max_files=20`), taking 10-60s. It's the second-longest-running tool after `tapps_validate_changed` and processes items in the same concurrent `asyncio.gather` pattern, making it a natural fit.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/server_analysis_tools.py` (modify)

**Tasks:**
- Add `ctx: Context[Any, Any, Any] | None = None` parameter to `tapps_report`
- Import `Context` from `mcp.server.fastmcp` in `server_analysis_tools.py`
- Create `_ProgressTracker` instance before the `asyncio.gather` scoring loop
- Update `_score_one()` inner function to accept and increment the tracker
- After each file is scored, call `ctx.info(f"Scored {path.name}: {score}/100")`
- Add heartbeat task using `_report_progress_heartbeat()` pattern:
  - Message format: `f"Scored {completed}/{total} files ({last_file})"`
  - Interval: 5 seconds
  - Cancel on completion
- Use the defensive access pattern for all ctx calls
- Pass `ctx=None` when `file_path` is provided (single-file mode — no progress needed)

**Test File:**
- `packages/tapps-mcp/tests/unit/test_report_ctx.py` (new)

**Tests (8):**
1. `test_ctx_info_called_per_file` — Verify `ctx.info` called once per scored file
2. `test_ctx_info_message_contains_filename` — Message includes the file name
3. `test_ctx_info_message_contains_score` — Message includes the numeric score
4. `test_ctx_noop_when_none` — No error when `ctx is None`
5. `test_ctx_noop_when_no_info_method` — No error when `ctx` has no `info` attr
6. `test_ctx_info_exception_suppressed` — RuntimeError from `ctx.info` is swallowed
7. `test_heartbeat_sends_progress_with_total` — `report_progress` called with `total=N`
8. `test_single_file_mode_no_ctx_calls` — When `file_path` is set, no ctx activity

---

### 39.2 — `tapps_init` ctx.info for File Generation + Heartbeat for Cache Warming

**Points:** 5

Enhance the existing `tapps_init` ctx usage (currently only Pattern 4: elicitation) with per-file `ctx.info()` during file generation and heartbeat progress during cache/RAG warming.

**Why this tool:** `tapps_init` already accepts a `ctx` parameter for elicitation. It generates 10+ files and can spend 10-35s warming caches. Users see no feedback during the warming phase.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/server_pipeline_tools.py` (modify — `tapps_init` handler)
- `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py` (modify — pass ctx through to generation/warming functions)

**Tasks:**
- Thread `ctx` parameter from `tapps_init` handler through to `run_init()` in `pipeline/init.py`
- After each file is created by `_create_templates()`, `_create_agents_md()`, and `_setup_platform()`:
  - Call `ctx.info(f"Created {filename}")` using the defensive pattern
- During `warm_cache()` (up to 20 libraries):
  - Start a heartbeat task: `f"Warming {i}/{total} libraries ({current})"`
  - Cancel on completion
- During `warm_expert_rag_indices()` (up to 10 domains):
  - Start a heartbeat task: `f"Indexing {i}/{total} domains"`
  - Cancel on completion
- No ctx activity in `dry_run=True` or `verify_only=True` modes

**Test File:**
- `packages/tapps-mcp/tests/unit/test_init_ctx.py` (new)

**Tests (7):**
1. `test_ctx_info_called_per_file_created` — `ctx.info` called for each generated file
2. `test_ctx_info_message_format` — Message starts with "Created " and contains filename
3. `test_ctx_noop_when_none` — No error when `ctx is None`
4. `test_ctx_noop_in_dry_run` — No ctx.info calls in dry_run mode
5. `test_ctx_noop_in_verify_only` — No ctx.info calls in verify_only mode
6. `test_cache_warming_heartbeat_sends_total` — `report_progress` called with correct total
7. `test_ctx_info_exception_suppressed` — Exceptions from ctx.info do not crash init

---

### 39.3 — `tapps_dependency_scan` Heartbeat Progress

**Points:** 3

Add heartbeat progress during the pip-audit execution in `tapps_dependency_scan`.

**Why this tool:** `tapps_dependency_scan` runs `pip-audit` as a subprocess (5-30s depending on package count and network). Users see no feedback during the scan.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/server_analysis_tools.py` (modify)

**Tasks:**
- Add `ctx: Context[Any, Any, Any] | None = None` parameter to `tapps_dependency_scan`
- Start a heartbeat task before calling `run_pip_audit_async()`:
  - Message format: `f"Scanning dependencies... ({elapsed}s elapsed)"`
  - Interval: 5 seconds
  - Since pip-audit is a single subprocess call, report elapsed time rather than item count
- Cancel heartbeat when `run_pip_audit_async()` returns
- After scan completes, send `ctx.info(f"Scan complete: {vuln_count} vulnerabilities found")`
- Use defensive access pattern for all ctx calls

**Test File:**
- `packages/tapps-mcp/tests/unit/test_dependency_scan_ctx.py` (new)

**Tests (5):**
1. `test_ctx_info_called_after_scan` — `ctx.info` called once with scan summary
2. `test_ctx_info_message_contains_vuln_count` — Message includes vulnerability count
3. `test_ctx_noop_when_none` — No error when `ctx is None`
4. `test_ctx_info_exception_suppressed` — RuntimeError from ctx.info is swallowed
5. `test_heartbeat_sends_progress_during_scan` — `report_progress` called during scan

---

### 39.4 — `tapps_dead_code` ctx.info for Project Scope

**Points:** 3

Add per-file `ctx.info()` notifications to `tapps_dead_code` when operating in `scope=project` or `scope=changed` mode.

**Why this tool:** In project-wide scope, `tapps_dead_code` scans many files (5-30s). Single-file scope is fast (< 2s) and doesn't need progress.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/server_analysis_tools.py` (modify)

**Tasks:**
- Add `ctx: Context[Any, Any, Any] | None = None` parameter to `tapps_dead_code`
- In scope=project and scope=changed paths only:
  - After collecting file list, send `ctx.info(f"Scanning {len(files)} files for dead code...")`
  - After scan completes, send `ctx.info(f"Dead code scan complete: {total_findings} items found")`
- In scope=file path: no ctx activity (single file, fast)
- Use defensive access pattern for all ctx calls

**Test File:**
- `packages/tapps-mcp/tests/unit/test_dead_code_ctx.py` (new)

**Tests (5):**
1. `test_ctx_info_called_for_project_scope` — `ctx.info` called with file count and results
2. `test_ctx_info_not_called_for_file_scope` — No ctx calls in single-file mode
3. `test_ctx_noop_when_none` — No error when `ctx is None`
4. `test_ctx_info_exception_suppressed` — RuntimeError from ctx.info is swallowed
5. `test_ctx_info_message_contains_finding_count` — Summary message includes count

---

### 39.5 — Shared `_emit_info` Helper Extraction

**Points:** 2

Extract the defensive `ctx.info()` helper into `server_helpers.py` so all server modules can reuse it without duplicating the pattern.

**Why:** Stories 39.1-39.4 each need the same defensive access pattern. Rather than copy-paste `_emit_file_info` into every module, extract a reusable helper.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/server_helpers.py` (modify)
- `packages/tapps-mcp/src/tapps_mcp/server_pipeline_tools.py` (modify — use shared helper)
- `packages/tapps-mcp/src/tapps_mcp/server_analysis_tools.py` (modify — use shared helper)

**Tasks:**
- Add `emit_ctx_info(ctx, message)` async helper to `server_helpers.py`:
  ```python
  async def emit_ctx_info(
      ctx: Context[Any, Any, Any] | None,
      message: str,
  ) -> None:
      """Send a ctx.info() log notification (best-effort, never raises)."""
      if ctx is None:
          return
      info_fn = getattr(ctx, "info", None)
      if not callable(info_fn):
          return
      with contextlib.suppress(Exception):
          await info_fn(message)
  ```
- Update `_emit_file_info` in `server_pipeline_tools.py` to delegate to `emit_ctx_info`
- Import and use `emit_ctx_info` in `server_analysis_tools.py` for stories 39.1, 39.3, 39.4
- Verify existing tests still pass after extraction

**Test File:**
- `packages/tapps-mcp/tests/unit/test_ctx_helpers.py` (new)

**Tests (5):**
1. `test_emit_ctx_info_calls_info` — Verifies `ctx.info` is called with the message
2. `test_emit_ctx_info_noop_when_none` — No error when `ctx is None`
3. `test_emit_ctx_info_noop_when_no_method` — No error when `ctx` lacks `info`
4. `test_emit_ctx_info_suppresses_exception` — RuntimeError suppressed
5. `test_emit_ctx_info_awaits_async` — Confirms the function awaits the info call

---

## Implementation Order

```
39.5 (shared helper)  →  39.1 (report)
                      →  39.2 (init)
                      →  39.3 (dependency_scan)
                      →  39.4 (dead_code)
```

Story 39.5 should be implemented first to provide the shared `emit_ctx_info` helper. Stories 39.1-39.4 can then be implemented in any order (they are independent).

## Estimated Test Count

| Story | New Tests | Modified Tests |
|-------|-----------|---------------|
| 39.1 | 8 | 0 |
| 39.2 | 7 | 0 |
| 39.3 | 5 | 0 |
| 39.4 | 5 | 0 |
| 39.5 | 5 | ~2 (update imports in existing sidecar tests) |
| **Total** | **30** | **~2** |

## Out of Scope

- **`tapps_upgrade`** — Synchronous function signature (`def`, not `async def`). Converting to async is a larger refactor deferred to a future epic.
- **`tapps_dependency_graph`** — Mostly single-call operations (build graph, detect cycles, calculate coupling). Per-phase messages provide minimal benefit.
- **Sidecar progress files** — Only `tapps_validate_changed` and `tapps_report` warrant sidecar files. Other tools are fast enough that hooks don't need filesystem fallback.
- **PostToolUse hooks** — Only `tapps_validate_changed` gets a PostToolUse hook (already implemented). Other tools don't run long enough to benefit from hook-based redundant delivery.

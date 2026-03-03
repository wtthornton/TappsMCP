# MCP Context (`ctx`) Pattern Reference

This document defines TappsMCP's standard patterns for using the MCP `Context` object
(`ctx`) in tool handlers. Use it as a reference when adding `ctx` support to new tools
or reviewing existing tools for adoption.

## Overview

The MCP `Context` object provides three notification channels back to the client:

| Channel | Method | Purpose | Client Support (2026) |
|---------|--------|---------|----------------------|
| **Progress** | `ctx.report_progress(progress, total, message)` | Percentage/count progress bars | Claude Code, Cursor (message ignored) |
| **Logging** | `ctx.info(msg)` / `ctx.debug(msg)` / `ctx.warning(msg)` / `ctx.error(msg)` | Inline status notifications | Partial (some clients render, some discard) |
| **Elicitation** | `ctx.elicit(message, schema)` | Interactive user prompts | Claude Code (others may not support) |

All channels are **best-effort** — clients may ignore notifications, lack support, or
time out. Tool handlers must never depend on these channels for correctness.

---

## Standard Defensive Access Pattern

Every `ctx` method call must follow this pattern:

```python
async def _emit_status(
    ctx: Context[Any, Any, Any] | None,
    message: str,
) -> None:
    """Send a ctx.info() notification (best-effort, never raises)."""
    if ctx is None:
        return
    info_fn = getattr(ctx, "info", None)
    if not callable(info_fn):
        return
    with contextlib.suppress(Exception):
        await info_fn(message)
```

### Why each guard matters

1. **`if ctx is None`** — Tool handlers declare `ctx` as `Context | None`. FastMCP
   injects context when available, but some call paths (tests, direct invocation) pass
   `None`.

2. **`getattr(ctx, "method", None)`** — Not all MCP SDK versions expose every method.
   Defensive attribute access prevents `AttributeError` on older clients.

3. **`contextlib.suppress(Exception)`** — Network errors, client disconnects, or
   protocol mismatches must never crash the tool. Progress/logging is advisory.

4. **`await`** — All `ctx` methods are async. Never call synchronously.

---

## Pattern 1: Per-File Progress Notifications (`ctx.info`)

**When to use:** Any tool that processes multiple items sequentially or concurrently
where the user benefits from seeing per-item status.

**Current adopter:** `tapps_validate_changed`

```python
async def _emit_file_info(
    ctx: Context[Any, Any, Any] | None,
    path: Path,
    result: dict[str, Any],
) -> None:
    """Send a ctx.info() log notification for the completed file."""
    if ctx is None:
        return
    info_fn = getattr(ctx, "info", None)
    if not callable(info_fn):
        return
    score = result.get("overall_score", "?")
    passed = result.get("gate_passed", False)
    status = "PASSED" if passed else "FAILED"
    with contextlib.suppress(Exception):
        await info_fn(f"Validated {path.name}: {score}/100, gate {status}")
```

**Key rules:**
- One `ctx.info()` call per completed item (not per retry or sub-step)
- Message format: `"{verb} {item}: {key_metric}, {status}"`
- Keep messages short (< 100 chars) — clients may truncate

### Candidate tools for adoption

| Tool | Items Processed | Suggested `ctx.info()` Message |
|------|----------------|-------------------------------|
| `tapps_report` | Multiple files scored | `"Scored {name}: {score}/100"` |
| `tapps_dead_code` (scope=project) | Multiple files scanned | `"Scanned {name}: {count} dead items"` |
| `tapps_dependency_scan` | Multiple packages audited | `"Checked {pkg}: {vuln_count} vulnerabilities"` |
| `tapps_dependency_graph` | Import graph built | `"Analyzed {name}: {import_count} imports"` |
| `tapps_init` | Multiple files generated | `"Created {filename}"` |
| `tapps_upgrade` | Multiple files refreshed | `"Updated {filename}"` |

---

## Pattern 2: Heartbeat Progress Reporting (`ctx.report_progress`)

**When to use:** Long-running tools (> 5 seconds) where the client can show a progress
bar or spinner with counts.

**Current adopter:** `tapps_validate_changed`

```python
@dataclasses.dataclass
class _ProgressTracker:
    """Shared progress state between validation workers and heartbeat."""
    total: int = 0
    completed: int = 0
    last_file: str = ""

async def _heartbeat(
    ctx: Context[Any, Any, Any],
    tracker: _ProgressTracker,
    stop_event: asyncio.Event,
) -> None:
    """Send progress updates every N seconds until stopped."""
    report = getattr(ctx, "report_progress", None)
    if not callable(report):
        return
    while not stop_event.is_set():
        done = tracker.completed
        last = tracker.last_file or "starting..."
        msg = f"Validated {done}/{tracker.total} files ({last})"
        with contextlib.suppress(Exception):
            await report(progress=done, total=tracker.total, message=msg)
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.wait_for(stop_event.wait(), timeout=5.0)
```

**Key rules:**
- Always send `total` (never `None`) so clients can render `X/Y`
- Heartbeat interval: 5 seconds (too fast clutters, too slow looks frozen)
- Run heartbeat as a background `asyncio.Task`; cancel on completion
- Store task reference in a `set()` to prevent garbage collection
- Thread-safe note: asyncio coroutines on same event loop — no locks needed

### Candidate tools for adoption

| Tool | Duration | Progress Type |
|------|----------|---------------|
| `tapps_init` (warm_cache) | 10-35s | `"Warming {i}/{total} libraries"` |
| `tapps_report` (project-wide) | 10-60s | `"Scored {i}/{total} files"` |
| `tapps_dependency_scan` | 5-30s | `"Auditing {i}/{total} packages"` |

---

## Pattern 3: Sidecar Progress File

**When to use:** Tools where the MCP response may not reach the LLM (context
compaction, client timeout, stdio buffering) and a secondary delivery path is needed.

**Current adopter:** `tapps_validate_changed`

**File location:** `{project_root}/.tapps-mcp/.validation-progress.json`

```json
{
  "status": "running",
  "total": 5,
  "completed": 3,
  "last_file": "scorer.py",
  "started_at": "2026-03-03T10:30:00Z",
  "results": [
    {"file": "server.py", "score": 62.0, "gate_passed": false},
    {"file": "models.py", "score": 88.5, "gate_passed": true},
    {"file": "scorer.py", "score": 82.0, "gate_passed": true}
  ]
}
```

**Terminal states:**

```json
{"status": "completed", "all_gates_passed": true, "summary": "...", "elapsed_ms": 1234}
{"status": "error", "error": "Scoring engine crashed"}
```

**Key rules:**
- Write atomically (overwrite entire file) — no partial JSON
- Suppress all write errors (unwritable path must not crash the tool)
- Include `started_at` timestamp for staleness detection by hooks
- Hooks read the file; the tool writes it — one writer, many readers

### Hook integration

The sidecar file enables three Claude Code hooks to provide redundant feedback:

| Hook Event | Script | Behavior |
|------------|--------|----------|
| **PostToolUse** | `tapps-post-validate.{sh,ps1}` | Reads sidecar after `tapps_validate_changed` completes; echoes summary to LLM transcript |
| **Stop** | `tapps-stop.{sh,ps1}` | Reads sidecar before session ends; includes last validation result in reminder |
| **TaskCompleted** | `tapps-task-completed.{sh,ps1}` | Reads sidecar when LLM declares task done; blocking variant lists failed files |

**Why three paths?**
1. **MCP tool response** — primary path, but can be lost to context compaction
2. **PostToolUse hook** — stdout goes into LLM transcript (immediate, reliable)
3. **Stop/TaskCompleted** — catch-all safety net before session ends

---

## Pattern 4: Interactive Elicitation (`ctx.elicit`)

**When to use:** Tools that need user input to select between options (presets,
configurations, wizard flows). Not a notification pattern — this blocks until the user
responds.

**Current adopters:** `tapps_quality_gate`, `tapps_init`

```python
async def _resolve_preset(
    preset: str,
    ctx: Context[Any, Any, Any] | None,
) -> str:
    """Resolve quality gate preset, falling back to 'standard'."""
    if not preset and ctx is not None:
        from tapps_mcp.common.elicitation import elicit_preset
        selected = await elicit_preset(ctx)
        if selected is not None:
            return selected
    return preset or "standard"
```

**Key rules:**
- Only elicit when the parameter is empty/missing (respect explicit values)
- Always provide a fallback default for non-interactive clients
- Wrap in try/except — not all clients support elicitation

---

## Current Adoption Matrix

| Tool | `ctx.info` | `ctx.report_progress` | Sidecar File | `ctx.elicit` |
|------|-----------|----------------------|-------------|-------------|
| tapps_validate_changed | YES | YES | YES | - |
| tapps_quality_gate | - | - | - | YES |
| tapps_init | - | - | - | YES |
| tapps_score_file | - | - | - | - |
| tapps_quick_check | - | - | - | - |
| tapps_security_scan | - | - | - | - |
| tapps_report | - | - | - | - |
| tapps_dead_code | - | - | - | - |
| tapps_dependency_scan | - | - | - | - |
| tapps_dependency_graph | - | - | - | - |
| tapps_lookup_docs | - | - | - | - |
| tapps_consult_expert | - | - | - | - |
| tapps_research | - | - | - | - |
| tapps_init | - | - | - | YES |
| tapps_upgrade | - | - | - | - |
| tapps_session_start | - | - | - | - |
| tapps_doctor | - | - | - | - |
| tapps_dashboard | - | - | - | - |
| tapps_stats | - | - | - | - |
| tapps_feedback | - | - | - | - |
| tapps_memory | - | - | - | - |
| tapps_session_notes | - | - | - | - |
| tapps_impact_analysis | - | - | - | - |
| tapps_checklist | - | - | - | - |
| tapps_server_info | - | - | - | - |
| tapps_validate_config | - | - | - | - |
| tapps_list_experts | - | - | - | - |
| tapps_project_profile | - | - | - | - |
| tapps_set_engagement_level | - | - | - | - |

---

## Priority Adoption Recommendations

### Tier 1 — High Value (long-running, multi-item tools)

1. **`tapps_report`** (project-wide scoring) — Add `ctx.info` per file + heartbeat
2. **`tapps_init`** (with cache warming) — Add `ctx.info` per file created + heartbeat
3. **`tapps_dependency_scan`** — Add `ctx.info` per package checked

### Tier 2 — Medium Value (moderate duration)

4. **`tapps_upgrade`** — Add `ctx.info` per file updated
5. **`tapps_dead_code`** (scope=project) — Add `ctx.info` per file scanned
6. **`tapps_dependency_graph`** — Add `ctx.info` for cycle detection status

### Tier 3 — Low Value (fast tools, single-item)

7. **`tapps_score_file`** — Single file, typically < 2s. `ctx.info` optional.
8. **`tapps_quick_check`** — Single file, typically < 1s. Not needed.
9. **`tapps_security_scan`** — Single file. Not needed.

### Not recommended

- `tapps_session_start`, `tapps_server_info`, `tapps_project_profile` — instantaneous
- `tapps_stats`, `tapps_feedback`, `tapps_memory` — fast lookups
- `tapps_session_notes`, `tapps_checklist` — pure computation

---

## Implementation Checklist

When adding `ctx` support to a tool:

- [ ] Add `ctx: Context[Any, Any, Any] | None = None` to the handler signature
- [ ] Import `Context` from `mcp.server.fastmcp` at runtime (not `TYPE_CHECKING`)
- [ ] Use the defensive access pattern (null check → getattr → suppress)
- [ ] For `ctx.info`: one call per completed item, concise message
- [ ] For `ctx.report_progress`: always include `total`, 5s heartbeat interval
- [ ] For sidecar files: atomic writes, suppress errors, include timestamps
- [ ] Add tests: mock `ctx.info = AsyncMock()`, assert call count and message content
- [ ] Add tests: verify no error when `ctx is None`
- [ ] Add tests: verify no error when `ctx` lacks the method (`spec=[]`)
- [ ] Add tests: verify exception from `ctx.info()` is suppressed

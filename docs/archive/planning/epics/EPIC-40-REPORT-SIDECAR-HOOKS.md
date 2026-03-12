# Epic 40: Report Sidecar Progress & Hook Integration

**Status:** Complete
**Priority:** P3 — Low (UX enhancement; supplements Epic 39)
**Estimated LOE:** ~0.5-1 week (1 developer)
**Dependencies:** Epic 39 (MCP Context Progress Adoption — specifically Story 39.1)
**Blocks:** None

---

## Goal

Add sidecar progress file and PostToolUse hook support to `tapps_report`, mirroring the pattern established in `tapps_validate_changed`. This ensures project-wide report results reach the user even when the MCP tool response is lost to context compaction, client timeout, or stdio buffering.

## Motivation

**Why `tapps_report` needs a sidecar:**

`tapps_report` in project-wide mode (no `file_path`) scores up to 20 files, taking 10-60s. This puts it in the same "long-running, results-may-be-lost" category as `tapps_validate_changed`. The three visibility gaps apply:

1. **During execution:** User sees only a spinner (addressed by Epic 39 ctx.info/heartbeat)
2. **Tool response lost:** Context compaction or client timeout drops the result (addressed here)
3. **No recovery path:** Without a sidecar, the LLM has no way to retrieve lost results (addressed here)

**Why other tools don't need a sidecar:**

- `tapps_dependency_scan` (5-30s) — Results are a simple list; re-running is cheap
- `tapps_dead_code` (5-30s) — Same: re-run is fast and results are small
- `tapps_init` — One-time setup; user observes file creation directly in their editor

## Reference

- [CTX_PATTERN_REFERENCE.md](../CTX_PATTERN_REFERENCE.md) — Pattern 3: Sidecar Progress File
- `server_pipeline_tools.py` — Reference implementation (`_ProgressTracker`, sidecar write/read)

## Acceptance Criteria

- [ ] `tapps_report` writes a `.tapps-mcp/.report-progress.json` sidecar file during project-wide scoring
- [ ] Sidecar file records per-file scores as they complete
- [ ] Sidecar file records final status (completed/error) with summary
- [ ] PostToolUse hook reads the sidecar after `tapps_report` completes
- [ ] Stop/TaskCompleted hooks read report sidecar (if present) alongside validation sidecar
- [ ] All sidecar writes are fault-tolerant (suppress errors, no crash on unwritable path)
- [ ] Tests cover sidecar creation, updates, finalization, error handling, and hook reading

---

## Stories

### 40.1 — Report Sidecar Progress File

**Points:** 3

Write a `.report-progress.json` sidecar file during project-wide `tapps_report` execution.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/server_analysis_tools.py` (modify)

**Tasks:**
- Define `_REPORT_PROGRESS_FILE = ".tapps-mcp/.report-progress.json"` constant
- Reuse or adapt `_ProgressTracker` pattern from `server_pipeline_tools.py`:
  - `init_sidecar(project_root)` — create file with `status: "running"`
  - `record_file_result(file_path, result)` — append per-file score
  - `finalize(summary, elapsed_ms)` — set `status: "completed"`
  - `finalize_error(error)` — set `status: "error"`
- Call `init_sidecar` before the `asyncio.gather` scoring loop
- Call `record_file_result` after each file is scored
- Call `finalize` after all results are collected
- Wrap in try/except for `finalize_error` on unexpected errors
- Only write sidecar in project-wide mode (skip when `file_path` is set)

**Sidecar schema:**
```json
{
  "status": "running",
  "total": 20,
  "completed": 12,
  "last_file": "scorer.py",
  "started_at": "2026-03-03T10:30:00Z",
  "results": [
    {"file": "server.py", "score": 62.0},
    {"file": "models.py", "score": 88.5}
  ]
}
```

**Test File:**
- `packages/tapps-mcp/tests/unit/test_report_sidecar.py` (new)

**Tests (6):**
1. `test_sidecar_created_on_init` — File exists with `status: "running"`
2. `test_sidecar_records_file_results` — Results array grows with each file
3. `test_sidecar_finalize_sets_completed` — Final status is `"completed"` with summary
4. `test_sidecar_finalize_error` — Error status with error message
5. `test_sidecar_not_written_in_single_file_mode` — No sidecar when `file_path` is set
6. `test_sidecar_survives_write_error` — No exception on unwritable path

---

### 40.2 — PostToolUse Hook for `tapps_report`

**Points:** 2

Add a PostToolUse hook that reads the report sidecar after `tapps_report` completes and echoes the summary to the LLM transcript.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_hook_templates.py` (modify)

**Tasks:**
- Add `tapps-post-report.sh` to `CLAUDE_HOOK_SCRIPTS`:
  - Reads `.tapps-mcp/.report-progress.json`
  - If `status == "completed"`: echoes `"Report complete: N files scored, avg M/100"`
  - If `status == "error"`: echoes `"Report failed: {error}"`
  - If file missing: exit silently
  - Exit 0 (advisory, never blocking)
- Add `tapps-post-report.ps1` to `CLAUDE_HOOK_SCRIPTS_PS` (PowerShell equivalent)
- Add PostToolUse config entry with `matcher: "mcp__tapps-mcp__tapps_report"` and `timeout: 10`
- Update script count assertions in `test_platform_generators.py` (13 → 14)

**Test File:**
- `packages/tapps-mcp/tests/unit/test_post_report_hook.py` (new)

**Tests (6):**
1. `test_bash_script_exists` — Script key in `CLAUDE_HOOK_SCRIPTS`
2. `test_bash_script_reads_report_progress` — `.report-progress.json` referenced
3. `test_bash_script_handles_completed` — Contains "completed" and summary output
4. `test_ps_script_exists` — Script key in `CLAUDE_HOOK_SCRIPTS_PS`
5. `test_config_has_report_matcher` — PostToolUse has `tapps_report` matcher
6. `test_config_timeout` — Hook timeout is 10 seconds

---

### 40.3 — Stop/TaskCompleted Hooks Read Report Sidecar

**Points:** 2

Update existing Stop and TaskCompleted hooks to also read the report sidecar alongside the validation sidecar.

**Source Files:**
- `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_hook_templates.py` (modify)

**Tasks:**
- Update 4 Stop hook scripts (medium bash/ps, blocking bash/ps) to:
  - Read `.tapps-mcp/.report-progress.json` if it exists
  - Append "Last report: N files, avg score M/100" to the reminder message
  - Keep existing validation sidecar reading unchanged
- Update 4 TaskCompleted hook scripts similarly:
  - Read report sidecar if present
  - Show report summary alongside validation summary
  - Blocking variants: include low-scoring files from report in the failure list

**Test File:**
- Update `packages/tapps-mcp/tests/unit/test_post_validate_hook.py` (modify)

**Tests (4 new):**
1. `test_stop_reads_report_progress` — Stop script references `.report-progress.json`
2. `test_stop_ps_reads_report_progress` — PS variant references `.report-progress.json`
3. `test_task_completed_reads_report_progress` — TaskCompleted references report sidecar
4. `test_task_completed_ps_reads_report_progress` — PS variant references report sidecar

---

## Implementation Order

```
Epic 39 Story 39.1 (tapps_report ctx.info)
    ↓
40.1 (report sidecar)  →  40.2 (PostToolUse hook)
                        →  40.3 (Stop/TaskCompleted hooks read report sidecar)
```

Story 40.1 must be complete before 40.2 and 40.3 (they read the file 40.1 writes). Stories 40.2 and 40.3 are independent of each other.

## Estimated Test Count

| Story | New Tests | Modified Tests |
|-------|-----------|---------------|
| 40.1 | 6 | 0 |
| 40.2 | 6 | 1 (script count) |
| 40.3 | 4 | 0 |
| **Total** | **16** | **1** |

## Out of Scope

- Sidecar files for `tapps_dependency_scan`, `tapps_dead_code`, `tapps_init` — these tools are either fast enough or one-time operations where sidecar redundancy doesn't justify the complexity
- Hook-based retries or automatic re-running of failed reports
- Persistent report history or trend tracking (belongs in metrics/dashboard)

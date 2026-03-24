# TappsMCP checklist (`tapps_checklist`)

The checklist tracks **which MCP tools were invoked** in the current **checklist session** and compares that to **task-type policy** (required / recommended / optional), adjusted by **engagement level** and optional **`.tapps-mcp/checklist-policy.yaml`** overrides.

## Session boundary

- Calling **`tapps_session_start`** starts a new checklist session (new `checklist_session_id`).
- The server returns `checklist_session_id` in session start and checklist responses.
- Tool calls before the first `tapps_session_start` in a process use **legacy mode**: all persisted rows are visible (backward compatible for tests and minimal setups).
- After a session boundary, only JSONL rows whose `session_id` matches the active session are evaluated.
- Use **`tapps_checklist(..., reset_checklist_session=True)`** to rotate the checklist session without a full session start (long-lived servers).

## Persistence and locking

- Append log: `.tapps-mcp/sessions/checklist_calls.jsonl` (each line includes `tool_name`, `timestamp`, `session_id`, `success`).
- Active session id file: `.tapps-mcp/sessions/checklist_active_session`.
- Writes use a **file lock** (`checklist_calls.jsonl.lock`) to reduce corruption under concurrent processes.

## Policy version and overrides

- Responses include **`checklist_policy_version`** (hash of merged built-in maps + optional policy file).
- Optional file: **`.tapps-mcp/checklist-policy.yaml`**

```yaml
extra_required:
  feature:
    - tapps_dependency_scan
extra_recommended:
  review:
    - tapps_memory
```

## Strict task types

- Set **`checklist_strict_unknown_task_types: true`** in `.tapps-mcp.yaml` (or env **`TAPPS_MCP_CHECKLIST_STRICT_UNKNOWN_TASK_TYPES`**) so unknown `task_type` values **error** instead of falling back to the `review` policy.

## Outcome-aware mode

- Set **`checklist_require_success: true`** (or **`TAPPS_MCP_CHECKLIST_REQUIRE_SUCCESS`**) so the **latest receipt per tool** must be **`success: true`** for that tool to count. Failed gates / scans record failure for key tools when possible.

## OpenTelemetry hints (optional)

If the host exports:

- `TAPPS_OTEL_TRACE_ID`
- `TAPPS_OTEL_SPAN_ID`

checklist responses include **`otel_trace_hint`** for correlation with external traces.

## Epic markdown validation

Pass **`epic_file_path`** to `tapps_checklist` (with **`task_type="epic"`** recommended) to attach **`epic_validation`** (structural checks on the epic document).

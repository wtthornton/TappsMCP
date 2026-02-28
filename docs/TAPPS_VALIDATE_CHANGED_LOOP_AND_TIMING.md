# tapps_validate_changed: Loop and Timing Review

## 1. The Loop (Why the Reminder Repeats)

### What triggers the message

The text **"Before ending: please run tapps_validate_changed to confirm all changed files pass quality gates."** is produced by:

- **Pipeline rules**  
  `.cursor/rules/tapps-pipeline.mdc` and `tapps-pipeline.md` state that you must call `tapps_validate_changed()` before declaring work complete. The agent is instructed to do that and to remind the user.

So the “loop” is:

1. Rules instruct the agent to call `tapps_validate_changed()` before declaring work complete.
2. User (or agent) runs `tapps_validate_changed`.
3. If the call is **slow or aborted**, the user may try to end again → rules still instruct validation on the next session → same reminder. No “validation completed” state is stored for the rules to check, so the reminder is shown every time.

> **Note:** The Cursor `stop` hook was removed. Validation reminders now come only from the pipeline rules. The rules do **not** know whether validation actually ran or succeeded. The only way to “break” the loop from the user’s perspective is for `tapps_validate_changed` to **finish successfully** (and ideally quickly) so the user can end the session without feeling stuck.

---

## 2. Timing (Where Time Is Spent)

### Path A: No changed files (early return)

When there are no changed Python files, the handler:

1. **`_record_call("tapps_validate_changed")`**  
   - First time only: `load_settings()`, then `CallTracker.set_persist_path()` → `_load_persisted()` reads the full checklist JSONL (can be slow if the file is large or on slow storage).  
   - Every time: `CallTracker.record()` → `_persist_record()` does a sync append to disk (blocking).

2. **`load_settings()`**  
   - Cached after first use. First time: read `.tapps-mcp.yaml`, build settings. Usually fast.

3. **`detect_changed_python_files(project_root, base_ref)`**  
   - Two git diffs run **in parallel** in a `ThreadPoolExecutor` (unstaged and staged), each with a **5 s** timeout.  
   - Wall time for git is therefore at most ~5 s (not 10 s).

4. **Early return branch**  
   - `_record_execution` is **deferred** to a background task (so MetricsHub creation and `execution.record()` do not block the response).  
   - Build `success_response` and call `_with_nudges()`.

5. **`_with_nudges()`**  
   - Imports and runs `compute_next_steps`, `compute_pipeline_progress`, `compute_suggested_workflow`.  
   - Each uses `CallTracker.get_called_tools()` (in-memory after first load).  
   - Typically fast unless the checklist module or filesystem is slow.

So on the “no changed files” path, the main variable costs are:

- First-time: checklist setup + first `load_settings` + first `_load_persisted` read + one sync persist write.
- Every time: one sync append in `_persist_record`, two parallel git diffs (up to 5 s), and nudges.

Observed wall times for this path have ranged from ~10 s to ~2–3 minutes, which suggests:

- **Client/network/process startup**: MCP server cold start or client timeout/retry can dominate.
- **First-time checklist/metrics**: First call in a session pays for checklist and (if ever on the “with files” path) MetricsHub init.
- **Git**: Unlikely to exceed 5 s per run due to the timeout; large or slow repos could still approach that.

If the **client request timeout** (e.g. 30–60 s) is reached before the server sends the response, the client aborts the request and shows “Error: Aborted.” So any remaining blocking work on this path (e.g. `_record_call` persist, or slow `_with_nudges`) can still cause aborts when the total time exceeds the client’s timeout.

---

### Path B: With changed files (validation branch)

When there are changed files:

1. **Same as Path A** up to and including `detect_changed_python_files` (so same `_record_call`, `load_settings`, git, and up to 5 s for git).

2. **Progress**  
   - If the client supplies a context with `report_progress`, an initial progress message is sent and a heartbeat task runs every 5 s so the client does not think the request is hung.

3. **`await ensure_session_initialized()`**  
   - **First time in session**: runs `detect_project_profile(project_root)` in a thread (TechStack detection + project type, etc.). This can take **tens of seconds to minutes** on large repos.  
   - Later calls: no-op.

4. **Scorer and per-file work**  
   - Default is **quick mode** (`quick=True`): for each file, `score_file_quick` (ruff-only) in a thread, then gate evaluation. Concurrency is capped by `_VALIDATE_CONCURRENCY` (10).  
   - If `quick=False`: full scoring (ruff, mypy, bandit, radon, vulture) per file → much slower (1–5+ minutes for many files).

5. **After all files**  
   - `_record_execution(..., gate_passed=...)` runs **synchronously** (not deferred on this path).  
   - Then `success_response` and `_with_nudges`.

So when there are files to validate:

- **First run in session**: session init (project profile) dominates; then N × (quick or full) per-file work. This can easily exceed a 30–60 s client timeout and lead to “Error: Aborted.”
- **Subsequent runs** (same session): no session init; quick mode is usually on the order of seconds per file (ruff subprocess per file), but with many files or slow disk it can still exceed the client timeout.

---

## 3. Why “Error: Aborted” Happens

- **Client timeout**  
  The client (e.g. Cursor) stops waiting after a fixed time (often 30–60 s or similar). If the server has not returned by then, the client aborts and shows “Error: Aborted.”  
  So any combination of:
  - first-time checklist/load_settings,
  - git (up to 5 s),
  - first-time session init (when there are files),
  - N × per-file validation,
  - sync I/O in `_record_call` or `_record_execution`  
  that pushes total time over the client’s limit will cause an abort.

- **User or UI cancellation**  
  The user (or UI) can cancel the running tool; the client then aborts the request and shows the same “Error: Aborted.”

In both cases the server may have done part or all of the work, but the client never receives a normal success response, so the “before ending” reminder will appear again on the next session.

---

## 4. Summary Table

| Path              | Main cost                                      | Deferred / non-blocking already              |
|-------------------|------------------------------------------------|----------------------------------------------|
| No changed files  | _record_call (first-time + persist), git ≤5 s, _with_nudges | _record_execution (metrics)                  |
| With files        | ensure_session_initialized (first time), N × (quick or full) | Dependency cache warm; progress heartbeat    |

The flow is driven by rules instructing the agent to run `tapps_validate_changed` before declaring work complete; timing and aborts are driven by client timeout and by any remaining blocking or slow work on the server before the response is sent.

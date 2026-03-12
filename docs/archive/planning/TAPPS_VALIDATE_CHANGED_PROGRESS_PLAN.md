# tapps_validate_changed progress notifications – local plan

**Source:** [HomeIQ TAPPS_VALIDATE_CHANGED_HANG_ANALYSIS.md](C:\cursor\HomeIQ\implementation\TAPPS_VALIDATE_CHANGED_HANG_ANALYSIS.md)
**Date:** 2026-02-25
**Status:** COMPLETE — All items implemented and verified 2026-02-25.

---

## Problem summary

- `tapps_validate_changed` can run **44 s to 3+ minutes** even with **0** changed files (git diff + discovery + dependency warm-up).
- With many changed files, total time reaches **several more minutes**.
- Many MCP clients use a **~60 s** request timeout and do not reset it on progress, so the tool is aborted with "Error: Aborted" or timeout (-32001).
- **No progress updates** are sent during the run, so the client has no signal that work is ongoing.

---

## Recommendations (from analysis)

1. **Client/IDE:** Increase MCP timeout (e.g. 300000 ms) for the TappsMCP server.
2. **Fallback:** Prefer `tapps_quick_check(file_path)` per file when the batch call is unreliable.
3. **CI:** Use GitHub Actions `tapps-mcp validate-changed` for full batch validation on PRs.
4. **Server-side (this plan):** Send **progress notifications** every 5–10 s during `tapps_validate_changed` so clients can avoid treating the request as hung.

---

## Implementation plan

### 1. Progress notifications in `tapps_validate_changed`

- Add an optional **`ctx: Context | None = None`** parameter to `tapps_validate_changed` (same pattern as `tapps_quality_gate` and `tapps_init`).
- When `ctx` is not None and the context supports progress reporting:
  - **Phase 1 – Discovery:** After resolving the file list, send one progress message (e.g. "Validating N files…").
  - **Phase 2 – Heartbeat:** While validation runs (e.g. during dependency warm-up and during `asyncio.gather`), send a **heartbeat** every **8 seconds** with a monotonic progress value (e.g. elapsed seconds) and message like "Validating N files… (in progress)".
- Use a small helper that:
  - Runs a background task that sleeps 8 s and then calls `ctx.report_progress(...)` if the context exposes such a method.
  - Stops when the main validation completes (cancel the task or use a shared "done" flag).
- **Graceful degradation:** If `ctx` is None or `report_progress` is missing or fails (e.g. client did not send a progress token), the tool continues as today; no progress is sent.

### 2. Behaviour and compatibility

- **Backward compatible:** Callers that do not pass `ctx` see no change. MCP host injects `Context` when available.
- **Spec-aligned:** MCP progress spec (e.g. 2025-06-18) allows progress notifications with `progress`, optional `total`, and `message`; progress must increase. Using elapsed time as progress when total is unknown is valid.
- **No change to result:** The tool’s return value and semantics are unchanged; only optional out-of-band progress notifications are added.

### 3. Tests and docs

- **Unit test:** When a mock `Context` with `report_progress` is passed, ensure it is called (e.g. at least once, or with expected message pattern); when `ctx` is None, ensure no progress call is made and the tool still returns the same shape of result.
- **Docs:** Mention in `AGENTS.md` / `CLAUDE.md` that `tapps_validate_changed` may send progress notifications so clients that support progress tokens can show activity and avoid timeout/abort.

---

## Definition of done

- [x] `tapps_validate_changed` accepts optional `ctx: Context | None = None`. — `server_pipeline_tools.py:101`
- [x] When `ctx` is provided and supports progress, progress notifications are sent (discovery + heartbeat every ~8 s). — `_validate_progress_heartbeat()` at line 65; initial report at line 185; heartbeat task at line 192
- [x] When `ctx` is None or progress is unsupported, behaviour is unchanged and no errors are raised. — Guard at line 181 (`if ctx is not None`); `getattr`/`callable` check in heartbeat helper
- [x] Unit tests cover progress and no-progress paths. — `test_progress_notifications_when_ctx_provided` (line 326); 9 other tests call without ctx (implicit None)
- [x] Docs (e.g. AGENTS.md) note that progress notifications may be sent during `tapps_validate_changed`. — AGENTS.md tool table + troubleshooting section

## Verification notes (2026-02-25)

All five items were verified against the current codebase. No remaining work. This plan is closed.

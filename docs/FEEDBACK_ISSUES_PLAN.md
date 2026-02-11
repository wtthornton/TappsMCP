# TAPPS-MCP Feedback Issues — Fix Plan

**Source:** [Site24x7 TAPPS_MCP_FEEDBACK.md](../../Site24x7/TAPPS_MCP_FEEDBACK.md)  
**Date:** 2026-02-11  
**Status:** Plan (issues to fix)

---

## Summary of Reported Problem

When running TappsMCP via a **standalone binary** (`tapps-mcp.exe`) on Windows (Cursor IDE), **all** tool invocations fail with:

```text
Error executing tool: No module named 'tapps_mcp.tools.checklist'
```

Affected tools include `tapps_list_experts`, `tapps_consult_expert`, `tapps_server_info`, `tapps_project_profile`, and effectively every tool, because each handler calls `_record_call(tool_name)` which performs a lazy `from tapps_mcp.tools.checklist import CallTracker`. The first tool call therefore triggers the missing-module error.

---

## Root Cause (Findings)

1. **Call path:** In `src/tapps_mcp/server.py`, every tool calls `_record_call(tool_name)` at the start. `_record_call()` does:
   ```python
   from tapps_mcp.tools.checklist import CallTracker
   CallTracker.record(tool_name)
   ```
2. **Module exists in repo:** `src/tapps_mcp/tools/checklist.py` exists and is part of the package. With a normal install (e.g. `pip install tapps-mcp` or `uv sync`), `tapps_mcp.tools.checklist` is available.
3. **Likely cause:** The **standalone executable** (`tapps-mcp.exe`) is built in a way that does **not** bundle or expose `tapps_mcp.tools.checklist` (e.g. only entrypoint and transitive imports are included). So when the binary runs, that import fails.

---

## Issues to Fix

### 1. **Resilience: optional checklist import (high priority)**

**Problem:** A single missing optional dependency (or packaging omission) breaks every tool.

**Change:** Make the checklist dependency non-fatal.

- In `server.py`: In `_record_call()`, wrap the import and `CallTracker.record()` in a try/except. On `ImportError`, no-op (optionally log at debug) so tool execution continues without session call tracking.
- In `server.py`: In `tapps_checklist()` itself, if `from tapps_mcp.tools.checklist import CallTracker` (or the checklist evaluation logic) fails, return a structured response indicating “checklist unavailable” (e.g. `complete: false`, message explaining the module is missing) instead of raising.
- In `common/nudges.py`: Lazy import of `CallTracker` is already inside logic that uses it; make that import safe (try/except, fallback to “no nudges” or skip checklist-based nudges when the module is missing).

**Acceptance:** When `tapps_mcp.tools.checklist` is missing (e.g. in a minimal or broken binary), all other tools (server_info, list_experts, consult_expert, etc.) run successfully; `tapps_checklist` returns a clear “unavailable” result instead of a generic import error.

---

### 2. **Distribution: ensure `tapps_mcp.tools` is included (high priority)**

**Problem:** Standalone binary fails to resolve `tapps_mcp.tools.checklist`; likely the build does not include the full `tapps_mcp.tools` package.

**Actions:**

- **If the binary is built in-repo:** Identify the build method (e.g. PyInstaller, shiv, uv tool, etc.). Ensure the spec/config explicitly includes `tapps_mcp.tools` and all submodules (e.g. `tapps_mcp.tools.checklist`). Add a test or CI step that runs the built binary and calls at least one tool (e.g. `tapps_server_info`) to verify no import error.
- **If the binary is built elsewhere:** Document in `docs/` that the standalone executable **must** include the full `tapps_mcp` package (including `tapps_mcp.tools.checklist`). Provide a “recommended install” path (e.g. `pip install tapps-mcp` / `uv tool install` from PyPI) so that a correctly installed environment is the default recommendation.

**Acceptance:** Either the shipped binary includes the checklist module and all tools work, or the docs clearly state how to install so that the checklist (and thus all tools) work.

---

### 3. **Documentation: install, upgrade, and Windows (medium priority)**

**Problem:** User asked for recommended install/upgrade and Windows compatibility.

**Actions:**

- Add a short **Install & upgrade** section (e.g. in `README.md` and/or `docs/TAPPS_MCP_SETUP_AND_USE.md`):
  - **Recommended:** Install with `pip install tapps-mcp` or `uv tool install tapps-mcp` (or from repo with `pip install -e .` / `uv sync`), then run `tapps-mcp serve`. Prefer this over a standalone `.exe` unless the build is known to include the full package.
  - **Upgrade:** `pip install -U tapps-mcp` / `uv tool install -U tapps-mcp` (and note any breaking changes in CHANGELOG).
  - **Standalone binary:** If using a pre-built executable, ensure it is built with the full `tapps_mcp` package (see issue 2). Document any known Windows-specific issues (e.g. path handling, encoding).
- Optionally add a **Troubleshooting** subsection: “All tools fail with `No module named 'tapps_mcp.tools.checklist'`” → use pip/uv install, or rebuild the binary with the full package.

**Acceptance:** Users can find a clear recommended install/upgrade path and know what to do when the checklist import error appears.

---

### 4. **Migration: tapps-agents → tapps-mcp (medium priority)**

**Problem:** User is migrating from tapps-agents and wants a clear migration path (what to keep, remove, configure).

**Actions:**

- Add a **Migration from tapps-agents** section (e.g. in `docs/TAPPS_MCP_SETUP_AND_USE.md` or a dedicated `docs/MIGRATION_FROM_TAPPS_AGENTS.md`):
  - **Remove:** Old tapps-agents config/runtime (e.g. `.tapps-agents/`, agents-specific config) where superseded by TappsMCP.
  - **Keep:** Project layout, quality expectations, and any custom knowledge or rules that are file-based and can be reused (e.g. docs or prompts that TappsMCP can read).
  - **Configure:** MCP host config (e.g. `.cursor/mcp.json`) to point to `tapps-mcp serve` (command or URL). Optionally `.tapps-mcp.yaml` in project root for preset, timeouts, etc.
- Link to this from README so “migrating from tapps-agents” is easy to find.

**Acceptance:** A user moving from tapps-agents to tapps-mcp has a single place to read what to remove, what to keep, and how to point the host at TappsMCP.

---

## Out of Scope (for this plan)

- Changes to the Site24x7 project itself (only TappMCP repo changes are in scope).
- Adding new features beyond “checklist optional” and “clear error when checklist is unavailable.”

---

## Implementation Order

1. **Resilience (issue 1):** Implement optional checklist import and safe behavior in `server.py` and `nudges.py` so that existing binaries and minimal installs stop failing for every tool.
2. **Documentation (issues 3 and 4):** Add install/upgrade/Windows and migration notes so users can get unblocked and migrate cleanly.
3. **Distribution (issue 2):** Confirm how the `.exe` is produced; then either fix the build to include `tapps_mcp.tools` or document the requirement and recommend pip/uv install.

---

## Checklist for closure

- [x] `_record_call` and `tapps_checklist` handle missing `tapps_mcp.tools.checklist` without breaking other tools.
- [x] Nudges code handles missing checklist module without raising.
- [x] Docs describe recommended install/upgrade and Windows.
- [x] Docs describe migration from tapps-agents (what to remove, keep, configure).
- [x] Binary build is fixed or documented so that `tapps_mcp.tools.checklist` is available when using the standalone executable.

# TappsMCP Tool UX Review (Agent Session)

**Review date:** 2026-03-09
**Context:** Agent used TappsMCP tools during Epic 65 Memory implementation (Phase 1, quality verification)

---

## Tools Used

| Tool | Purpose | Result |
|------|---------|--------|
| **tapps_session_start** | First call; server info, checkers | ✅ Worked well. Quick mode fast; clear next_steps |
| **tapps_validate_changed** | Batch validate changed files | ⚠️ Returned 0 files validated despite explicit file_paths |
| **tapps_checklist** | Final verification; auto_run validate_changed | ✅ Worked. complete=true; auto_run succeeded |

---

## What Worked Well

1. **tapps_session_start**
   - Quick mode (~600ms) avoided slow subprocess checks
   - Clear server info (version, checkers, preset)
   - `recommended_next` and `next_steps` helpful
   - `pipeline_progress` tracks tools called

2. **tapps_checklist**
   - Clear `missing_required` / `missing_recommended` / `missing_optional`
   - `missing_required_hints` explains *why* each tool is needed
   - `auto_run: true` ran `tapps_validate_changed` automatically
   - `complete: true` when required steps satisfied

3. **Schema / discovery**
   - Tool schemas in mcps folder enable parameter checking before calls
   - AGENTS.md gives clear guidance on when to use each tool

---

## Issues Observed

### 1. tapps_validate_changed: 0 files validated with explicit file_paths

**Observed:** Passed `file_paths="packages/tapps-core/.../dashboard.py,..."` (relative paths). Response: `files_validated: 0`, `summary: "No changed Python files found"`, `all_gates_passed: true`.

**Likely cause:** MCP server runs in Docker with `project_root=/workspace`. Host project path (`c:\cursor\TappMCP`) may not map to container paths. Or git diff in container doesn't see host changes. AGENTS.md mentions `TAPPS_MCP_HOST_PROJECT_ROOT` for path mapping but agent may not have set it.

**Impact:** Agent cannot verify changed files when server runs in Docker with different path space. Quality gate passes (no failures) but no actual validation ran.

**Recommendation:** See Epic 66.1 below.

### 2. No hint when file_paths provided but 0 validated

**Observed:** `validate_changed` returned 0 files without hint about path mapping or fallback.

**Recommendation:** When `file_paths` non-empty and `files_validated == 0`, add `path_hint` to response: "Explicit paths provided but none validated. Check TAPPS_MCP_PROJECT_ROOT / TAPPS_MCP_HOST_PROJECT_ROOT if using Docker."

### 3. Checklist auto_run validate_changed with 0 files

**Observed:** `auto_run_results.validate_changed.files_validated: 0` but `complete: true`. Checklist doesn't flag "validation ran but no files were checked."

**Recommendation:** Optional: when auto_run validate_changed returns 0 files validated, add `validation_note` to checklist: "Validation ran but 0 files validated. Consider tapps_quick_check on changed files."

---

## Recommendations → Epics

| Epic | Title | Priority | LOE |
|------|-------|----------|-----|
| [Epic 66.1](epics/EPIC-66.1-VALIDATE-CHANGED-PATH-HINTS.md) | validate_changed Path Mapping Hints | P2 | 2-3 days |
| [Epic 66.2](epics/EPIC-66.2-CHECKLIST-VALIDATION-NOTE.md) | Checklist Validation Note for 0 Files | P3 | 1-2 days |

---

## Tools Not Used (No Issues)

- **tapps_quick_check** — Would use as fallback for per-file validation; didn't need because checklist passed
- **tapps_memory** — Recommended but optional; didn't use for this session
- **tapps_score_file** — Per-file scoring; validate_changed covers batch
- **tapps_quality_gate** — Per-file gate; validate_changed covers batch
- **tapps_project_profile** — Would use for project context; session_start quick mode sufficient

---

## Summary

TappsMCP tools were mostly effective. Main gap: **validate_changed with explicit paths returned 0 files validated** in Docker/path-mismatch scenarios. Adding path hints and optional checklist validation notes would improve agent experience. Epic 66.1 and 66.2 capture these improvements.

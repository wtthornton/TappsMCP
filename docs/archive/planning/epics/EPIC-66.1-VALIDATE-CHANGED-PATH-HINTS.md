# Epic 66.1: validate_changed Path Mapping Hints (Tool UX)

**Status:** Complete
**Priority:** P2 | **LOE:** 2-3 days | **Source:** [TAPPS_MCP_TOOL_UX_REVIEW](../TAPPS_MCP_TOOL_UX_REVIEW.md)
**Dependencies:** Epic 1, 8 (core quality, pipeline)

## Problem Statement

When an agent passes explicit `file_paths` to `tapps_validate_changed` but the server validates 0 files (e.g., Docker path mismatch, project_root differs), the response only says "No changed Python files found." The agent has no hint that path mapping may be the cause or what to check.

**Context:** MCP server often runs in Docker with `project_root=/workspace`. Host paths (`c:\cursor\TappMCP\...`) may not map. AGENTS.md documents `TAPPS_MCP_HOST_PROJECT_ROOT` but agents may not discover this when validation returns empty.

## Stories

### Story 66.1.1: path_hint when file_paths provided but 0 validated

**Files:** `packages/tapps-mcp/src/tapps_mcp/tools/batch_validator.py`, `server_analysis_tools.py`

1. When `file_paths` is non-empty and `files_validated == 0`:
   - Add `path_hint` to response: "Explicit paths provided but none validated. If using Docker, check TAPPS_MCP_PROJECT_ROOT / TAPPS_MCP_HOST_PROJECT_ROOT for path mapping."
   - Or: "No files matched project scope. Check path mapping when server runs in container."
2. Add to `summary` or `next_steps` when applicable
3. Configurable: only include when `file_paths` explicitly passed (not auto-detect)

**Acceptance criteria:**
- Response includes path_hint when file_paths non-empty and files_validated=0
- Hint mentions TAPPS_MCP_PROJECT_ROOT, TAPPS_MCP_HOST_PROJECT_ROOT
- No hint when file_paths empty (auto-detect returned 0)

### Story 66.1.2: Suggest tapps_quick_check fallback

**Files:** `packages/tapps-mcp/src/tapps_mcp/server_analysis_tools.py`

1. When 0 files validated with explicit paths, add to `next_steps`:
   - "FALLBACK: Use tapps_quick_check on individual files to validate when paths don't map."
2. Or add `fallback_tool: "tapps_quick_check"` with short reason

**Acceptance criteria:**
- next_steps suggests tapps_quick_check when 0 validated with explicit paths

### Story 66.1.3: Documentation update

**Files:** AGENTS.md, docs/TAPPS_MCP_REQUIREMENTS.md

1. Document path mapping for Docker in troubleshooting
2. Link TAPPS_MCP_HOST_PROJECT_ROOT to validate_changed behavior

**Acceptance criteria:**
- AGENTS.md troubleshooting mentions path mapping
- validate_changed doc mentions path_hint

## Testing

- Unit: validate_changed returns path_hint when file_paths non-empty and 0 validated
- Unit: no path_hint when file_paths empty

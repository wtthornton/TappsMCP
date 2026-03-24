# Story 89.1: Add project_root to tapps_impact_analysis

<!-- docsmcp:start:metadata -->
**Epic:** [89 - Cross-Project Tool Parity](../EPIC-89-CROSS-PROJECT-TOOL-PARITY.md)
**Points:** 5
**Priority:** P1 - Critical
**Status:** Proposed

<!-- docsmcp:end:metadata -->

## User Story

As an agent using TappsMCP to review an external project, I need `tapps_impact_analysis` to accept a `project_root` parameter so that I can assess blast radius for files outside the MCP server's directory.

## Description

`tapps_impact_analysis` in `server_analysis_tools.py` (line 245) is the **only MCP tool** that does not accept a `project_root` override. The underlying `analyze_impact()` function in `project/impact_analyzer.py` already accepts `project_root: Path`, but the MCP wrapper hardcodes `settings.project_root` (line 264). This means:

1. Relative paths resolve against the MCP server's directory, not the target project
2. Absolute paths to external projects are rejected by `_validate_file_path_lazy()` with "Path outside project root"

The fix is straightforward: add the parameter to the MCP tool signature and thread it through.

## Tasks

- [ ] Add `project_root: str = ""` parameter to `tapps_impact_analysis()` signature
- [ ] When non-empty, resolve to `Path` and validate it's an existing directory
- [ ] Use custom root for `_validate_file_path_lazy()` call (or bypass with custom validation)
- [ ] Pass custom root to `analyze_impact()` and `build_impact_memory_context()`
- [ ] Update docstring with parameter documentation
- [ ] Add unit tests:
  - Default behavior (uses settings.project_root) unchanged
  - Explicit project_root resolves files correctly
  - File outside custom project_root returns proper error
  - Non-existent project_root returns proper error
- [ ] Update AGENTS.md tool documentation

## Acceptance Criteria

- [ ] `tapps_impact_analysis(file_path="lib/foo.sh", project_root="/path/to/external")` succeeds
- [ ] Default behavior (no project_root) is identical to current behavior
- [ ] Path security validation still applies against the custom root
- [ ] Error messages include the resolved project_root for diagnostics

## Definition of Done

Cross-project impact analysis works. Calling with an external project's root and file paths returns correct impact data including dependents, test files, and recommendations.

## Technical Notes

- Follow the pattern from `tapps_project_profile` which already handles `project_root` override
- `_validate_file_path_lazy()` may need an optional `root` parameter or a parallel validation path
- The `settings.project_root` fallback ensures backward compatibility

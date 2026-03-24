# Story 89.2: Include resolved project_root in session_start response

<!-- docsmcp:start:metadata -->
**Epic:** [89 - Cross-Project Tool Parity](../EPIC-89-CROSS-PROJECT-TOOL-PARITY.md)
**Points:** 2
**Priority:** P3 - Low
**Status:** Proposed

<!-- docsmcp:end:metadata -->

## User Story

As an agent connecting to TappsMCP, I need the session start response to include the resolved `project_root` so that I can verify the server is pointing at the correct repository before making further tool calls.

## Description

`tapps_session_start` returns server info, checkers, diagnostics, and workflow guidance, but does NOT include the resolved `project_root` path. Agents cannot verify which directory the server considers its project root without calling `tapps_project_profile` or another tool. This is a quick diagnostic win -- especially important in Docker or remote MCP setups where the project root may differ from expectations.

The field already exists in the data dict at line ~340 of `server.py` inside the `config` sub-object, but it's nested. Add it as a top-level field for easy access.

## Tasks

- [ ] Add `"project_root": str(settings.project_root)` to the top-level response dict in `tapps_session_start()`
- [ ] Ensure it appears in both `quick=True` and `quick=False` modes
- [ ] Add test verifying the field is present and matches `settings.project_root`
- [ ] Update output schema if applicable (`SessionStartResponse`)

## Acceptance Criteria

- [ ] Response includes `"project_root": "/path/to/resolved/root"` at top level
- [ ] Field is present in both quick and full modes
- [ ] Value matches the actual resolved project root

## Definition of Done

Agents can read `project_root` from session start and verify they're connected to the right project.

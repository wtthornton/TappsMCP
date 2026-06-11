# checklist.py: add task_type document profile

## What

Add checklist profile for PDF/HTML/document work mentioning judges and config validation.

## Where

- `packages/tapps-mcp/src/tapps_mcp/tools/checklist.py:152-293`
- `packages/tapps-mcp/src/tapps_mcp/tools/checklist_policy.py:1-100`

## Acceptance

- [ ] - [ ] task_type document added to TASK_TOOL_MAP and high/medium/low engagement maps
- [ ] Required includes tapps_validate_changed; recommended includes tapps_validate_config and tapps_lookup_docs
- [ ] TOOL_REASONS documents when to use document task_type
- [ ] Unit test asserts document policy resolves and unknown task_type no longer falls back for document

## Refs

docs/epics/EPIC-105.md

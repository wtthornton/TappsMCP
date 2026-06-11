# Epic 108: EPIC-108: MCP-environment judge reliability (uv-aware pytest)

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** High
**Estimated LOE:** S

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that validate_changed pytest judges pass when the consumer project uses uv-managed venvs, even though the MCP server process runs in an isolated tool environment without project pytest installed.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Make pytest judges resolve the consumer project virtualenv (uv run pytest, .venv/bin/python -m pytest) before falling back to bare python -m pytest, with optional command override in judge config.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

ReportLab production proved local uv run pytest passes but MCP validate_changed returns python -m pytest not found, causing judges_passed=false and training agents to ignore document gates. EPIC-104 shipped shell/when_changed/blocking integration but left pytest resolution MCP-host-only.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] - [ ] pytest judge tries uv run pytest
- [ ] then .venv/bin/python -m pytest
- [ ] then python -m pytest
- [ ] Judge runs with cwd=project_root and inherits env
- [ ] Optional command field on pytest judge overrides auto-resolution
- [ ] Unit tests mock subprocess and cover uv-first resolution
- [ ] ReportLab fixture: tapps_validate_changed pytest judge passes when uv run pytest passes locally

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 108.1 -- judge.py: uv-aware pytest resolution for MCP env

**Points:** 3

Describe what this story delivers...

**Tasks:**
- [ ] Implement judge.py: uv-aware pytest resolution for mcp env
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** judge.py: uv-aware pytest resolution for MCP env is implemented, tests pass, and documentation is updated.

---

### 108.2 -- document_judges.py: optional shell audit judge in discovered preset

**Points:** 2

Describe what this story delivers...

**Tasks:**
- [ ] Implement document_judges.py: optional shell audit judge in discovered preset
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** document_judges.py: optional shell audit judge in discovered preset is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Document architecture decisions for **EPIC-108: MCP-environment judge reliability (uv-aware pytest)**...

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- - Do not install pytest into the MCP server global env as the primary fix
- Do not embed ReportLab-specific pytest paths
- Do not auto-run full PDF build without when_changed

<!-- docsmcp:end:non-goals -->

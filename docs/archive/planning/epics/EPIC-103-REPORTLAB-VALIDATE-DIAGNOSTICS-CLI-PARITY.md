# ReportLab Consumer Feedback — Validate Diagnostics & CLI Parity

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P1
**Estimated LOE:** 2-3 weeks
**Dependencies:** Epic 74 (complete), Epic 53 (complete)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that consuming projects like ReportLab get actionable batch validation failures and reliable CLI fallbacks when MCP disconnects mid-session, without requiring per-file quick_check reruns or custom audit tooling.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Close the diagnostic depth gap in tapps_validate_changed, complete CLI/MCP parity for core validation tools, surface MCP recovery hints at session start, and optionally bridge PDF/report-studio domain quality into the TAPPS pipeline.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

ReportLab session feedback (grade B+): Tapps blocked real lint defects and confirmed a 17-file clean batch, but validate_changed failures showed only score/gate with no lint lines, CLI fallback commands were wrong (--file-paths, quick-check missing), MCP dropped mid-session with no recovery hint, and PDF-specific quality (thin pages, hyperlinks) required custom audit.py. Epic 74 addressed automation UX; Epic 53 added memory/lookup CLI but not validation tools.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] - validate_changed gate failures include top 3 lint/security findings per file
- CLI exposes quick-check and validate-changed --file-paths matching MCP contract
- session_start surfaces cli_fallback map and mid-session MCP recovery hint
- Optional report-studio judges preset documented and/or wired via .tapps-mcp.yaml
- search_first warms reportlab/pypdf for pinned consumer deps

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 0.1 -- validate_changed_output.py: top lint findings on gate fail

**Points:** TBD

Describe what this story delivers...

**Tasks:**
- [ ] Implement validate_changed_output.py: top lint findings on gate fail
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** validate_changed_output.py: top lint findings on gate fail is implemented, tests pass, and documentation is updated.

---

### 0.2 -- cli.py: quick-check + validate-changed --file-paths

**Points:** TBD

Describe what this story delivers...

**Tasks:**
- [ ] Implement cli.py: quick-check + validate-changed --file-paths
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** cli.py: quick-check + validate-changed --file-paths is implemented, tests pass, and documentation is updated.

---

### 0.3 -- session_start: MCP recovery + cli_fallback hints

**Points:** TBD

Describe what this story delivers...

**Tasks:**
- [ ] Implement session_start: mcp recovery + cli_fallback hints
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** session_start: MCP recovery + cli_fallback hints is implemented, tests pass, and documentation is updated.

---

### 0.4 -- validate_changed: failure_reason for score 0.0

**Points:** TBD

Describe what this story delivers...

**Tasks:**
- [ ] Implement validate_changed: failure_reason for score 0.0
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** validate_changed: failure_reason for score 0.0 is implemented, tests pass, and documentation is updated.

---

### 0.5 -- report-studio domain gate via judges preset

**Points:** TBD

Describe what this story delivers...

**Tasks:**
- [ ] Implement report-studio domain gate via judges preset
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** report-studio domain gate via judges preset is implemented, tests pass, and documentation is updated.

---

### 0.6 -- search_first warm reportlab/pypdf consumer deps

**Points:** TBD

Describe what this story delivers...

**Tasks:**
- [ ] Implement search_first warm reportlab/pypdf consumer deps
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** search_first warm reportlab/pypdf consumer deps is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Document architecture decisions for **ReportLab Consumer Feedback — Validate Diagnostics & CLI Parity**...

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Full PDF layout scoring inside tapps-mcp core; blocking memory saves; replacing report-studio audit CLI

<!-- docsmcp:end:non-goals -->

# Epic 105: Document consumer bootstrap (init, doctor, checklist)

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** High
**Estimated LOE:** M

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that document-shipping repos get working validate_changed judges and checklist guidance out of the box after tapps_init or tapps_upgrade — without hand-authoring .tapps-mcp.yaml for every consumer.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

When document tooling is detected (e.g. nlt-report-studio pin, reports/ directory), auto-merge discovered judge presets, report judge configuration in doctor, and add a document task_type to the checklist.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Today report-studio detection only adds a next_steps hint when validate_changed.judges is empty. Agents skip PDF audit gates unless manually prompted. Doctor shows installed status but not whether judges are configured.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] - [ ] tapps_init/tapps_upgrade merges discovered judge preset when document tooling detected
- [ ] Judge paths discovered via heuristics (reports/
- [ ] **/build-pdfs.mjs
- [ ] tests/test_pdf_audit.py) not hard-coded ReportLab layout
- [ ] tapps_doctor reports judges configured vs missing for document consumers
- [ ] task_type document exists in checklist with validate_changed
- [ ] validate_config
- [ ] lookup_docs guidance
- [ ] Fresh init on report-studio fixture consumer gets working blocking judges without manual YAML edits

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 105.1 -- init.py: auto-merge discovered judge preset on init upgrade

**Points:** 3

Describe what this story delivers...

**Tasks:**
- [ ] Implement init.py: auto-merge discovered judge preset on init upgrade
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** init.py: auto-merge discovered judge preset on init upgrade is implemented, tests pass, and documentation is updated.

---

### 105.2 -- doctor.py: report judge configuration status

**Points:** 2

Describe what this story delivers...

**Tasks:**
- [ ] Implement doctor.py: report judge configuration status
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** doctor.py: report judge configuration status is implemented, tests pass, and documentation is updated.

---

### 105.3 -- checklist.py: add task_type document profile

**Points:** 2

Describe what this story delivers...

**Tasks:**
- [ ] Implement checklist.py: add task_type document profile
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** checklist.py: add task_type document profile is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Document architecture decisions for **Document consumer bootstrap (init, doctor, checklist)**...

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- - Do not hard-code ReportLab-specific paths (apps/docs/scripts/build-pdfs.mjs) without discovery fallback
- Do not ship ReportLab pydantic schemas in core

<!-- docsmcp:end:non-goals -->

# Epic 107: Document config validation and agent guidance

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** Medium
**Estimated LOE:** M

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that agents working on document-shipping repos get schema validation for consumer YAML manifests, generic document-quality lookup_docs guidance, memory recall, and impact nudges — without embedding PDF logic in tapps-mcp core.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Ship pluggable validate_config for consumer brand/template manifests, a document-quality lookup_docs topic pack, optional document-builder memory profile, and impact_analysis rebuild-documents nudges.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Brand/template YAML affects shipped PDFs but is invisible to validate_changed. TROUBLESHOOTING references config_type yaml before core supports it. Agents lack generic guidance on PDF links, outlines, and thin pages. Impact analysis does not nudge document rebuilds when layout modules change.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] - [ ] validate_config supports consumer-registerable YAML manifest schemas (extension point
- [ ] not ReportLab-specific enums in core)
- [ ] TROUBLESHOOTING aligned with implemented config types
- [ ] lookup_docs document-quality topic returns generic PDF/HTML quality guidance
- [ ] memory.profile document-builder optional on init when document tooling detected
- [ ] tapps_impact_analysis nudges rebuild + suggested shell judge when reports/templates/brands paths change

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 107.1 -- validators: pluggable consumer YAML manifest validation

**Points:** 3

Describe what this story delivers...

**Tasks:**
- [ ] Implement validators: pluggable consumer yaml manifest validation
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** validators: pluggable consumer YAML manifest validation is implemented, tests pass, and documentation is updated.

---

### 107.2 -- session_start_helpers.py: document-quality lookup_docs pack

**Points:** 2

Describe what this story delivers...

**Tasks:**
- [ ] Implement session_start_helpers.py: document-quality lookup_docs pack
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** session_start_helpers.py: document-quality lookup_docs pack is implemented, tests pass, and documentation is updated.

---

### 107.3 -- init.py: document-builder memory profile preset

**Points:** 2

Describe what this story delivers...

**Tasks:**
- [ ] Implement init.py: document-builder memory profile preset
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** init.py: document-builder memory profile preset is implemented, tests pass, and documentation is updated.

---

### 107.4 -- server_analysis_tools.py: impact rebuild-documents nudge

**Points:** 2

Describe what this story delivers...

**Tasks:**
- [ ] Implement server_analysis_tools.py: impact rebuild-documents nudge
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** server_analysis_tools.py: impact rebuild-documents nudge is implemented, tests pass, and documentation is updated.

---

### 107.5 -- TROUBLESHOOTING.md: fix yaml config_type doc drift

**Points:** 1

Describe what this story delivers...

**Tasks:**
- [ ] Implement troubleshooting.md: fix yaml config_type doc drift
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** TROUBLESHOOTING.md: fix yaml config_type doc drift is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Document architecture decisions for **Document config validation and agent guidance**...

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- - Do not embed ReportLab-specific glossary.outward or audit_profile enums in tapps-core
- Do not run PDF rendering inside tapps-mcp

<!-- docsmcp:end:non-goals -->

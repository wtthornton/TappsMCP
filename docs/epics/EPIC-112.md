# Epic 112: Quality Tool Cross-Repo UX & Audit Hardening

<!-- docsmcp:start:metadata -->
**Status:** In Progress
**Linear:** TAP-3958
**Priority:** High
**Estimated LOE:** M

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that tapps-mcp quality tools work reliably when invoked from consumer repos (e.g. tapps-brain in Cursor), audit campaigns plan correctly on monorepos without manual graph_root, and doctor warnings translate into actionable defaults.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Fix cross-repo project_root handling in MCP analysis tools, auto-detect monorepo graph roots, tighten NLT tool-budget defaults, scope dependency scans to the target project, and close remaining EPIC-103 validate-diagnostics gaps.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

June 2026 audit run from tapps-brain workspace: tapps_audit_campaign and tapps_validate_changed ignored project_root (scoped to tapps-brain paths), tapps_report scored wrong repo, tapps_doctor warns 5 NLT servers / 29 eager tools, dependency_scan surfaced unrelated torch CVE from global env. CLI paths work; MCP cross-repo path mapping is the gap.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [x] MCP tools honor explicit project_root for scope, validate-changed paths, and report sampling
- [x] Audit campaign auto-sets graph_root on monorepo nested scopes (TAP-2035)
- [x] dependency_scan defaults to project lockfile/venv when project_root set
- [x] Doctor NLT partial-enablement resolves to ≤3 enabled servers or documented bundle default
- [x] Remaining EPIC-103 validate_changed diagnostic items shipped (TAP-3585; validate_changed_diagnostics.py)
- [x] Unit tests cover cross-repo project_root for audit_campaign and validate_changed

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 112.1 -- server_analysis_tools.py: honor project_root in MCP handlers

**Points:** 3

Fix tapps_audit_campaign, tapps_report, tapps_dead_code, tapps_dependency_scan to resolve paths against explicit project_root instead of MCP host project_root when parameter is set.

**Tasks:**
- [ ] Implement server_analysis_tools.py: honor project_root in mcp handlers
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** server_analysis_tools.py: honor project_root in MCP handlers is implemented, tests pass, and documentation is updated.

---

### 112.2 -- validate_changed.py: cross-repo explicit file_paths

**Points:** 2

When file_paths are repo-relative and project_root differs from host, map and validate files under the target root; surface clear path_hint on mismatch.

**Tasks:**
- [ ] Implement validate_changed.py: cross-repo explicit file_paths
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** validate_changed.py: cross-repo explicit file_paths is implemented, tests pass, and documentation is updated.

---

### 112.3 -- audit_chunker.py: auto-detect monorepo graph_root

**Points:** 3

When scope is nested under packages/*, infer graph_root from nearest pyproject/package root so import graph is non-empty without manual graph_root (TAP-2035).

**Tasks:**
- [ ] Implement audit_chunker.py: auto-detect monorepo graph_root
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** audit_chunker.py: auto-detect monorepo graph_root is implemented, tests pass, and documentation is updated.

---

### 112.4 -- pip_audit.py: scope scan to target project

**Points:** 2

When project_root is set, scan project venv/lockfile dependencies only; avoid unrelated global-site-package CVE noise (e.g. torch).

**Tasks:**
- [ ] Implement pip_audit.py: scope scan to target project
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** pip_audit.py: scope scan to target project is implemented, tests pass, and documentation is updated.

---

### 112.5 -- doctor.py: NLT tool-budget default bundle

**Points:** 2

Reduce default enabled nlt-* servers to developer bundle (code-quality + platform-admin) or emit auto-fix hint in doctor output.

**Tasks:**
- [ ] Implement doctor.py: nlt tool-budget default bundle
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** doctor.py: NLT tool-budget default bundle is implemented, tests pass, and documentation is updated.

---

### 112.6 -- validate_changed_diagnostics.py: close EPIC-103 gaps

**Points:** 3

Ship remaining validate_changed failure diagnostics from archived EPIC-103 (top findings per category, MCP recovery hints parity).

**Tasks:**
- [ ] Implement validate_changed_diagnostics.py: close epic-103 gaps
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** validate_changed_diagnostics.py: close EPIC-103 gaps is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Document architecture decisions for **Quality Tool Cross-Repo UX & Audit Hardening**...

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- - Graduating tapps_dead_code from Preview (separate epic)
- EPIC-111 dependency pin bumps
- Exposing fleet_audit as MCP tool

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:refs -->
## Refs

TAP-2035

<!-- docsmcp:end:refs -->

# Epic 104: Document-output gate orchestration (judges pipeline)

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** High
**Estimated LOE:** M

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that TappsMCP can gate shipped document OUTPUT quality (PDFs, HTML builds, audit CLIs) — not only Python source quality — using deterministic judges that agents and CI actually fail on.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Harden validate_changed judges so blocking failures fold into the primary pass/fail signal, surface visibly in summary output, and support generic shell/command gates with optional when_changed path filters.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

ReportLab production use proved code gates miss thin PDF pages, missing link annotations, and dropped --audit flags in prebuild scripts. Judges exist (pytest/grep/exists) but judges_passed is separate from all_gates_passed, blocking defaults to False, and CLI ignores judge failures. Shell judges are needed for consumer audit CLIs.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] - [ ] Blocking judge failure sets all_gates_passed and overall_passed to false
- [ ] judge_results appear in summary_rows and CLI validate-changed output
- [ ] shell/command judge runs subprocess with timeout and cwd=project_root
- [ ] when_changed globs skip judges when git diff does not touch matching paths
- [ ] Unit tests cover blocking integration
- [ ] shell exit codes
- [ ] and when_changed filtering

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 104.1 -- judge.py: wire blocking judges into all_gates_passed

**Points:** 3

Describe what this story delivers...

**Tasks:**
- [ ] Implement judge.py: wire blocking judges into all_gates_passed
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** judge.py: wire blocking judges into all_gates_passed is implemented, tests pass, and documentation is updated.

---

### 104.2 -- validate_changed_output.py: judge rows in summary_rows and CLI

**Points:** 2

Describe what this story delivers...

**Tasks:**
- [ ] Implement validate_changed_output.py: judge rows in summary_rows and cli
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** validate_changed_output.py: judge rows in summary_rows and CLI is implemented, tests pass, and documentation is updated.

---

### 104.3 -- judge.py: add shell command judge type

**Points:** 3

Describe what this story delivers...

**Tasks:**
- [ ] Implement judge.py: add shell command judge type
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** judge.py: add shell command judge type is implemented, tests pass, and documentation is updated.

---

### 104.4 -- judge.py: add when_changed glob filter for judges

**Points:** 2

Describe what this story delivers...

**Tasks:**
- [ ] Implement judge.py: add when_changed glob filter for judges
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** judge.py: add when_changed glob filter for judges is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Document architecture decisions for **Document-output gate orchestration (judges pipeline)**...

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- - Do not embed ReportLab or pypdf inside tapps-mcp scoring
- Do not auto-run full suite PDF build on every validate_changed without when_changed guards
- Do not replace consumer story modules with tapps-mcp templates

<!-- docsmcp:end:non-goals -->

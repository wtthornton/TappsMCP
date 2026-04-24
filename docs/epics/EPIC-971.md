# Epic 971: Fleet audit 3.3.0: sync consumers + close enforcement gaps

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P1 - High
**Estimated LOE:** ~1-2 weeks (1 developer)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that every tapps-mcp consumer runs the same enforcement surface (hooks, rules, skills, AGENTS.md) at the same shipped version, and so that the pipeline (session_start -> lookup_docs -> quick_check -> validate_changed -> checklist) is consistently enforced rather than relying on agent memory.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Bring all 5 known tapps-mcp consumer repos to parity with shipped version (currently 3.3.0) and close the hook/rule/skill enforcement gaps discovered in the 2026-04-24 fleet audit.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Audit found: tapps-mcp-workflow-fix is 3 majors stale at 2.10.1; source repo has self-stamp drift (AGENTS.md 3.2.4 vs shipped 3.3.0); the only blocking hook (PreToolUse) is missing from 3/5 consumers; PostToolUseFailure matcher wired with no handler; no composite /tapps-finish-task skill; git commits bypass validation.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] All 5 consumer repos report AGENTS.md stamp == current shipped version after upgrade
- [ ] Every shipped hook matcher has a corresponding script (no dead matchers)
- [ ] /tapps-finish-task skill exists and is referenced in AGENTS.md REQUIRED workflow at all engagement levels
- [ ] tapps_doctor grows checks for PreToolUse deployment and self-stamp drift
- [ ] Release checklist updated to require self-upgrade at every version bump

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 971.1 -- Fix source-repo self-stamp drift (3.2.4 -> 3.3.0)

**Points:** 1

Describe what this story delivers...

**Tasks:**
- [ ] Implement fix source-repo self-stamp drift (3.2.4 -> 3.3.0)
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Fix source-repo self-stamp drift (3.2.4 -> 3.3.0) is implemented, tests pass, and documentation is updated.

---

### 971.2 -- Upgrade stale consumer repos to 3.3.0

**Points:** 2

Describe what this story delivers...

**Tasks:**
- [ ] Implement upgrade stale consumer repos to 3.3.0
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Upgrade stale consumer repos to 3.3.0 is implemented, tests pass, and documentation is updated.

---

### 971.3 -- Ship PreToolUse hook to all consumers

**Points:** 3

Describe what this story delivers...

**Tasks:**
- [ ] Implement ship pretooluse hook to all consumers
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Ship PreToolUse hook to all consumers is implemented, tests pass, and documentation is updated.

---

### 971.4 -- Add UserPromptSubmit per-turn reminder hook

**Points:** 3

Describe what this story delivers...

**Tasks:**
- [ ] Implement add userpromptsubmit per-turn reminder hook
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Add UserPromptSubmit per-turn reminder hook is implemented, tests pass, and documentation is updated.

---

### 971.5 -- Ship PostToolUseFailure handler script

**Points:** 2

Describe what this story delivers...

**Tasks:**
- [ ] Implement ship posttoolusefailure handler script
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Ship PostToolUseFailure handler script is implemented, tests pass, and documentation is updated.

---

### 971.6 -- Ship /tapps-finish-task composite skill

**Points:** 3

Describe what this story delivers...

**Tasks:**
- [ ] Implement ship /tapps-finish-task composite skill
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Ship /tapps-finish-task composite skill is implemented, tests pass, and documentation is updated.

---

### 971.7 -- Decide landing model for security/test-quality/config-files rules

**Points:** 2

Describe what this story delivers...

**Tasks:**
- [ ] Implement decide landing model for security/test-quality/config-files rules
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Decide landing model for security/test-quality/config-files rules is implemented, tests pass, and documentation is updated.

---

### 971.8 -- Add git pre-commit/pre-push integration

**Points:** 5

Describe what this story delivers...

**Tasks:**
- [ ] Implement add git pre-commit/pre-push integration
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Add git pre-commit/pre-push integration is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Source of truth is packages/tapps-mcp/src/tapps_mcp/platform_hooks.py + platform_hook_templates.py + platform_skills.py + platform_rules.py
- Upgrade propagation relies on forced-overwrite for 100%-tapps-owned files and section-aware merge for AGENTS.md/CLAUDE.md
- Doctor checks live in packages/tapps-mcp/src/tapps_mcp/distribution/doctor.py

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Rewriting individual tapps-mcp tools
- Server-side (GitHub Actions) enforcement
- Changes to tapps-brain or docs-mcp beyond what init/upgrade already ship

<!-- docsmcp:end:non-goals -->

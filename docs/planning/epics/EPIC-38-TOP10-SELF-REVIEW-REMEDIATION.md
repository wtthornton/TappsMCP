# Epic 38: Top-10 Self-Review Remediation

**Status:** Complete
**Priority:** P1
**Estimated LOE:** ~1-2 weeks
**Dependencies:** None (all findings from self-review)
**Blocks:** None

---

## Goal

Remediate all gaps and quality issues found during TappsMCP's self-review of its top 10 features. The review used TappsMCP's own tools (score_file, quality_gate, security_scan, dead_code, research) across 11 quality dimensions, coordinated by a 5-agent team.

## Review Methodology

- **5 agents** ran in parallel: quality-scorer, security-auditor, infra-verifier, expert-checker, doc-reviewer
- **9 source files** scored with full mode + strict quality gate
- **11 dimensions** checked per feature: Score, Gate, Security, Dead Code, Skill, Agent, Hook, Rule, RAG, Tests, Docs
- **Preset:** strict (80+ overall, 8.0+ security, 7.5+ maintainability)

---

## Review Completeness Matrix

| Feature | Score | Gate | Security | Dead Code | Skill | Agent | Hook | Rule | RAG | Tests | Docs |
|---------|-------|------|----------|-----------|-------|-------|------|------|-----|-------|------|
| #1 quick_check | 71.2 | **FAIL** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS (17) | PASS |
| #2 validate_changed | 68.2 | **FAIL** | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS (21) | PASS |
| #3 research | 61.1 | **FAIL** | PASS | PASS | PASS | PASS | **GAP** | PARTIAL | PASS | PASS (32) | PASS |
| #4 pipeline | N/A | N/A | N/A | N/A | PARTIAL | PASS | N/A | **GAP** | PASS | PASS (218) | PASS |
| #5 init | 67.0 | **FAIL** | PASS | PASS | **GAP** | **GAP** | **GAP** | **GAP** | PASS | PASS (97) | PASS |
| #6 checklist | 74.9 | **FAIL** | PASS | PASS | PARTIAL | PARTIAL | **GAP** | PASS | PASS | PASS (42) | PASS |
| #7 engagement | 74.9 | **FAIL** | PASS | PASS | **GAP** | **GAP** | **GAP** | **GAP** | PASS | PASS (44) | PASS |
| #8 security_scan | 78.2 | **FAIL** | PASS | PASS | PASS | PASS | **GAP** | PARTIAL | PASS | PASS (15) | PASS |
| #9 memory | 68.1 | **FAIL** | PASS | PASS | PASS | PARTIAL | PARTIAL | PASS | PASS | PASS (586) | PASS |
| #10 score_file | 71.2 | **FAIL** | PASS | PASS | PASS | PASS | **GAP** | PASS | PASS | PASS (17) | PASS |

### Dimension Legend
- **Score**: Overall quality score from `tapps_score_file` (full mode)
- **Gate**: `tapps_quality_gate(preset="strict")` pass/fail
- **Security**: `tapps_security_scan` -- zero HIGH/CRITICAL
- **Dead Code**: `tapps_dead_code` -- zero items at >=80% confidence
- **Skill**: Dedicated `.claude/skills/` SKILL.md exists with correct `allowed-tools`
- **Agent**: `.claude/agents/` agent covers this feature
- **Hook**: Lifecycle hook references this tool
- **Rule**: `.claude/rules/` or `.cursor/rules/` references this feature
- **RAG**: Expert knowledge files exist in relevant domain
- **Tests**: Dedicated test count (threshold: >=15)
- **Docs**: AGENTS.md documents the feature accurately

---

## Summary of Findings

### What passed cleanly (no action needed)
- **Security**: All 9 files PASS. 3 LOW-severity informational findings only. Zero secrets.
- **Dead Code**: All 9 files CLEAN. Zero unused items at >=80% confidence.
- **RAG Knowledge**: All 10 features have excellent expert knowledge coverage (139 files, 17 domains). Expert responses scored 59-83% confidence.
- **Test Coverage**: All 10 features have >=15 tests. Range: 15-586 tests per feature.

### What needs remediation

#### Critical: Quality Gate Failures (all 9 files)
All 9 source files fail the strict quality gate. Scores range 61.1-78.2 (need 80+).

| File | Overall | Gap to 80 | Primary Blocker |
|------|---------|-----------|-----------------|
| server_metrics_tools.py | 61.1 | -18.9 | Maintainability 3.75, CC=25 (tapps_research) |
| scoring/scorer.py | 66.1 | -13.9 | Maintainability 1.82, large file (908 LOC) |
| pipeline/init.py | 67.0 | -13.0 | Maintainability 2.21, CC=19 (_run_server_verification) |
| server_memory_tools.py | 68.1 | -11.9 | Maintainability 5.14, CC=13 (tapps_memory) |
| server_pipeline_tools.py | 68.2 | -11.8 | Maintainability 2.90, CC=15 (tapps_validate_changed) |
| server.py | 68.7 | -11.3 | Maintainability 2.98, CC=15 (tapps_validate_config) |
| server_scoring_tools.py | 71.2 | -8.8 | Maintainability 3.81, CC=12 (_build_quick_check_data) |
| checklist.py | 74.9 | -5.1 | Maintainability 4.63, CC=16 (evaluate) |
| security_scanner.py | 78.2 | -1.8 | Maintainability 6.89 (closest to passing) |

**Root cause**: Maintainability is the universal bottleneck (scores 1.82-6.89/10, need 7.5+). Driven by large file sizes and high cyclomatic complexity in dispatch functions.

#### High: AGENTS.md Stale Claims
| Claim in AGENTS.md | Expected | Actual | Delta |
|---------------------|----------|--------|-------|
| "Seven SKILL.md files" | 7 | 8 | +1 (tapps-tool-reference added) |
| "Three agent definitions" | 3 | 4 | +1 (tapps-review-fixer added) |
| "7 hook scripts" | 7 | 9 | +2 (memory-capture, subagent-stop added) |

#### Medium: Infrastructure Gaps
| Feature | Missing Infrastructure |
|---------|----------------------|
| #5 `tapps_init` | No skill, no agent, no hook, no rule |
| #7 Engagement levels | No skill, no agent, no hook, no rule |
| #4 Pipeline workflow | No dedicated rule (only in Cursor pipeline.mdc) |
| #6 `tapps_checklist` | No dedicated skill (only in gate skill indirectly) |

#### Medium: Prompt Template Gaps
- `discover.md` does not reference `tapps_session_start` (references `tapps_project_profile` instead)
- `verify.md` does not mention `tapps_memory` for persisting learnings
- `overview.md` does not list `tapps_quick_check` in its overview table

#### Low: Minor Findings
- `tapps-pipeline.mdc` references CLI command `tapps-mcp validate-changed` which is undocumented
- `tapps-gate` skill instructions mention quality_gate but not checklist
- Untracked `tools/` directory at project root

---

## Stories

### 38.1 -- Fix AGENTS.md Count Inaccuracies
**Priority:** High | **Points:** 2

AGENTS.md has 3 stale numerical claims that will confuse consuming projects.

**Tasks:**
- Update skill count: "Seven SKILL.md files" -> "Eight SKILL.md files", add tapps-tool-reference to list
- Update agent count: "Three agent definitions" -> "Four agent definitions", add tapps-review-fixer
- Update hook count: "7 hook scripts" -> "9 hook scripts", add tapps-memory-capture.ps1 and tapps-subagent-stop.ps1
- Verify with `tapps_doctor`

**Definition of Done:**
- [ ] All numerical claims match filesystem
- [ ] AGENTS.md version bumped
- [ ] `tapps_doctor` shows no doc drift

---

### 38.2 -- Reduce Cyclomatic Complexity in Top-10 Source Files
**Priority:** High | **Points:** 13

All 9 source files fail the strict quality gate due to low maintainability scores driven by high cyclomatic complexity. This is the single biggest quality gap.

**High-CC functions to refactor:**

| Function | File | CC | Target CC |
|----------|------|-----|-----------|
| `tapps_research` | server_metrics_tools.py | 25 | <=10 |
| `_run_server_verification` | pipeline/init.py | 19 | <=10 |
| `evaluate` | tools/checklist.py | 16 | <=10 |
| `tapps_validate_changed` | server_pipeline_tools.py | 15 | <=10 |
| `tapps_validate_config` | server.py | 15 | <=10 |
| `tapps_memory` | server_memory_tools.py | 13 | <=10 |
| `run_security_scan` | security/security_scanner.py | 13 | <=10 |
| `_build_quick_check_data` | server_scoring_tools.py | 12 | <=10 |

**Tasks:**
- Extract helper functions from high-CC dispatch functions
- Split large files where >800 LOC (scorer.py, pipeline/init.py, server.py, server_pipeline_tools.py)
- Re-run `tapps_score_file` after each refactor to verify improvement
- Target: all files pass `tapps_quality_gate(preset="strict")`

**Definition of Done:**
- [ ] All 9 files score >=80 overall
- [ ] All 9 files pass strict quality gate
- [ ] No CC >10 in any function
- [ ] All existing tests pass
- [ ] No new ruff/mypy violations

---

### 38.3 -- Add Missing Skills for Init and Engagement
**Priority:** Medium | **Points:** 3

Features #5 (`tapps_init`) and #7 (engagement levels) have zero platform infrastructure.

**Tasks:**
- Create `tapps-init` skill in `.claude/skills/tapps-init/SKILL.md` and `.cursor/skills/tapps-init/SKILL.md`
  - `allowed-tools:` `mcp__tapps-mcp__tapps_init`, `mcp__tapps-mcp__tapps_doctor`
  - Instructions: bootstrap workflow, when to use init vs session_start
- Create `tapps-engagement` skill in `.claude/skills/tapps-engagement/SKILL.md` and `.cursor/skills/tapps-engagement/SKILL.md`
  - `allowed-tools:` `mcp__tapps-mcp__tapps_set_engagement_level`
  - Instructions: what each level means, when to change
- Consider adding `tapps-checklist` skill (feature #6 has only indirect coverage via tapps-gate)
- Update platform_skills.py generator to include new skills
- Verify skills appear in `tapps_upgrade --dry-run`

**Definition of Done:**
- [ ] New skills created in both `.claude/` and `.cursor/`
- [ ] Skills have correct `allowed-tools:` frontmatter
- [ ] `tapps_upgrade` regenerates them correctly
- [ ] AGENTS.md skill count updated

---

### 38.4 -- Fix Prompt Template Gaps
**Priority:** Medium | **Points:** 2

Three prompt templates have inaccurate or missing references.

**Tasks:**
- `discover.md`: Add explicit `tapps_session_start` reference (currently only mentions `tapps_project_profile`)
- `verify.md`: Add `tapps_memory` recommendation for persisting learnings
- `overview.md`: Add `tapps_quick_check` to the overview table
- Verify engagement variant templates (`agents_template_high.md`, etc.) are consistent

**Definition of Done:**
- [ ] discover.md references tapps_session_start as first action
- [ ] verify.md mentions tapps_memory for knowledge persistence
- [ ] overview.md includes tapps_quick_check
- [ ] All 3 engagement variants consistent

---

### 38.5 -- Expand Rule Coverage for Underserved Features
**Priority:** Low | **Points:** 3

Features #3 (research), #5 (init), #7 (engagement), #8 (security_scan), #10 (score_file) have no or partial rule coverage.

**Tasks:**
- Update `python-quality.md` (Claude) to mention `tapps_research` for library API lookups
- Update `tapps-python-quality.mdc` (Cursor) to mention `tapps_validate_changed`
- Consider adding `tapps_security_scan` mention to python quality rules
- Update platform_rules.py generator templates
- Verify rules regenerate correctly via `tapps_upgrade --dry-run`

**Definition of Done:**
- [ ] `python-quality.md` references research, security_scan
- [ ] `tapps-python-quality.mdc` references validate_changed
- [ ] Rule templates in platform_rules.py updated
- [ ] `tapps_upgrade` output matches

---

### 38.6 -- Add Hook Coverage for Score and Security Features
**Priority:** Low | **Points:** 2

Features #8 (`tapps_security_scan`) and #10 (`tapps_score_file`) have no lifecycle hooks. Feature #6 (`tapps_checklist`) has no hook reminding users before session end.

**Tasks:**
- Evaluate adding checklist reminder to `tapps-stop.ps1` (currently only reminds validate_changed)
- Consider whether security_scan and score_file hooks are warranted (may be too noisy)
- If adding, update `platform_hooks.py` and `platform_hook_templates.py`
- Update settings.json hook configuration

**Definition of Done:**
- [ ] tapps-stop.ps1 mentions checklist as final step
- [ ] Decision documented on whether security/score hooks are needed
- [ ] Hook templates updated if new hooks added

---

### 38.7 -- Resolve Untracked tools/ Directory
**Priority:** Low | **Points:** 1

`git status` shows `?? tools/` at project root. This should be tracked, gitignored, or removed.

**Tasks:**
- Determine purpose of `tools/` directory
- Either add to `.gitignore`, commit, or remove
- Clean up git status

**Definition of Done:**
- [ ] `tools/` directory resolved
- [ ] `git status` clean (no unexpected untracked files)

---

## Acceptance Criteria

- [ ] All 9 source files pass `tapps_quality_gate(preset="strict")`
- [ ] AGENTS.md claims match actual filesystem counts
- [ ] All 10 features have at least a skill or clear documentation for platform coverage
- [ ] Prompt templates reference correct tools for each pipeline stage
- [ ] `tapps_checklist(task_type="review")` passes
- [ ] All existing tests continue to pass
- [ ] No new security findings introduced

---

## Appendix: Agent Reports

### Security Audit (security-auditor)
- **Result:** 9/9 files PASS
- **Findings:** 3 LOW-severity only (B110 try-except-pass, B404/B603 subprocess -- mitigated by allowlist)
- **Dead code:** 0 items across all 9 files

### Quality Scoring (quality-scorer)
- **Result:** 9/9 files FAIL strict gate
- **Score range:** 61.1 (server_metrics_tools.py) to 78.2 (security_scanner.py)
- **Strengths:** Security 10/10, Structure 10/10, Linting 9.5-10, Type checking 10/10
- **Weakness:** Maintainability 1.82-6.89 (need 7.5+), Complexity 1.46-3.90

### Expert RAG Coverage (expert-checker)
- **Result:** 10/10 features have complete RAG coverage
- **Knowledge files:** 139 across 17 domains, all verified relevant
- **Expert response quality:** 59-83% confidence on top-3 feature queries
- **Recommendation:** Add git-diff patterns to ci-cd-patterns.md for better #2 retrieval

### Infrastructure Verification (infra-verifier)
- **Fully covered:** #1 quick_check, #2 validate_changed
- **Mostly covered:** #3, #4, #6, #8, #9, #10
- **Not covered:** #5 init, #7 engagement (zero platform artifacts)

### Documentation Review (doc-reviewer)
- **AGENTS.md:** 3 stale claims (skills 7->8, agents 3->4, hooks 7->9)
- **Prompt templates:** 3 gaps (discover.md, verify.md, overview.md)
- **Test coverage:** All 10 features have >=15 tests (range: 15-586)

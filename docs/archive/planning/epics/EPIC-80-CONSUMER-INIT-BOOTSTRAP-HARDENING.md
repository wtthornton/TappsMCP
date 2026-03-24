# Epic 80: Consumer Init & Bootstrap Hardening (tapps-mcp init)

<!-- docsmcp:start:metadata -->
**Status:** Complete
**Completed:** 2026-03-24
**Priority:** P0–P1 (hooks P0)
**Estimated LOE:** ~3–5 weeks (1 developer), parallelizable stories

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that teams bootstrapping TappsMCP from Windows, uv-run-from-checkout, and agent/non-interactive flows do not hit silent wrong-project roots, broken Claude hooks, or unusable MCP configs. Outcomes: init targets the intended consumer tree, generated hooks match settings, MCP server entries start reliably without assuming PATH, documentation matches real install paths, and doctor reports align with project-only setups.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Close the gaps captured in consumer feedback from a real Windows bootstrap (2026-03-24): critical hook/script mismatch, high-severity init and MCP-config footguns, and medium documentation and parity issues.

**Tech Stack:** TappMCP

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Consumer trust and support load depend on first-run success; broken hooks and wrong project_root are show-stoppers for adoption.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [x] Referenced Claude hook scripts exist after init/upgrade when settings reference them
- [x] Init never silently applies consumer bootstrap to the TappMCP package tree without explicit opt-in or warning
- [x] Non-interactive/CI init does not block on overwrite prompts; behavior and flags documented
- [x] Generated MCP config works when tapps-mcp is not on PATH (uv-run path or clear template)
- [x] Docs state canonical install paths; no misleading npx-only guidance
- [x] Optional docs-mcp multi-host parity documented or available via init flag
- [x] Doctor treats valid project-level MCP as sufficient where appropriate
- [x] Automated regression tests cover project root hooks and non-interactive init

<!-- docsmcp:end:acceptance-criteria -->

## Story documents (full)

| Story | Doc |
|-------|-----|
| 80.1 | [Fix PostToolUse hook scripts](EPIC-80/story-80.1-fix-posttooluse-hook-scripts-validate-report.md) |
| 80.2 | [Doctor: hook files exist](EPIC-80/story-80.2-doctor-verify-hook-files-exist.md) |
| 80.3 | [Init project-root guard](EPIC-80/story-80.3-init-project-root-self-bootstrap-guard.md) |
| 80.4 | [Non-interactive init / MCP overwrite](EPIC-80/story-80.4-noninteractive-init-mcp-overwrite.md) |
| 80.5 | [MCP PATH + uv-run fallback](EPIC-80/story-80.5-mcp-config-path-and-uv-fallback.md) |
| 80.6 | [Docs: canonical install](EPIC-80/story-80.6-docs-canonical-install-windows.md) |
| 80.7 | [docs-mcp parity across hosts](EPIC-80/story-80.7-docs-mcp-parity-across-hosts.md) |
| 80.8 | [TECH_STACK wrapper layouts](EPIC-80/story-80.8-tech-stack-low-confidence-wrappers.md) |
| 80.9 | [Doctor: project-only MCP](EPIC-80/story-80.9-doctor-project-only-mcp.md) |
| 80.10 | [Regression tests](EPIC-80/story-80.10-regression-tests-init-hooks-noninteractive.md) |

**Source feedback:** `C:\cursor\ralph\tapps-mcp-init-consumer-feedback.md` (2026-03-24).

<!-- docsmcp:start:stories -->
## Stories

### 80.1 -- Fix PostToolUse hook script generation (validate/report)

**Points:** 5

Add tapps-post-validate and tapps-post-report to script_event_map; ensure .ps1/.sh emitted.

**Tasks:**
- [x] Implement fix posttooluse hook script generation (validate/report)
- [x] Write unit tests
- [x] Update documentation

**Definition of Done:** Fix PostToolUse hook script generation (validate/report) is implemented, tests pass, and documentation is updated.

---

### 80.2 -- Doctor: verify hook files exist for settings references

**Points:** 3

Check .claude/settings* PostToolUse commands vs on-disk tapps-*.ps1/.sh.

**Tasks:**
- [x] Implement doctor: verify hook files exist for settings references
- [x] Write unit tests
- [x] Update documentation

**Definition of Done:** Doctor: verify hook files exist for settings references is implemented, tests pass, and documentation is updated.

---

### 80.3 -- Init default project root and TappMCP self-bootstrap guard

**Points:** 5

Warn/refuse when cwd resolves to packages/tapps-mcp; document uv --directory + --project-root.

**Tasks:**
- [x] Implement init default project root and tappmcp self-bootstrap guard
- [x] Write unit tests
- [x] Update documentation

**Definition of Done:** Init default project root and TappMCP self-bootstrap guard is implemented, tests pass, and documentation is updated.

---

### 80.4 -- Non-interactive init: MCP overwrite and env/TTY behavior

**Points:** 3

No hang without TTY; TAPPS_MCP_INIT_ASSUME_YES or skip with log; document --force.

**Tasks:**
- [x] Implement non-interactive init: mcp overwrite and env/tty behavior
- [x] Write unit tests
- [x] Update documentation

**Definition of Done:** Non-interactive init: MCP overwrite and env/TTY behavior is implemented, tests pass, and documentation is updated.

---

### 80.5 -- MCP config: PATH detection and uv-run fallback

**Points:** 5

Emit uv-based command when binary missing; preserve env vars on merge.

**Tasks:**
- [x] Implement mcp config: path detection and uv-run fallback
- [x] Write unit tests
- [x] Update documentation

**Definition of Done:** MCP config: PATH detection and uv-run fallback is implemented, tests pass, and documentation is updated.

---

### 80.6 -- Documentation: canonical install and Windows examples

**Points:** 3

Replace/fix npx guidance; copy-paste uv run init examples.

**Tasks:**
- [x] Implement documentation: canonical install and windows examples
- [x] Write unit tests
- [x] Update documentation

**Definition of Done:** Documentation: canonical install and Windows examples is implemented, tests pass, and documentation is updated.

---

### 80.7 -- docs-mcp parity across hosts

**Points:** 3

Full-stack snippet or --with-docs-mcp for Cursor/VS Code/Claude.

**Tasks:**
- [x] Implement docs-mcp parity across hosts
- [x] Write unit tests
- [x] Update documentation

**Definition of Done:** docs-mcp parity across hosts is implemented, tests pass, and documentation is updated.

---

### 80.8 -- TECH_STACK low-confidence wrapper layouts

**Points:** 2

Comment block and optional subfolder scan for detection.

**Tasks:**
- [x] Implement tech_stack low-confidence wrapper layouts
- [x] Write unit tests
- [x] Update documentation

**Definition of Done:** TECH_STACK low-confidence wrapper layouts is implemented, tests pass, and documentation is updated.

---

### 80.9 -- Doctor: user-scope Claude MCP vs project-only

**Points:** 2

Downgrade to warning when project .mcp.json is valid.

**Tasks:**
- [x] Implement doctor: user-scope claude mcp vs project-only
- [x] Write unit tests
- [x] Update documentation

**Definition of Done:** Doctor: user-scope Claude MCP vs project-only is implemented, tests pass, and documentation is updated.

---

### 80.10 -- Regression tests: init root hooks non-interactive

**Points:** 3

Tests from consumer appendix: dry-run paths hook files TTY.

**Tasks:**
- [x] Implement regression tests: init root hooks non-interactive
- [x] Write unit tests
- [x] Update documentation

**Definition of Done:** Regression tests: init root hooks non-interactive is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- Source feedback: C:\cursor\ralph\tapps-mcp-init-consumer-feedback.md
- Root cause cited: platform_hooks._filter_scripts script_event_map missing tapps-post-validate and tapps-post-report
- **Shipped (2026-03-24):** `platform_hooks.py` script_event_map; `setup_generator.py` (uv fallback, env merge, non-TTY overwrite, `--with-docs-mcp`, `is_tapps_mcp_package_layout`); `doctor.py` (`check_claude_hook_scripts`, project-only Claude user check); `init.py` TECH_STACK callout; CLI `--allow-package-init` / `--with-docs-mcp`; README + `docs/TROUBLESHOOTING.md`; tests in `test_setup_generator.py`, `test_doctor.py`, `test_claude_hooks_generation.py`, etc.

**Project Structure:** 48 packages, 789 modules, 3071 public APIs

### Expert Recommendations

- **Security Expert** (67%): *Senior application security architect specializing in OWASP, threat modeling, and secure-by-default design.*
- **Software Architecture Expert** (63%): *Principal software architect focused on clean architecture, domain-driven design, and evolutionary system design.*

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Publishing tapps-mcp to npm unless product decision made separately
- Rewriting all platform hook semantics beyond missing scripts

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:files-affected -->
## Files Affected

| File | Lines | Recent Commits | Public Symbols |
|------|-------|----------------|----------------|
| `packages/tapps-mcp/src/tapps_mcp/pipeline/platform_hooks.py` | 740 | - | 5 functions |
| `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py` | 1497 | 5 recent: 46c97bb chore: simplify Docker config, remove d... | 1 classes, 2 functions |

<!-- docsmcp:end:files-affected -->

<!-- docsmcp:start:related-epics -->
## Related Epics

- **EPIC-86-DOCUMENTATION-PLATFORM-INIT-INTEGRATION.md** -- references `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py`

<!-- docsmcp:end:related-epics -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Reduction in init-related issues | qualitative | support and issues | Post-release survey |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:stakeholders -->
## Stakeholders

| Role | Person | Responsibility |
|------|--------|----------------|
| Maintainers | TappsMCP core | Implementation |

<!-- docsmcp:end:stakeholders -->

<!-- docsmcp:start:references -->
## References

- Consumer feedback 2026-03-24|file://tapps-mcp-init-consumer-feedback.md

<!-- docsmcp:end:references -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 80.1: Fix PostToolUse hook script generation (validate/report)
2. Story 80.2: Doctor: verify hook files exist for settings references
3. Story 80.3: Init default project root and TappMCP self-bootstrap guard
4. Story 80.4: Non-interactive init: MCP overwrite and env/TTY behavior
5. Story 80.5: MCP config: PATH detection and uv-run fallback
6. Story 80.6: Documentation: canonical install and Windows examples
7. Story 80.7: docs-mcp parity across hosts
8. Story 80.8: TECH_STACK low-confidence wrapper layouts
9. Story 80.9: Doctor: user-scope Claude MCP vs project-only
10. Story 80.10: Regression tests: init root hooks non-interactive

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Behavior change for default project_root may surprise power users | Medium | Medium | Warning: Mitigation required - no automated recommendation available |
| UV path placeholders need clear docs for Windows vs POSIX | Medium | Low | Warning: Mitigation required - no automated recommendation available |

**Expert-Identified Risks:**

- **Security Expert**: *Senior application security architect specializing in OWASP, threat modeling, and secure-by-default design.*

<!-- docsmcp:end:risk-assessment -->

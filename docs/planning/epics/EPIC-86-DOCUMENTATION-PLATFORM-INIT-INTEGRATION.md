# Epic 86: Documentation Platform Init & Upgrade Integration

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P1 - High
**Estimated LOE:** ~2 weeks (1 developer)
**Dependencies:** Epic 46 (Docker MCP Distribution), Epic 82 (Diataxis), Epic 83 (llms.txt)
**Blocks:** All consuming projects benefit from this

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that consuming projects get documentation quality automation out of the box -- the same way they currently get code quality automation. Every `tapps_init` with DocsMCP detected will generate doc-focused agents, skills, and hooks that close the gap between code quality (fully automated) and doc quality (currently manual).

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

The `tapps_init` and `tapps_upgrade` pipeline generates documentation-focused agents, skills, hooks, and AGENTS.md sections for DocsMCP -- giving consuming projects automatic documentation quality automation alongside code quality, with a new docs-reviewer agent, docs-validate skill, and post-commit doc freshness hooks.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

TappsMCP init currently generates 4 code-quality agents, 8 skills, and 7 hooks -- but zero documentation-focused automation. Projects that use DocsMCP must manually configure their own doc workflows. By adding docs-focused agents, skills, and hooks to init/upgrade, every project gets documentation quality automation out of the box. This closes the gap between code quality (fully automated via init) and doc quality (currently manual).

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] New `tapps-docs-reviewer` agent definition generated during init (Claude and Cursor)
- [ ] New `tapps-docs-validator` agent definition generated during init
- [ ] New `tapps-docs-report` skill generated (invokes `docs_project_scan` + `docs_check_completeness`)
- [ ] New `tapps-docs-validate` skill generated (invokes `docs_check_drift` + `docs_check_freshness` + `docs_check_links` + `docs_check_diataxis`)
- [ ] New `tapps-docs-generate` skill generated (invokes `docs_generate_readme` + `docs_generate_llms_txt`)
- [ ] Post-commit hook added that checks doc freshness when markdown files change
- [ ] AGENTS.md template updated with DocsMCP tool reference section
- [ ] Init detects if docs-mcp MCP server is configured and conditionally generates doc automation
- [ ] Upgrade preserves existing doc automation config while updating to latest templates
- [ ] All new agents and skills follow existing naming and structure conventions

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### [86.1](EPIC-86/story-86.1-documentation-subagent-definitions.md) -- Documentation Subagent Definitions

**Points:** 5

Add two new subagent definitions to init/upgrade: `tapps-docs-reviewer` (reviews doc quality, runs validation suite) and `tapps-docs-validator` (pre-completion doc validation). Follow existing agent patterns.

**Tasks:**
- [ ] Create `tapps-docs-reviewer` agent template (sonnet, 20 maxTurns) with prompt: "Review documentation quality using docs_check_drift, docs_check_freshness, docs_check_completeness, docs_check_links, and docs_check_diataxis. Report findings with severity and recommendations."
- [ ] Create `tapps-docs-validator` agent template (haiku, 10 maxTurns) with prompt: "Run pre-completion doc validation on changed markdown files. Check freshness, links, and drift."
- [ ] Add to Claude Code `.claude/agents/` generation in `init.py`
- [ ] Add to Cursor `.cursor/agents/` generation in `init.py`
- [ ] Add to `upgrade.py` agent regeneration
- [ ] Add tests for agent file generation

**Definition of Done:** Documentation Subagent Definitions are implemented, tests pass, and documentation is updated.

---

### [86.2](EPIC-86/story-86.2-documentation-skills.md) -- Documentation Skills

**Points:** 5

Add three new skills: `tapps-docs-report` (project scan + completeness), `tapps-docs-validate` (drift + freshness + links + diataxis), `tapps-docs-generate` (readme + llms.txt). Follow existing skill patterns.

**Tasks:**
- [ ] Create `tapps-docs-report` SKILL.md template with allowed-tools: `mcp__docs-mcp__docs_project_scan mcp__docs-mcp__docs_check_completeness mcp__docs-mcp__docs_check_diataxis`
- [ ] Create `tapps-docs-validate` SKILL.md template with allowed-tools: `mcp__docs-mcp__docs_check_drift mcp__docs-mcp__docs_check_freshness mcp__docs-mcp__docs_check_links mcp__docs-mcp__docs_check_diataxis`
- [ ] Create `tapps-docs-generate` SKILL.md template with allowed-tools: `mcp__docs-mcp__docs_generate_readme mcp__docs-mcp__docs_generate_llms_txt mcp__docs-mcp__docs_generate_changelog`
- [ ] Add to Claude Code `.claude/skills/` generation in `init.py`
- [ ] Add to Cursor `.cursor/skills/` generation in `init.py`
- [ ] Add to `upgrade.py` skill regeneration
- [ ] Add tests for skill file generation

**Definition of Done:** Documentation Skills are implemented, tests pass, and documentation is updated.

---

### [86.3](EPIC-86/story-86.3-documentation-hooks.md) -- Documentation Hooks

**Points:** 5

Add documentation-aware hooks: post-commit hook checking doc freshness when `.md` files change, session-start hook that includes doc status in project context.

**Tasks:**
- [ ] Create `tapps-docs-freshness` hook script for Claude Code (triggers on PostToolUse/Write when file ends in `.md`)
- [ ] Create `tapps-docs-freshness` hook script for Cursor (triggers on afterFileEdit for `.md` files)
- [ ] Add hook to session-start to include doc completeness score when DocsMCP available
- [ ] Wire hooks into `init.py` hook generation
- [ ] Wire hooks into `upgrade.py` hook regeneration
- [ ] Add conditional generation based on docs-mcp availability
- [ ] Add tests for hook generation

**Definition of Done:** Documentation Hooks are implemented, tests pass, and documentation is updated.

---

### [86.4](EPIC-86/story-86.4-agentsmd-docsmcp-section.md) -- AGENTS.md DocsMCP Section

**Points:** 3

Add DocsMCP tool reference section to the AGENTS.md template with engagement-level variants. Include recommended doc workflow alongside code quality workflow.

**Tasks:**
- [ ] Add DocsMCP tools section to `agents_template_high.md` (mandatory doc validation before completion)
- [ ] Add DocsMCP tools section to `agents_template_medium.md` (recommended doc validation)
- [ ] Add DocsMCP tools section to `agents_template_low.md` (optional doc validation)
- [ ] Include doc validation in recommended workflow (7-step becomes 9-step: add "Doc Audit" and "Doc Generate" stages)
- [ ] Add domain hints for documentation expert consultation
- [ ] Add tests for AGENTS.md template rendering

**Definition of Done:** AGENTS.md DocsMCP Section is implemented, tests pass, and documentation is updated.

---

### [86.5](EPIC-86/story-86.5-init-detection-conditional-generation.md) -- Init Detection & Conditional Generation

**Points:** 3

Detect whether docs-mcp MCP server is configured and conditionally generate doc automation. Add `docs_automation` flag to `BootstrapConfig`.

**Tasks:**
- [ ] Add `docs_automation: bool = False` to `BootstrapConfig`
- [ ] Auto-detect docs-mcp in MCP config (`settings.json`, `mcp.json`, `.cursor/mcp.json`)
- [ ] When detected, set `docs_automation = True` automatically
- [ ] Conditionally generate doc agents, skills, hooks only when `docs_automation=True`
- [ ] Add `--docs-automation` CLI flag to `tapps-mcp init`
- [ ] Update dry-run output to show doc automation files
- [ ] Add tests for conditional generation (with and without docs-mcp)

**Definition of Done:** Init Detection & Conditional Generation is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- New agents follow existing pattern: YAML frontmatter + markdown prompt
- Skills follow agentskills.io spec with `allowed-tools` field (space-delimited for Claude, `mcp_tools` list for Cursor)
- Hooks follow existing pattern: bash scripts with config YAML
- Conditional generation prevents clutter in projects not using DocsMCP
- AGENTS.md template uses engagement-level variants (high/medium/low)
- Doc automation should be opt-in by default (`docs_automation=False`) with auto-enable when docs-mcp detected
- MCP server name detection should check for both `docs-mcp` and `MCP_DOCKER` (Docker variant)

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- DocsMCP server installation/configuration (handled by Epic 46)
- Modifying DocsMCP tools themselves
- CI/CD documentation pipeline (future epic)

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Doc agents generated | 0 | 2 | per init with docs-mcp detected |
| Doc skills generated | 0 | 3 | per init with docs-mcp detected |
| Doc hooks generated | 0 | 2 | per init with docs-mcp detected |
| AGENTS.md doc section | 0% | 100% | inits including DocsMCP tools |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 86.5: Init Detection & Conditional Generation (foundation)
2. Story 86.1: Documentation Subagent Definitions
3. Story 86.2: Documentation Skills
4. Story 86.3: Documentation Hooks
5. Story 86.4: AGENTS.md DocsMCP Section

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Too many agents/skills overwhelm AI context | Medium | Medium | Conditional generation; only add when docs-mcp detected |
| DocsMCP server unavailable in some environments | Medium | Medium | Graceful degradation; hooks check server availability before calling |

<!-- docsmcp:end:risk-assessment -->

<!-- docsmcp:start:files-affected -->
## Files Affected

| File | Story | Action |
|---|---|---|
| `packages/tapps-mcp/src/tapps_mcp/pipeline/init.py` | 86.1-86.5 | Add doc automation generation |
| `packages/tapps-mcp/src/tapps_mcp/pipeline/upgrade.py` | 86.1-86.3 | Add doc automation upgrade |
| `packages/tapps-mcp/src/tapps_mcp/prompts/agents_template_high.md` | 86.4 | Add DocsMCP section |
| `packages/tapps-mcp/src/tapps_mcp/prompts/agents_template_medium.md` | 86.4 | Add DocsMCP section |
| `packages/tapps-mcp/src/tapps_mcp/prompts/agents_template_low.md` | 86.4 | Add DocsMCP section |

<!-- docsmcp:end:files-affected -->

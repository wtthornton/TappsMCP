# Epic 105: Harden tapps-mcp / docs-mcp tool reliability

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P1 - High
**Estimated LOE:** ~1-2 weeks (1 developer)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are filing this epic so that tapps-mcp and docs-mcp stop silently failing or returning misleading success across consuming projects. A 30-day audit of 1,132 Claude Code sessions found 71 docs-mcp WRITE_ERROR failures, 19 tapps_memory store_init_failed errors from a stale `EmbeddingProvider` import, 38 sessions silently degraded by a tapps-brain 403, 90 calls to hallucinated tool names, and 2,099 raw `save_issue` calls bypassing the documented Linear template gate. Each finding is a discrete server bug or harness gap; together they make the platform feel unreliable to every consuming agent.</purpose_and_intent>
<parameter name="goal">Eliminate the top six reliability issues observed in production agent traffic across all consuming projects: the docs-mcp path-validator regression, the tapps_memory store init failures, the silent-degraded session_start, the missing PreToolUse Linear gate, the generator/validator template drift, and the hallucinated subagent tool names.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Describe how **Harden tapps-mcp / docs-mcp tool reliability** will change the system. What measurable outcome proves this epic is complete?

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Audit of ~1.2 GB of Claude Code session logs across 11 projects (tapps-mcp, docs-mcp, tapps-brain, AgentForge, ralph-claude-code, NLTlabsPE, Workstation, Alpaca, BambuStudio, Tapps-Command-Center, agent-monitor) shows agents routinely encounter these failures and either retry blindly, fall back to ungated paths, or proceed with degraded functionality. This blocks the platform from being a trusted dependency for downstream projects.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] docs-mcp generators succeed when invoked from any project_root regardless of server cwd
- [ ] tapps_memory store_init_failed rate drops to zero across all consuming projects
- [ ] tapps_session_start returns success=false (not silent degraded=true) when tapps-brain returns 403
- [ ] PreToolUse hook blocks raw save_issue calls without a prior docs_validate_linear_issue in the same turn cluster
- [ ] docs_generate_epic and docs_generate_story output passes docs_validate_linear_issue on first try with agent_ready=true
- [ ] hallucinated tool names tapps_consult_expert and tapps_research no longer surface as MCP tools and the tapps-mcp vs tapps-quality namespace overlap on tapps_lookup_docs is reconciled
- [ ] subagent system prompts include the same tapps_session_start obligation as the parent agent

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 105.1 -- fix(docs-mcp): docs_generate_* WRITE_ERROR when output path is outside server cwd

**Points:** 3

Path validator rejects absolute output paths when server was started from a different cwd; affects 12 docs_generate_* tools, 71 occurrences in 30-day audit

**Tasks:**
- [ ] Implement fix(docs-mcp): docs_generate_* write_error when output path is outside server cwd
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** fix(docs-mcp): docs_generate_* WRITE_ERROR when output path is outside server cwd is implemented, tests pass, and documentation is updated.

---

### 105.2 -- fix(tapps-core): tapps_memory store_init_failed — EmbeddingProvider import + None-store null-deref

**Points:** 3

tapps_brain.embeddings no longer exports EmbeddingProvider but tapps-core still imports it (19 hits); hive_status and search null-deref when store is None (2 hits)

**Tasks:**
- [ ] Implement fix(tapps-core): tapps_memory store_init_failed — embeddingprovider import + none-store null-deref
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** fix(tapps-core): tapps_memory store_init_failed — EmbeddingProvider import + None-store null-deref is implemented, tests pass, and documentation is updated.

---

### 105.3 -- feat(tapps-mcp): PreToolUse hook blocking save_issue without prior docs_validate_linear_issue

**Points:** 5

Land the soft-enforcement TODO from .claude/rules/linear-standards.md as a real PreToolUse hook; covers 912 raw create + 1,187 raw update violations across 30 days

**Tasks:**
- [ ] Implement feat(tapps-mcp): pretooluse hook blocking save_issue without prior docs_validate_linear_issue
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** feat(tapps-mcp): PreToolUse hook blocking save_issue without prior docs_validate_linear_issue is implemented, tests pass, and documentation is updated.

---

### 105.4 -- fix(tapps-mcp): session_start should fail loud on brain 403 instead of silent degraded:true

**Points:** 2

38 sessions silently degraded; one project retried session_start 18 times because the auth_probe failure was buried inside success=true response

**Tasks:**
- [ ] Implement fix(tapps-mcp): session_start should fail loud on brain 403 instead of silent degraded:true
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** fix(tapps-mcp): session_start should fail loud on brain 403 instead of silent degraded:true is implemented, tests pass, and documentation is updated.

---

### 105.5 -- fix(docs-mcp): docs_generate_epic and docs_generate_story output must satisfy docs_validate_linear_issue

**Points:** 2

3 audited cases where the validator immediately rejected generator output for missing acceptance checkbox or missing file:line anchor

**Tasks:**
- [ ] Implement fix(docs-mcp): docs_generate_epic and docs_generate_story output must satisfy docs_validate_linear_issue
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** fix(docs-mcp): docs_generate_epic and docs_generate_story output must satisfy docs_validate_linear_issue is implemented, tests pass, and documentation is updated.

---

### 105.6 -- chore(tapps-mcp): reconcile hallucinated tool names and tapps-mcp vs tapps-quality namespace overlap

**Points:** 3

90 calls to tapps_consult_expert and tapps_research as if they were MCP tools (they are skills); tapps_lookup_docs surfaced under both tapps-mcp and tapps-quality namespaces causing confusion in subagents

**Tasks:**
- [ ] Implement chore(tapps-mcp): reconcile hallucinated tool names and tapps-mcp vs tapps-quality namespace overlap
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** chore(tapps-mcp): reconcile hallucinated tool names and tapps-mcp vs tapps-quality namespace overlap is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- All findings come from grep over ~/.claude/projects/*.jsonl with --mtime -30 over 1481 session files; root-cause guesses are in the per-story descriptions. The Linear-gate TODO is already documented at the bottom of .claude/rules/linear-standards.md ('Currently soft-enforced'). The path validator lives at packages/docs-mcp/src/docs_mcp/security/ — the absolute path rejection logic needs to honor the project_root argument passed in the tool call rather than the server startup cwd.

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Adding observability or dashboards for these failures (separate epic)
- rewriting the generator templates beyond the validator-compatibility fix
- migrating tapps-brain to brain-as-a-service
- expanding the audit beyond Claude Code logs (e.g. Cursor or VSCode Copilot transcripts)

<!-- docsmcp:end:non-goals -->

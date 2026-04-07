# Epic 96: Session and Profiling Deduplication — Clean Tool Boundaries

<!-- docsmcp:start:metadata -->
**Status:** Completed (superseded by v2.0.0)
**Priority:** P2 - Medium
**Estimated LOE:** ~1 week (1 developer)
**Dependencies:** EPIC-94 (Expert Extraction), EPIC-95 (Memory Extraction), AgentForge EPIC-15 (Tool-Agent Boundary Cleanup — coordinated changes)

> **Closed (2026-04-07):** This epic is obsolete. The tools it targeted
> (`tapps_project_profile`, `tapps_get_canonical_persona`, `tapps_research`)
> were all deleted in v2.0.0 (EPIC-93 Phase 3, commit d651a14). Final tool
> count reduced to 24. No AgentForge coordination was needed — the tools
> were removed outright.

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that tapps-mcp stops duplicating session management, project profiling, persona lookup, feedback collection, and observability that AgentForge now owns. After EPIC-94 (expert extraction) and EPIC-95 (memory extraction), tapps-mcp should be a focused quality tooling server with ~15 deterministic tools. This epic removes the remaining orchestration-layer concerns and establishes clean integration points with AgentForge.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Remove or simplify tapps-mcp tools that duplicate AgentForge capabilities: session lifecycle, project profiling, persona lookup, feedback routing, and standalone observability dashboards. Expose lightweight integration hooks so AgentForge can pull metrics and profile data without both servers doing the same analysis independently.

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

After EPIC-94 and EPIC-95 land, tapps-mcp still has overlap: (1) tapps_session_start does project analysis that AgentForge also does, (2) tapps_project_profile duplicates docs_project_scan and AgentForge's own profiling, (3) tapps_get_canonical_persona duplicates AgentForge's agent catalog lookup, (4) tapps_feedback duplicates AgentForge's EPIC-9 feedback system, (5) tapps_dashboard/tapps_stats provide observability that should flow into AgentForge's unified dashboard. Cleaning these up completes the extraction and gives tapps-mcp a clear, focused identity: Python quality analysis tools.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] tapps_session_start simplified to checker discovery only (no project analysis or memory GC)
- [ ] tapps_project_profile deprecated in favor of AgentForge's unified profile endpoint
- [ ] tapps_get_canonical_persona deprecated — persona lookup routes through AgentForge catalog
- [ ] tapps_feedback forwards to AgentForge's feedback endpoint instead of local tracking
- [ ] tapps_dashboard and tapps_stats expose a metrics export API for AgentForge to consume
- [ ] tapps-mcp final tool inventory documented: ~15 focused quality tools
- [ ] No breaking changes to tool interfaces — deprecated tools still respond with redirect guidance

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 96.1 -- Simplify tapps_session_start

**Points:** 2

Strip tapps_session_start down to checker discovery (ruff, mypy, bandit, radon, vulture, pip-audit availability) and basic config loading. Remove project analysis, memory GC trigger, and diagnostic subsystem. These are now AgentForge's responsibility via its startup hook.

**Tasks:**
- [ ] Implement simplify tapps_session_start
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Simplify tapps_session_start is implemented, tests pass, and documentation is updated.

---

### 96.2 -- Deprecate tapps_project_profile

**Points:** 2

Mark tapps_project_profile as deprecated. Return a redirect response pointing to AgentForge's GET /project/profile. Keep the tool responding for backward compat during transition but stop running analysis internally.

**Tasks:**
- [ ] Implement deprecate tapps_project_profile
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Deprecate tapps_project_profile is implemented, tests pass, and documentation is updated.

---

### 96.3 -- Deprecate tapps_get_canonical_persona

**Points:** 1

Mark tapps_get_canonical_persona as deprecated. Persona/agent lookup is AgentForge's catalog responsibility. Return redirect guidance pointing to AgentForge's agent catalog endpoints.

**Tasks:**
- [ ] Implement deprecate tapps_get_canonical_persona
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Deprecate tapps_get_canonical_persona is implemented, tests pass, and documentation is updated.

---

### 96.4 -- Route tapps_feedback to AgentForge

**Points:** 2

Replace tapps_feedback's local tracking with a forwarding call to AgentForge's feedback endpoint (EPIC-9). Tool-level feedback (was this score helpful?) and domain feedback flow into AgentForge's unified RL training signal.

**Tasks:**
- [ ] Implement route tapps_feedback to agentforge
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Route tapps_feedback to AgentForge is implemented, tests pass, and documentation is updated.

---

### 96.5 -- Metrics Export API for Observability

**Points:** 3

Add a lightweight metrics export endpoint to tapps-mcp that returns raw tool usage data (call counts, durations, gate pass rates) in a structured format. AgentForge's consolidated dashboard (EPIC-15) consumes this instead of users calling tapps_dashboard and tapps_stats directly.

**Tasks:**
- [ ] Implement metrics export api for observability
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Metrics Export API for Observability is implemented, tests pass, and documentation is updated.

---

### 96.6 -- Final Tool Inventory and Documentation

**Points:** 2

Document the final tapps-mcp tool inventory post-extraction. Update AGENTS.md, CONFIG_REFERENCE.md, README, and CLAUDE.md consumer instructions. The final list should be ~15 tools: score_file, quick_check, quality_gate, validate_changed, security_scan, dead_code, dependency_scan, dependency_graph, impact_analysis, validate_config, lookup_docs, session_start (simplified), checklist, init, upgrade, doctor.

**Tasks:**
- [ ] Implement final tool inventory and documentation
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Final Tool Inventory and Documentation is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- This is the final cleanup epic — it should only be started after EPIC-94 and EPIC-95 are complete
- Deprecated tools should return HTTP 299 (non-standard) or include a deprecation header/field in the MCP response
- The metrics export API should use a simple JSON format that AgentForge can poll on a schedule
- tapps_checklist stays but may evolve into an AgentForge post-task hook in a future epic
- tapps_init and tapps_upgrade stay as infrastructure tools — they manage tapps-mcp's own generated files

### Cross-repo Coordination with AgentForge EPIC-15

AgentForge EPIC-15 research findings that affect this epic:

- **Transport question (BLOCKING for 96.2):** AgentForge story 15.1 needs to call tapps_project_profile from Python. Options: (a) subprocess to tapps-mcp CLI with JSON-RPC, (b) tapps-mcp HTTP endpoint, (c) direct Python import. **Resolve which transport before sprint planning.** If (b), story 96.2 should expose the HTTP endpoint rather than just deprecating. If (c), this may be a no-op.
- **Persona lookup already implemented:** AgentForge `GET /agents/{name}` already returns system_prompt (the canonical persona). Story 96.3 can be minimal — just a deprecation notice + redirect guidance. AgentForge EPIC-15.4 is nearly zero effort.
- **Feedback schema migration:** AgentForge EPIC-15.5 relaxes feedback table constraints: `invocation_id` becomes nullable, adds `tool_call_id TEXT` and `source TEXT DEFAULT 'agent'` columns. Story 96.4 (feedback routing) must know the AgentForge endpoint's schema — coordinate on POST /rl/feedback payload format. **This is a two-repo coordination blocker:** does tapps-mcp need a configurable webhook URL to POST tool-level feedback?
- **Skip OpenTelemetry:** AgentForge chose structured logging with session_id correlation over OTel (too heavy for solo-dev project). Story 96.5 (metrics export) should return structured JSON, not OTel spans. Include: tool call counts, durations, gate pass rates, error rates — all as flat JSON.
- **Facade justification test:** AgentForge EPIC-15.6 applies a test to each tool: does it add caching, scatter-gather, error isolation, or schema unification? Pure pass-through facades should be removed. Story 96.6 should apply the same test to each remaining tapps-mcp tool.
- **asyncio.gather error isolation:** AgentForge story 15.2 wraps tapps_session_start in `asyncio.gather` with error isolation so a failed MCP init never crashes startup. Story 96.1 (simplify session_start) should ensure the simplified version returns fast and never hangs.

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Removing quality analysis tools (scoring and security and dependency tools all stay)
- Merging tapps-mcp into AgentForge — they remain separate MCP servers
- Changing docs-mcp — its dedup is handled by AgentForge EPIC-15

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| All 7 acceptance criteria met | 0/7 | 7/7 | Checklist review |
| All 6 stories completed | 0/6 | 6/6 | Sprint board |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 96.1: Simplify tapps_session_start
2. Story 96.2: Deprecate tapps_project_profile
3. Story 96.3: Deprecate tapps_get_canonical_persona
4. Story 96.4: Route tapps_feedback to AgentForge
5. Story 96.5: Metrics Export API for Observability
6. Story 96.6: Final Tool Inventory and Documentation

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Backward compatibility: CLAUDE.md files in many projects reference these tools — need transition period | Medium | Medium | Deprecation notices run for 1+ release before removal. Tools still respond with redirect guidance during transition. Update consumer-facing AGENTS.md and UPGRADE_FOR_CONSUMERS.md. |
| AgentForge EPIC-15 must be coordinated — both repos changing integration boundaries simultaneously | Medium | Medium | Three specific coordination points: transport for profile (96.2↔15.1), feedback webhook schema (96.4↔15.5), tool inventory reconciliation (96.6↔15.6). Resolve all three before sprint. |
| Some users may prefer tapps-mcp's standalone observability — consider keeping tapps_stats as opt-in | Medium | Low | Keep tapps_stats responding but add a note that unified dashboard is available via AgentForge. Do not remove — just deprioritize. |
| Transport mechanism unresolved for profile endpoint | High | High | Must decide: HTTP endpoint, CLI subprocess, or Python import for AgentForge to call tapps_project_profile. Blocking prerequisite for story 96.2. |

<!-- docsmcp:end:risk-assessment -->

<!-- docsmcp:start:files-affected -->
## Files Affected

| File | Story | Action |
|---|---|---|
| Files will be determined during story refinement | - | - |

<!-- docsmcp:end:files-affected -->

<!-- docsmcp:start:performance-targets -->
## Performance Targets

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Test coverage | baseline | >= 80% | pytest --cov |
| Acceptance criteria pass rate | 0% | 100% | CI pipeline |
| Story completion rate | 0% | 100% | Sprint tracking |

<!-- docsmcp:end:performance-targets -->

# Epic 11: Memory-Aware Agents — tapps-brain Integration into Agent Execution

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P1 - High
**Estimated LOE:** ~1-2 weeks (1 developer)
**Dependencies:** EPIC-2 (hybrid matcher — see `EPIC-2-hybrid-matcher.md`), tapps-brain v2.1+ (code ready at commit c82937f, needs git tag)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that every agent automatically knows about and can use tapps-brain's tiered memory system (hive, group, personal scopes), enabling cross-agent knowledge sharing, execution learning capture, and memory-aware reasoning without manual per-agent configuration.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Make every AgentForge agent memory-aware by default: agents can recall shared knowledge via the hive before acting, save learnings after execution, and discover other agents through shared memory — all without modifying individual AGENT.md files.

**Tech Stack:** docs-mcp, Python >=3.12

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

Currently agents execute in complete isolation — each claude -p subprocess has zero knowledge of tapps-brain, the hive, other agents, or past executions. This means agents cannot learn from each other, cannot recall project-wide decisions, and repeatedly rediscover context that was already established. The hive memory system exists but no agent can use it.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] Every agent execution includes a memory preamble with tapps-brain instructions
- [ ] Brain recall is injected into system prompts before execution
- [ ] Successful executions are captured to brain with agent_scope=domain
- [ ] Agent catalog is published to hive on startup and agent CRUD
- [ ] memory_profile field on AgentConfig controls memory behavior (full/readonly/none)
- [ ] Agents can discover other agents through hive recall

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 11.1 -- Memory preamble template injection

**Points:** 5

Create a standard memory preamble (~200 tokens) that gets injected into every agent system prompt. Covers: how to interpret brain recall context, agent identity/name, available memory tiers, when to save vs recall. Add to compose_system_prompt as a new layer between USER.md and brain_context.

**Tasks:**
- [ ] Implement memory preamble template injection
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Memory preamble template injection is implemented, tests pass, and documentation is updated.

---

### 11.2 -- Agent catalog publishing to hive

**Points:** 3

On startup and after agent CRUD, publish a compact agent catalog to the hive with agent_scope=hive, tier=architectural. Each agent entry includes name, description, keywords, and capabilities. Brain recall naturally surfaces this when agents ask about related domains.

**Tasks:**
- [ ] Implement agent catalog publishing to hive
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Agent catalog publishing to hive is implemented, tests pass, and documentation is updated.

---

### 11.3 -- Execution capture to brain

**Points:** 3

After successful agent execution, save a structured summary to tapps-brain: prompt, agent used, result summary, cost, duration. Use agent_scope=domain so same-profile agents can learn from past executions. Gate on memory_profile != none.

**Tasks:**
- [ ] Implement execution capture to brain
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Execution capture to brain is implemented, tests pass, and documentation is updated.

---

### 11.4 -- memory_profile field on AgentConfig

**Points:** 2

Add memory_profile enum field to AgentConfig (full/readonly/none). full = recall + save, readonly = recall only, none = no memory. Default to full for approved agents. Update AGENT.md parser and frontmatter.

**Tasks:**
- [ ] Implement memory_profile field on agentconfig
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** memory_profile field on AgentConfig is implemented, tests pass, and documentation is updated.

---

### 11.5 -- Agent identity injection

**Points:** 2

Inject the executing agent's name, description, and role into the system prompt so it knows who it is in the multi-agent context. Include: 'You are the {name} agent. You are part of AgentForge, a multi-agent platform with {N} agents. Related agents you can suggest: {top-3 by embedding similarity}.'

**Tasks:**
- [ ] Implement agent identity injection
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Agent identity injection is implemented, tests pass, and documentation is updated.

---

### 11.6 -- Hive recall integration in compose_system_prompt

**Points:** 3

Extend brain recall to merge hive results. When brain_context is composed, query the hive for universal-scope memories relevant to the current prompt. Use hive_recall_weight=0.8. Budget: max 500 tokens from hive within the existing brain_recall_max_tokens budget.

**Tasks:**
- [ ] Implement hive recall integration in compose_system_prompt
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Hive recall integration in compose_system_prompt is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- tapps-brain Python API: MemoryStore.save(key
- value
- tier
- agent_scope) and HiveStore for shared state
- Agent preamble should be <400 tokens to avoid blowing the 4000-token system prompt budget
- Use agent_scope=domain for execution captures and agent_scope=hive for catalog
- memory_profile=none should skip both recall and save to avoid noise from test agents
- Existing brain bridge (BrainBridge in memory/brain.py) handles graceful degradation when tapps-brain is not installed

**Project Structure:** 6 packages, 63 modules, 230 public APIs

**Key Dependencies:** tapps-core>=1.0.0, mcp[cli]>=1.26.0,<2, click>=8.3.1,<9, jinja2>=3.1.6,<4, gitpython>=3.1.44,<4, pydantic>=2.12.5,<3, structlog>=25.5.0,<26, pyyaml>=6.0.3,<7

### Expert Recommendations

- **Software Architecture Expert** (63%): *Principal software architect focused on clean architecture, domain-driven design, and evolutionary system design.*
- **Security Expert** (63%): *Senior application security architect specializing in OWASP, threat modeling, and secure-by-default design.*

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- MCP-based inter-agent communication
- Real-time agent-to-agent delegation during execution
- Custom memory profiles per agent beyond the three tiers (full/readonly/none)

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:files-affected -->
## Files Affected

> **Note (2026-04-07):** Original paths referenced a `backend/` directory that does not
> exist in docs-mcp. Corrected to actual/planned docs-mcp paths below.

| File | Status | Purpose |
|------|--------|---------|
| `packages/docs-mcp/src/docs_mcp/agents/models.py` | New (EPIC-2) | AgentConfig with memory_profile field |
| `packages/docs-mcp/src/docs_mcp/agents/matcher.py` | New (EPIC-2) | HybridMatcher for agent discovery |
| `packages/docs-mcp/src/docs_mcp/agents/preamble.py` | New | Memory preamble template |
| `packages/docs-mcp/src/docs_mcp/agents/identity.py` | New | Agent identity injection |
| `packages/docs-mcp/src/docs_mcp/agents/catalog_publisher.py` | New | Hive catalog publishing |
| `packages/docs-mcp/src/docs_mcp/agents/execution_capture.py` | New | Post-execution brain save |

<!-- docsmcp:end:files-affected -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| All 6 acceptance criteria met | 0/6 | 6/6 | Checklist review |
| All 6 stories completed | 0/6 | 6/6 | Sprint board |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 11.1: Memory preamble template injection
2. Story 11.2: Agent catalog publishing to hive
3. Story 11.3: Execution capture to brain
4. Story 11.4: memory_profile field on AgentConfig
5. Story 11.5: Agent identity injection
6. Story 11.6: Hive recall integration in compose_system_prompt

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Token budget pressure — memory preamble + brain recall + catalog could exceed system_prompt_token_budget | Medium | High | Warning: Mitigation required - no automated recommendation available |
| Hive pollution from noisy agents saving low-value memories | Medium | Medium | Warning: Mitigation required - no automated recommendation available |
| Performance impact of hive queries on every request (~5-10ms acceptable) | Medium | Medium | Warning: Mitigation required - no automated recommendation available |
| tapps-brain optional dependency — must degrade gracefully when not installed | High | Medium | Warning: Mitigation required - no automated recommendation available |

**Expert-Identified Risks:**

- **Security Expert**: *Senior application security architect specializing in OWASP, threat modeling, and secure-by-default design.*

<!-- docsmcp:end:risk-assessment -->

<!-- docsmcp:start:performance-targets -->
## Performance Targets

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Test coverage | baseline | >= 80% | pytest --cov |
| Acceptance criteria pass rate | 0% | 100% | CI pipeline |
| Quality gate score | N/A | >= 70/100 | tapps_quality_gate |
| Story completion rate | 0% | 100% | Sprint tracking |

<!-- docsmcp:end:performance-targets -->

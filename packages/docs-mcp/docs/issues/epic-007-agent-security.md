# Epic 7: AI Agent Security

<!-- docsmcp:start:metadata -->
**Status:** Proposed
**Priority:** P0 - Critical
**Estimated LOE:** ~1-2 weeks (1 developer)

<!-- docsmcp:end:metadata -->

---

<!-- docsmcp:start:purpose-intent -->
## Purpose & Intent

We are doing this so that the AI agent operates under least-privilege with full audit logging, sandboxed execution, and human-in-the-loop controls for destructive actions.

<!-- docsmcp:end:purpose-intent -->

<!-- docsmcp:start:goal -->
## Goal

Implement sudoers allowlist, immutable audit logging, privilege tiers with human approval gates, and container sandboxing for the MCP server agent.

**Tech Stack:** docs-mcp, Python >=3.12

<!-- docsmcp:end:goal -->

<!-- docsmcp:start:motivation -->
## Motivation

The AI agent has subprocess execution, psutil, and Docker access. A compromised or misbehaving agent could modify firewall rules, delete containers, or escalate privileges. Defense-in-depth is critical.

<!-- docsmcp:end:motivation -->

<!-- docsmcp:start:acceptance-criteria -->
## Acceptance Criteria

- [ ] Agent sudo restricted to explicit command allowlist via sudoers
- [ ] Every tool invocation logged with timestamp and tool name and parameters and result
- [ ] Three privilege tiers enforced: read-only and operator and admin
- [ ] Admin-tier actions require human confirmation via Tailscale-auth webhook
- [ ] MCP server runs in gVisor-sandboxed container or AppArmor-confined process

<!-- docsmcp:end:acceptance-criteria -->

<!-- docsmcp:start:stories -->
## Stories

### 7.1 -- Implement Sudoers Allowlist

**Points:** 3

Create /etc/sudoers.d/server-agent with explicit NOPASSWD allowlist for each command the agent needs. Remove blanket sudo. Update run_command to validate against allowlist.

**Tasks:**
- [ ] Implement implement sudoers allowlist
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Implement Sudoers Allowlist is implemented, tests pass, and documentation is updated.

---

### 7.2 -- Add Immutable Audit Logging

**Points:** 3

Log every tool invocation to structured audit log via structlog. Include timestamp, tool name, parameters, result, and caller identity. Forward to Loki.

**Tasks:**
- [ ] Implement add immutable audit logging
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Add Immutable Audit Logging is implemented, tests pass, and documentation is updated.

---

### 7.3 -- Implement Privilege Tiers

**Points:** 5

Define three tiers: read-only (default), operator (restart services, update packages), admin (firewall, user management). Tools declare their tier. run_command enforces tier checks.

**Tasks:**
- [ ] Implement implement privilege tiers
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Implement Privilege Tiers is implemented, tests pass, and documentation is updated.

---

### 7.4 -- Add Human Approval Gate for Admin Actions

**Points:** 3

Admin-tier tool invocations pause and request human confirmation via Tailscale-authenticated webhook or MCP confirmation prompt before executing.

**Tasks:**
- [ ] Implement add human approval gate for admin actions
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Add Human Approval Gate for Admin Actions is implemented, tests pass, and documentation is updated.

---

### 7.5 -- Sandbox MCP Server Execution

**Points:** 3

Run MCP server process in gVisor container or under AppArmor profile. Restrict filesystem and network access to minimum required.

**Tasks:**
- [ ] Implement sandbox mcp server execution
- [ ] Write unit tests
- [ ] Update documentation

**Definition of Done:** Sandbox MCP Server Execution is implemented, tests pass, and documentation is updated.

---

<!-- docsmcp:end:stories -->

<!-- docsmcp:start:technical-notes -->
## Technical Notes

- This is the highest-priority security epic
- run_command in common/subprocess.py is the enforcement point
- OWASP Agentic Top 10 and Microsoft Agent Governance Toolkit are references
- See docs/recommendations-2026-server-hardening.md Section 9

**Project Structure:** 7 packages, 73 modules, 279 public APIs

**Key Dependencies:** tapps-core>=1.0.0, mcp[cli]>=1.26.0,<2, click>=8.3.1,<9, jinja2>=3.1.6,<4, gitpython>=3.1.44,<4, pydantic>=2.12.5,<3, structlog>=25.5.0,<26, pyyaml>=6.0.3,<7

<!-- docsmcp:end:technical-notes -->

<!-- docsmcp:start:non-goals -->
## Out of Scope / Future Considerations

- Define what is explicitly out of scope for **AI Agent Security**. Consider: Penetration testing

<!-- docsmcp:end:non-goals -->

<!-- docsmcp:start:success-metrics -->
## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| All 5 acceptance criteria met | 0/5 | 5/5 | Checklist review |
| All 5 stories completed | 0/5 | 5/5 | Sprint board |

<!-- docsmcp:end:success-metrics -->

<!-- docsmcp:start:implementation-order -->
## Implementation Order

1. Story 7.1: Implement Sudoers Allowlist
2. Story 7.2: Add Immutable Audit Logging
3. Story 7.3: Implement Privilege Tiers
4. Story 7.4: Add Human Approval Gate for Admin Actions
5. Story 7.5: Sandbox MCP Server Execution

<!-- docsmcp:end:implementation-order -->

<!-- docsmcp:start:risk-assessment -->
## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Authentication bypass if token validation incomplete | Medium | High | Warning: Mitigation required - no automated recommendation available |

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
| Story completion rate | 0% | 100% | Sprint tracking |

<!-- docsmcp:end:performance-targets -->

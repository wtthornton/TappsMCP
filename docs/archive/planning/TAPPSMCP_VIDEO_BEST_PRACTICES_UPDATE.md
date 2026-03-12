# TappMCP Init/Upgrade vs Claude Code Best Practices

**Source:** [Claude Code – 5 Features, 1 Decision Matrix](https://youtu.be/xuZ2meWfcKg)  
**Purpose:** Compare what the video recommends vs what TappMCP implements, with concrete update recommendations.

---

## 1. Video Decision Matrix (Summary)

| Feature | When to use | Context cost | Video rule |
|---------|-------------|--------------|------------|
| **CLAUDE.md** | Always-on standards | High (every session) | "Should Claude always know it?" |
| **Skills** | Task-specific expertise | Low (description only until invoked) | "Should Claude know it sometimes?" |
| **Sub-agents** | Delegation, isolation | Zero (own context) | "Should this run in isolation?" |
| **Hooks** | Event-driven automation | Zero (outside Claude's context) | "Should this happen automatically on events?" |
| **MCP servers** | External tools/data | Moderate (tools load on demand) | "Does Claude need external tools?" |

**Video mantra:** Don't force everything into one feature. Use all five; they compose.

---

## 2. What TappMCP Currently Implements

### 2.1 Always-on (CLAUDE.md / rules)

| Artifact | Content |
|----------|---------|
| AGENTS.md | Full tool reference, workflow, checklist, session start vs init, domain hints, recommended workflow |
| CLAUDE.md | Platform rules (claude-code) – TAPPS section |
| .cursor/rules/tapps-pipeline.md | Cursor rules – pipeline steps |

**Verdict:** AGENTS.md is dense and includes both always-on basics (session_start, workflow) and task-specific material (checklist per task type, tool tables). The video warns that everything in CLAUDE.md/always-on files consumes context every session.

### 2.2 Skills

| Skill | Description (stays in context) |
|-------|-------------------------------|
| tapps-score | Score a Python file across 7 categories |
| tapps-gate | Run quality gate, report pass/fail |
| tapps-validate | Validate all changed files before declaring complete |
| tapps-review-pipeline | Orchestrate parallel review-fix-validate |
| tapps-research | Expert + docs for technical questions |
| tapps-security | Security audit with vulnerability scanning |
| tapps-memory | Manage shared project memory |

**Verdict:** Skills are well-scoped as task-specific. The video says skills should include a short description (in context) and full instructions (on demand). TappMCP uses `description` and `allowed-tools` – aligned.

### 2.3 Sub-agents

| Sub-agent | Model | Tools | Notes |
|-----------|-------|-------|-------|
| tapps-reviewer | sonnet | Read, Glob, Grep | Review + score/gate |
| tapps-researcher | haiku | Read, Glob, Grep | Research, docs, experts |
| tapps-validator | haiku | Read, Glob, Grep | Pre-completion validation |
| tapps-review-fixer | sonnet | Read, Glob, Grep, Write, Edit, Bash | Worktree, parallel review |

**Verdict:** Matches video guidance: reviewer/researcher use read-only tools; fixer has write access in worktree. Model choice (haiku for research, sonnet for review) is reasonable.

### 2.4 Hooks (Claude Code)

| Event | Purpose |
|-------|---------|
| SessionStart (startup/resume) | Call tapps_session_start |
| SessionStart (compact) | Re-inject TappsMCP context after compaction |
| PostToolUse (Edit\|Write) | Remind tapps_quick_check after Python edits |
| Stop | Remind tapps_validate_changed (advisory) |
| TaskCompleted | Remind validation (advisory) |
| PreCompact | Backup scoring context |
| SubagentStart | Inject TappsMCP awareness |
| SubagentStop | Advise validation if subagent modified Python |
| SessionEnd | Session end |
| PostToolUseFailure (mcp__tapps-mcp__*) | On MCP tool failure |

**Verdict:** Uses multiple event types. Video mentions 15 event types and PreToolUse as a key pattern (e.g. block `rm -rf`). TappMCP does not add a PreToolUse destructive-command guard.

### 2.5 MCP

- Adds `tapps-mcp` to `.cursor/mcp.json`, `.mcp.json`, or `.vscode/mcp.json`
- Does not mention or configure other MCPs (GitHub, YouTube, Sentry, etc.)

**Verdict:** TappMCP is correctly treated as one MCP. The video stresses composing with other MCPs; docs could recommend adding complementary MCPs.

---

## 3. Gap Analysis

### 3.1 AGENTS.md / CLAUDE.md content placement

| Video guidance | TappMCP status |
|----------------|----------------|
| Always-on = minimal, non-negotiable rules | AGENTS.md is long and includes task-specific tables |
| Task-specific = skill | Checklist task types (feature, bugfix, etc.) are in AGENTS.md |
| "Everything in CLAUDE.md consumes context every session" | Large tool table and workflow text are always loaded |

### 3.2 Init flow

| Video guidance | TappMCP status |
|----------------|----------------|
| "Run init to bootstrap a claude.md. That's your foundation." | init creates AGENTS, rules, hooks, skills, sub-agents, MCP, CI, governance |
| "Then the next time you repeat yourself, write a skill." | No incremental path – full init only |
| Incremental adoption | No minimal vs full init |

### 3.3 Hierarchy

| Video guidance | TappMCP status |
|----------------|----------------|
| CLAUDE.md can be hierarchical (enterprise → personal → project → local) | Not documented or supported |
| "More specific always wins" | Not explained in docs |

### 3.4 Hooks

| Video guidance | TappMCP status |
|----------------|----------------|
| PreToolUse to block destructive commands (e.g. rm -rf) | Not implemented |
| Hooks can use LLM (prompt-based or agent-based) | Prompt-type hooks exist (Epic 36.4) but are opt-in |
| "Hooks fire on every matching event regardless of what you asked" | Implemented correctly for PostToolUse, Stop, etc. |

### 3.5 MCP composition

| Video guidance | TappMCP status |
|----------------|----------------|
| MCP tools compose with hooks, skills, sub-agents | Yes |
| Add other MCPs (GitHub, Sentry, Postgres, etc.) | Not documented or prompted |

---

## 4. Recommendations for TappMCP

### 4.1 Content placement (high priority)

| Action | Detail |
|--------|--------|
| **Slim AGENTS.md** | Move the full tool reference into a skill (`tapps-tool-reference`) or link to it. Keep in AGENTS.md: session_start first, workflow summary, memory/research guidance. |
| **Checklist as skill** | Consider a `tapps-checklist` skill with the task-type → tool mapping. Load only when user asks for checklist or declares work complete. |
| **Document rule** | Add to docs: "Put only non-negotiable, always-needed rules in CLAUDE.md / AGENTS.md. Put task-specific guidance in skills." |

### 4.2 Init options (medium priority)

| Action | Detail |
|--------|--------|
| **Minimal init** | Add `--minimal` or `create_agents_md=True, create_platform_rules=True` only (no hooks, skills, sub-agents, CI). |
| **Incremental upgrade** | Allow `tapps_upgrade` to add hooks/skills/sub-agents only when they are missing, without overwriting. |
| **Docs** | Document: "Start with minimal init, then add skills when you repeat yourself, hooks for guardrails, sub-agents for isolation." |

### 4.3 Hierarchy (low priority, docs only)

| Action | Detail |
|--------|--------|
| **Document hierarchy** | In docs, note that CLAUDE.md/rule files can be hierarchical (project vs personal) and that more specific wins. |

### 4.4 PreToolUse destructive-command guard (medium priority)

| Action | Detail |
|--------|--------|
| **Add PreToolUse hook** | Optional hook (high engagement or opt-in) that matches `Bash` and blocks commands containing `rm -rf`, `rm -fr`, `format c:`, etc. |
| **Configurable blocklist** | Support a simple config (e.g. `.tapps-mcp.yaml`) for patterns to block. |

### 4.5 MCP composition (low priority, docs only)

| Action | Detail |
|--------|--------|
| **Docs** | Add a section: "TappMCP works alongside other MCP servers. Consider adding GitHub, Sentry, YouTube, or database MCPs for your workflow." |
| **Init wizard** | Optionally ask: "Add other MCPs? (e.g. GitHub, YouTube)" and link to setup instructions. |

### 4.6 Skills best practices (already aligned)

| Action | Detail |
|--------|--------|
| **Keep skill descriptions short** | Current descriptions are one-line – good. |
| **Ensure full content loads on demand** | SKILL.md content is loaded when skill activates – aligned. |

### 4.7 Upgrade behavior

| Action | Detail |
|--------|--------|
| **Preserve custom content** | upgrade already preserves custom command paths; ensure it never overwrites user edits in AGENTS.md custom sections. |
| **Version-aware upgrades** | upgrade already does version checks; continue to be conservative about overwriting. |

---

## 5. Implementation Priorities

| Priority | Item | Effort | Impact |
|----------|------|--------|--------|
| P1 | Slim AGENTS.md, move tool table to skill or link | Medium | High (context cost) |
| P2 | Add minimal init mode | Low | Medium |
| P3 | Add PreToolUse destructive-command guard (opt-in) | Medium | Medium |
| P4 | Document hierarchy, MCP composition | Low | Low |
| P5 | Init wizard question: add other MCPs? | Low | Low |

---

## 6. Video Quotes (Reference)

- "That file loads into every conversation. Your PR review checklist is sitting in context when you're debugging a memory leak."
- "Claude.md is hierarchical. More specific always wins."
- "Skills load on demand only when relevant. Minimal context cost."
- "The rule is simple. Projectwide standards that always apply → claude.md. Task specific expertise that's only relevant sometimes → skills."
- "Sub-agents run in their own context window. Hooks run outside Claude's context entirely."
- "If it should happen automatically on every matching event, use a hook."
- "Don't force everything into one feature. You can use all five at the same time. They compose."
- "Open your project, run init to bootstrap a claude.md. That's your foundation. Then the next time you repeat yourself, write a skill."

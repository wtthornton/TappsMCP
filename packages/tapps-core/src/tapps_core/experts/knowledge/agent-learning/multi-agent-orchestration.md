---
last_reviewed: 2026-04-06
---

# Multi-Agent Orchestration Patterns

## Overview

Multi-agent systems coordinate multiple AI agents to achieve complex goals
that exceed a single agent's context, capability, or reliability. This guide
covers orchestration topologies, memory sharing strategies, prompt composition,
and failure handling for agent teams.

## Orchestration Topologies

### Hub-and-Spoke (Coordinator Pattern)

A central coordinator agent delegates tasks to specialist agents and
aggregates results.

```
Coordinator
  |-- Researcher (read-only exploration)
  |-- Implementer (code changes)
  |-- Reviewer (quality validation)
  |-- Tester (test execution)
```

**When to use:** Clear task decomposition, sequential dependencies, need
for quality gates between steps.

**Trade-offs:**
- Coordinator becomes a bottleneck and single point of failure
- Easy to reason about; clear ownership of each subtask
- Coordinator's context window limits the complexity it can manage

### Peer-to-Peer (Swarm Pattern)

Agents communicate directly, sharing state through a shared memory store
rather than a central coordinator.

**When to use:** Independent subtasks, embarrassingly parallel workloads,
exploratory research with multiple angles.

**Trade-offs:**
- No single bottleneck; scales horizontally
- Harder to debug; non-deterministic execution order
- Requires robust conflict resolution for shared state

### Pipeline (Assembly Line)

Each agent handles one stage, passing output to the next via a shared
artifact (file, message queue, or memory entry).

```
Plan -> Implement -> Review -> Test -> Ship
```

**When to use:** Well-defined stages, each requiring different expertise
or tool access.

**Trade-offs:**
- Simple mental model; each stage is independently testable
- Latency is additive; blocked by the slowest stage
- Rework loops (review -> implement) add complexity

### Hierarchical (Tree Pattern)

Agents are organized in a tree where each level can spawn child agents
for subtasks, recursively.

**When to use:** Large-scale tasks that decompose naturally into
sub-problems (e.g., "refactor all modules" -> per-module agents).

**Trade-offs:**
- Natural fit for divide-and-conquer problems
- Deep trees increase latency and context loss
- Parent must synthesize results from children

## Memory Sharing Strategies

### Shared Memory Store (Recommended)

All agents read/write to a centralized memory store (e.g., tapps_memory)
with scope-based visibility.

```python
# Agent 1 saves a decision
await tapps_memory(
    action="save",
    key="decision.api-versioning",
    value="Using URL-based versioning (/api/v2/)",
    tier="architectural",
    scope="project",
)

# Agent 2 checks before making related decisions
result = await tapps_memory(action="search", query="api versioning")
```

**Key principles:**
- **Scope isolation:** Use `session` scope for agent-local scratch,
  `project` scope for shared decisions
- **Read-before-write:** Always search for existing decisions before
  saving new ones to avoid contradictions
- **Source attribution:** Tag memories with `source_agent` so
  conflicts can be traced

### Memory Injection (Context Priming)

Inject relevant memories into an agent's context before it starts work,
reducing the need for the agent to search explicitly.

```python
# Before spawning a subagent, retrieve relevant memories
memories = await tapps_memory(action="search", query=task_description)

# Include in the agent's prompt
agent_prompt = f"""
## Prior Decisions (from project memory)
{format_memories(memories)}

## Your Task
{task_description}
"""
```

**When to use:** When subagents have limited tool access or when
prior decisions are critical to avoid conflicting work.

### Hive Memory Pattern

Agents contribute observations to a shared "hive mind" that consolidates
patterns and surfaces consensus.

```python
# Each agent saves observations during work
await tapps_memory(
    action="save",
    key=f"observation.{agent_id}.{topic}",
    value=observation,
    tier="context",
    scope="project",
    tags=["hive", topic],
)

# Consolidation step merges overlapping observations
await tapps_memory(action="consolidate")
```

**When to use:** Exploratory tasks where multiple agents investigate
the same codebase from different angles.

### Federation (Cross-Project Memory)

Share knowledge between related projects using `scope="shared"`.

**When to use:** Monorepo environments, microservice ecosystems,
or when patterns discovered in one project apply to others.

**Caution:** Shared memories need higher confidence thresholds
to avoid polluting unrelated projects.

## Prompt Composition for Agent Teams

### Task Framing

```markdown
## Context
You are the [role] agent in a team of [N] agents working on [goal].

## What Other Agents Have Done
[Inject memories or summaries from prior agents]

## Your Specific Task
[Precise, bounded task description]

## Constraints
- Do NOT modify files outside [scope]
- Save decisions to memory with key prefix "[domain]."
- If blocked, save a memory with tag "blocked" and stop
```

### Handoff Protocol

When one agent completes and another must continue:

1. **Save state:** Agent A saves its progress, decisions, and any
   unresolved issues to memory
2. **Summary artifact:** Agent A writes a concise handoff note
   (what was done, what remains, any gotchas)
3. **Context injection:** Agent B's prompt includes the handoff note
   and relevant memories

### Conflict Resolution

When agents make contradicting decisions:

1. **Detection:** Memory system flags contradictions via confidence
   penalties and `contradicted=True` markers
2. **Resolution priority:** Human > higher-confidence > newer
   (configurable per tier)
3. **Escalation:** If both agents have similar confidence, flag for
   human review rather than auto-resolving

## Failure Handling

### Agent Failure Recovery

```python
# Pattern: retry with narrower scope on failure
try:
    result = await run_agent(task=full_task)
except AgentFailure:
    # Decompose into smaller subtasks
    subtasks = decompose(full_task)
    results = [await run_agent(task=st) for st in subtasks]
    result = merge(results)
```

### Deadlock Prevention

- **Timeout all agent operations** — no agent should run indefinitely
- **Avoid circular dependencies** — agent A waiting on agent B
  waiting on agent A
- **Idempotent operations** — agents should be safe to retry

### Graceful Degradation

When a specialist agent is unavailable:
1. Fall back to a general-purpose agent with expert consultation
2. Save the limitation as a memory for future sessions
3. Flag the degradation in output so the user knows

## Anti-Patterns

### Chatty Agents

Agents that communicate every small decision through shared memory
create noise. **Fix:** Only save architectural decisions and
blocking issues; keep tactical decisions local.

### God Coordinator

A coordinator that micromanages every step, passing full context
to each subagent. **Fix:** Give subagents bounded autonomy with
clear success criteria; let them make local decisions.

### Stale Context

Injecting outdated memories that no longer reflect the codebase.
**Fix:** Check memory freshness (last_accessed, confidence decay)
before injection; verify file paths still exist.

### No Quality Gate

Agents that produce output without validation. **Fix:** Every
agent pipeline should include a validation step (e.g.,
tapps_validate_changed) before declaring work complete.

## Quick Reference

| Topology | Best For | Memory Strategy |
|---|---|---|
| Hub-and-spoke | Sequential tasks with dependencies | Coordinator manages memory |
| Peer-to-peer | Parallel independent work | Shared store with conflict detection |
| Pipeline | Clear stage progression | Artifact passing + memory for decisions |
| Hierarchical | Recursive decomposition | Scoped memory per subtree |

| Memory Pattern | Latency | Complexity | Best For |
|---|---|---|---|
| Shared store | Low | Low | General-purpose coordination |
| Injection | None (pre-loaded) | Medium | Subagent priming |
| Hive | Medium | High | Exploratory consensus |
| Federation | High | High | Cross-project knowledge |

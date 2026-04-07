---
last_reviewed: 2026-04-06
---

# Agent System Architecture

## Overview

Designing systems where AI agents are first-class components requires
architectural decisions about agent boundaries, communication, state
management, and observability. This guide covers patterns for integrating
agents into software architecture.

## Agent as a Service Boundary

### When Agents Replace Services

Traditional microservices handle deterministic request/response flows.
Agents handle tasks requiring reasoning, multi-step planning, or
tool orchestration. Use agents when:

- The task requires dynamic tool selection based on context
- Multi-step workflows where later steps depend on earlier reasoning
- The "API" is natural language (user requests, support tickets)

### Agent Interface Contracts

Agents need contracts just like APIs:

```python
@dataclass
class AgentTask:
    """Input contract for an agent."""
    goal: str                    # What to achieve (natural language)
    constraints: list[str]       # Boundaries (files, time, scope)
    context: dict[str, Any]      # Injected state (memories, config)
    tools_available: list[str]   # Which tools the agent can call
    success_criteria: str        # How to know when done

@dataclass
class AgentResult:
    """Output contract from an agent."""
    status: Literal["success", "partial", "failed", "blocked"]
    artifacts: list[Path]        # Files created/modified
    decisions: list[str]         # Key decisions made (for memory)
    blockers: list[str]          # Unresolved issues
    metrics: dict[str, float]    # Duration, token usage, tool calls
```

## State Management

### Agent State Machine

```
IDLE -> PLANNING -> EXECUTING -> REVIEWING -> COMPLETE
                      |              |
                      v              v
                   BLOCKED       FAILED
                      |
                      v
                   WAITING (for human/other agent)
```

### Persistent vs Ephemeral State

| State Type | Storage | Lifetime | Example |
|---|---|---|---|
| Task context | Agent memory (session scope) | Single task | Current file being edited |
| Decisions | Shared memory (project scope) | Cross-session | "We use URL versioning" |
| Learned patterns | Memory store (pattern tier) | Weeks-months | "This codebase prefers X" |
| Architecture | Memory store (architectural tier) | Months-years | "Auth uses OAuth2 PKCE" |

### Checkpoint Pattern

For long-running agent tasks, save checkpoints so work can resume
after interruptions:

```python
# Save progress after each major step
await memory.save(
    key=f"checkpoint.{task_id}",
    value=json.dumps({
        "step": current_step,
        "completed_files": completed,
        "remaining_files": remaining,
    }),
    tier="context",
    scope="session",
)
```

## Communication Patterns

### Tool-Mediated Communication

Agents communicate through shared tools (memory, file system, MCP)
rather than direct messaging. This provides:

- **Auditability** — every interaction is a tool call with input/output
- **Decoupling** — agents don't need to know about each other
- **Persistence** — state survives agent restarts

### Event-Driven Agent Coordination

Use file-system markers or memory entries as events:

```python
# Agent A signals completion
await memory.save(key="event.scoring-complete", value="all files passed")

# Agent B watches for the event
result = await memory.get(key="event.scoring-complete")
if result:
    # Proceed with deployment
    ...
```

### Structured Handoff

When one agent passes work to another:

1. **Artifact:** The work product (modified files, generated code)
2. **Manifest:** What was done, what remains, any caveats
3. **Memories:** Key decisions saved to shared memory
4. **Validation state:** Whether quality checks passed

## Observability

### Agent Metrics

Track per-agent:
- **Token usage** — input/output tokens per task
- **Tool call count** — how many tools were called
- **Duration** — wall-clock time per task
- **Success rate** — tasks completed vs failed
- **Rework rate** — how often review sends back to implementation

### Tracing Agent Workflows

Each agent task should carry a trace ID that propagates through
tool calls, memory operations, and subagent spawns. This enables
end-to-end debugging of multi-agent workflows.

## Security Considerations

### Principle of Least Privilege

Each agent should only have access to the tools and files it needs:

- **Read-only agents** (researchers, reviewers) should not have Edit/Write
- **Scoped agents** should be restricted to specific directories
- **Destructive tools** (rm, git push) should require explicit opt-in

### Memory Safety

- **RAG safety checks** on all memory writes prevent prompt injection
- **Confidence-based trust** — agent-created memories start at 0.6,
  human-created at 0.95
- **Contradiction detection** flags conflicting agent decisions

## Anti-Patterns

### Agent Sprawl

Creating too many specialized agents when a single agent with
appropriate tools would suffice. Coordination overhead grows
quadratically with agent count.

### Context Laundering

Passing information through memory just to get it into another
agent's context, when a direct tool call or file read would be
simpler and more reliable.

### Unbounded Agent Loops

Agents that retry indefinitely on failure. Always set:
- Maximum retry count
- Wall-clock timeout
- Token budget per task

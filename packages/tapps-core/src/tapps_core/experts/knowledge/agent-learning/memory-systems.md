# Memory Systems for AI Agents

## Overview

Memory systems enable AI agents to retain, retrieve, and share knowledge across
sessions. This guide covers memory tier taxonomy, confidence scoring, decay models,
reinforcement, cross-session sharing, contradiction detection, garbage collection,
expert injection, and practical implementation patterns.

## Memory Tier Taxonomy

### Three-Tier Classification

Memory entries are classified by their expected lifetime and stability:

| Tier | Decay Rate | Lifetime | Content Examples |
|---|---|---|---|
| architectural | Slow | Months-years | Project structure, key decisions, framework choices |
| pattern | Medium | Weeks-months | Coding patterns, conventions, recurring solutions |
| context | Fast | Hours-days | Session-specific context, temporary state |

### Tier Selection Guidelines

```python
from enum import StrEnum

class MemoryTier(StrEnum):
    architectural = "architectural"  # slow decay
    pattern = "pattern"              # medium decay
    context = "context"              # fast decay


def select_tier(content: str, source: str) -> MemoryTier:
    """Select appropriate tier based on content characteristics."""
    architectural_keywords = [
        "architecture", "framework", "database", "deployment",
        "infrastructure", "protocol", "schema",
    ]
    context_keywords = [
        "session", "current", "temporary", "debugging",
        "investigating", "trying",
    ]

    content_lower = content.lower()

    for keyword in architectural_keywords:
        if keyword in content_lower:
            return MemoryTier.architectural

    for keyword in context_keywords:
        if keyword in content_lower:
            return MemoryTier.context

    return MemoryTier.pattern
```

### Tier-Specific Behaviors

```python
TIER_CONFIG = {
    "architectural": {
        "decay_rate": 0.01,           # 1% per day
        "min_confidence_to_keep": 0.3,
        "gc_exempt_days": 90,
        "max_entries": 200,
    },
    "pattern": {
        "decay_rate": 0.05,           # 5% per day
        "min_confidence_to_keep": 0.4,
        "gc_exempt_days": 30,
        "max_entries": 200,
    },
    "context": {
        "decay_rate": 0.15,           # 15% per day
        "min_confidence_to_keep": 0.5,
        "gc_exempt_days": 7,
        "max_entries": 100,
    },
}
```

## Confidence Scoring

### Source-Based Defaults

Different sources of memory have different inherent reliability:

```python
SOURCE_CONFIDENCE_DEFAULTS = {
    "human": 0.95,     # explicitly set by a developer
    "agent": 0.6,      # created by an AI agent
    "inferred": 0.4,   # derived from analysis
    "system": 0.9,     # created by TappsMCP internals
}
```

### Confidence Model

```python
from dataclasses import dataclass

@dataclass
class ConfidenceFactors:
    source_base: float         # from SOURCE_CONFIDENCE_DEFAULTS
    reinforcement_bonus: float # +0.05 per reinforcement, capped at 0.2
    decay_penalty: float       # accumulated decay over time
    contradiction_penalty: float  # -0.3 if contradicted

    @property
    def effective_confidence(self) -> float:
        """Calculate effective confidence from all factors."""
        raw = (
            self.source_base
            + self.reinforcement_bonus
            - self.decay_penalty
            - self.contradiction_penalty
        )
        return max(0.0, min(1.0, raw))
```

### Confidence Thresholds

| Confidence Range | Interpretation | Action |
|---|---|---|
| 0.8 - 1.0 | High confidence | Use without qualification |
| 0.6 - 0.8 | Moderate confidence | Use with note of uncertainty |
| 0.4 - 0.6 | Low confidence | Verify before using |
| 0.0 - 0.4 | Very low | Candidate for garbage collection |

## Decay Models

### Time-Based Exponential Decay

Memory confidence decays exponentially over time based on tier:

```python
import math
from datetime import datetime, UTC

def calculate_decay(
    confidence: float,
    last_accessed: datetime,
    tier: str,
    now: datetime | None = None,
) -> float:
    """Calculate decayed confidence based on time since last access."""
    if now is None:
        now = datetime.now(tz=UTC)

    days_elapsed = (now - last_accessed).total_seconds() / 86400.0
    decay_rate = TIER_CONFIG[tier]["decay_rate"]

    # Exponential decay: C(t) = C(0) * e^(-rate * t)
    decayed = confidence * math.exp(-decay_rate * days_elapsed)
    return max(0.0, decayed)
```

### Access-Boosted Decay

Frequently accessed memories decay slower:

```python
def calculate_access_adjusted_decay(
    confidence: float,
    last_accessed: datetime,
    access_count: int,
    tier: str,
) -> float:
    """Decay with access frequency adjustment."""
    base_decay = TIER_CONFIG[tier]["decay_rate"]

    # Reduce decay rate for frequently accessed memories
    # Each 10 accesses reduces decay by 20%, capped at 60% reduction
    access_factor = min(0.6, (access_count // 10) * 0.2)
    adjusted_rate = base_decay * (1 - access_factor)

    days_elapsed = (datetime.now(tz=UTC) - last_accessed).total_seconds() / 86400.0
    decayed = confidence * math.exp(-adjusted_rate * days_elapsed)
    return max(0.0, decayed)
```

## Reinforcement

### What is Reinforcement?

When an agent confirms that a memory is still accurate and useful,
it reinforces the memory, boosting its confidence and resetting decay:

```python
from datetime import datetime, UTC

def reinforce_memory(
    entry: dict,
    bonus: float = 0.05,
    max_bonus: float = 0.2,
) -> dict:
    """Reinforce a memory entry, boosting confidence."""
    current_reinforcements = entry.get("reinforce_count", 0)
    total_bonus = min(bonus * (current_reinforcements + 1), max_bonus)

    new_confidence = min(1.0, entry["confidence"] + bonus)

    return {
        **entry,
        "confidence": new_confidence,
        "last_reinforced": datetime.now(tz=UTC).isoformat(),
        "reinforce_count": current_reinforcements + 1,
        "last_accessed": datetime.now(tz=UTC).isoformat(),
    }
```

### Reinforcement Triggers

1. **Explicit** - agent calls `tapps_memory(action="reinforce", key="...")`
2. **Implicit** - memory is retrieved and used successfully
3. **Cross-agent** - another agent confirms the same pattern

### Reinforcement Caps

Prevent runaway confidence inflation:

```python
MAX_REINFORCE_BONUS = 0.2       # max total bonus from reinforcements
MAX_REINFORCE_COUNT = 20        # stop counting after 20 reinforcements
REINFORCE_COOLDOWN_HOURS = 1.0  # min time between reinforcements
```

## Contradiction Detection

### Detecting Conflicting Memories

When a new memory contradicts an existing one, flag both:

```python
def detect_contradiction(
    existing_value: str,
    new_value: str,
    key: str,
) -> dict | None:
    """Detect if new memory contradicts existing memory."""
    # Simple heuristic: check for negation patterns
    negation_pairs = [
        ("always", "never"),
        ("use", "avoid"),
        ("enable", "disable"),
        ("required", "optional"),
        ("async", "sync"),
    ]

    existing_lower = existing_value.lower()
    new_lower = new_value.lower()

    for word_a, word_b in negation_pairs:
        if word_a in existing_lower and word_b in new_lower:
            return {
                "contradicted": True,
                "reason": f"Conflicting terms: existing uses '{word_a}', new uses '{word_b}'",
            }
        if word_b in existing_lower and word_a in new_lower:
            return {
                "contradicted": True,
                "reason": f"Conflicting terms: existing uses '{word_b}', new uses '{word_a}'",
            }

    return None
```

### Resolution Strategies

| Strategy | When to Use |
|---|---|
| Newer wins | Context tier, fast-changing information |
| Higher confidence wins | Pattern tier, established conventions |
| Human wins over agent | Architectural tier, key decisions |
| Flag for review | When confidence is similar |

### Marking Contradictions

```python
def mark_contradicted(
    entry: dict,
    reason: str,
    penalty: float = 0.3,
) -> dict:
    """Mark an entry as contradicted, reducing its confidence."""
    return {
        **entry,
        "contradicted": True,
        "contradiction_reason": reason,
        "confidence": max(0.0, entry["confidence"] - penalty),
    }
```

## Cross-Session Sharing

### Scope Model

Memories have different visibility scopes:

```python
class MemoryScope:
    PROJECT = "project"   # visible across the entire project
    BRANCH = "branch"     # scoped to a git branch
    SESSION = "session"   # ephemeral, current session only
```

### Scope Resolution

When retrieving a memory, the most specific scope wins:

```python
def resolve_scope(
    memories: dict,
    key: str,
    current_scope: str,
    current_branch: str | None,
) -> dict | None:
    """Resolve memory with scope precedence: session > branch > project."""
    # Try session-scoped first
    session_key = f"{key}:session"
    if session_key in memories:
        return memories[session_key]

    # Try branch-scoped
    if current_branch:
        branch_key = f"{key}:branch:{current_branch}"
        if branch_key in memories:
            return memories[branch_key]

    # Fall back to project-scoped
    return memories.get(key)
```

### Multi-Agent Sharing

Multiple agents can share memories within a project:

```python
def save_shared_memory(
    store: object,
    key: str,
    value: str,
    source_agent: str,
) -> dict:
    """Save a memory accessible to all agents in the project."""
    return store.save(
        key=key,
        value=value,
        source="agent",
        source_agent=source_agent,
        scope="project",
    )
```

## Garbage Collection

### GC Criteria

Entries are candidates for garbage collection when:

1. Confidence drops below tier minimum (after decay)
2. Not accessed within the GC exempt period
3. Not reinforced recently
4. Contradicted and unresolved

```python
from datetime import datetime, UTC, timedelta

def is_gc_candidate(
    entry: dict,
    tier_config: dict,
    now: datetime | None = None,
) -> bool:
    """Determine if a memory entry should be garbage collected."""
    if now is None:
        now = datetime.now(tz=UTC)

    tier = entry["tier"]
    config = tier_config[tier]

    # Check confidence threshold
    if entry["confidence"] < config["min_confidence_to_keep"]:
        return True

    # Check access recency
    last_accessed = datetime.fromisoformat(entry["last_accessed"])
    exempt_days = config["gc_exempt_days"]
    if (now - last_accessed) > timedelta(days=exempt_days):
        return True

    # Contradicted entries are GC candidates
    if entry.get("contradicted", False):
        return True

    return False
```

### GC Process

```python
def run_garbage_collection(
    store: object,
    dry_run: bool = False,
) -> dict:
    """Run garbage collection on the memory store."""
    entries = store.list_all()
    candidates = []

    for entry in entries:
        if is_gc_candidate(entry, TIER_CONFIG):
            candidates.append(entry)

    if not dry_run:
        for entry in candidates:
            store.archive(entry["key"])  # move to archive, not delete

    return {
        "total_entries": len(entries),
        "gc_candidates": len(candidates),
        "archived": len(candidates) if not dry_run else 0,
        "dry_run": dry_run,
    }
```

### Archival vs Deletion

Garbage-collected entries are archived (moved to `archived_memories` table),
not permanently deleted. This preserves audit history and allows recovery.

## Expert Injection

### Memory-to-Expert Pipeline

High-confidence memories can be injected into expert consultations:

```python
def inject_memories_into_expert(
    expert_domain: str,
    question: str,
    store: object,
    min_confidence: float = 0.7,
    max_entries: int = 5,
) -> list[dict]:
    """Retrieve relevant memories for expert context injection."""
    # Search for memories related to the question
    results = store.search(question)

    # Filter by confidence and limit
    relevant = [
        r for r in results
        if r["confidence"] >= min_confidence
    ]

    # Sort by confidence (highest first) and limit
    relevant.sort(key=lambda x: x["confidence"], reverse=True)
    return relevant[:max_entries]
```

### Seeding from Project Profile

When a project is first analyzed, seed memories from the profile:

```python
def seed_from_profile(
    store: object,
    profile: dict,
) -> int:
    """Seed memory store with project profile data."""
    seeded = 0

    if profile.get("language"):
        store.save(
            key="project.language",
            value=f"Primary language: {profile['language']}",
            tier="architectural",
            source="system",
            tags=["profile", "language"],
        )
        seeded += 1

    if profile.get("framework"):
        store.save(
            key="project.framework",
            value=f"Framework: {profile['framework']}",
            tier="architectural",
            source="system",
            tags=["profile", "framework"],
        )
        seeded += 1

    if profile.get("test_framework"):
        store.save(
            key="project.test-framework",
            value=f"Test framework: {profile['test_framework']}",
            tier="pattern",
            source="system",
            tags=["profile", "testing"],
        )
        seeded += 1

    return seeded
```

## Memory Entry Model

### Complete Entry Structure

```python
from pydantic import BaseModel, Field

class MemoryEntry(BaseModel):
    key: str = Field(description="Unique slug identifier (max 128 chars)")
    value: str = Field(description="Memory content (max 4096 chars)")
    tier: str = Field(default="pattern", description="Decay classification")
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    source: str = Field(default="agent", description="Who created this")
    source_agent: str = Field(default="unknown", description="Agent identifier")
    scope: str = Field(default="project", description="Visibility scope")
    tags: list[str] = Field(default_factory=list, description="Search tags (max 10)")
    created_at: str = Field(description="ISO-8601 UTC creation time")
    updated_at: str = Field(description="ISO-8601 UTC last update time")
    last_accessed: str = Field(description="ISO-8601 UTC last access time")
    access_count: int = Field(default=0, ge=0)
    branch: str | None = Field(default=None, description="Git branch for branch scope")
    last_reinforced: str | None = Field(default=None)
    reinforce_count: int = Field(default=0, ge=0)
    contradicted: bool = Field(default=False)
    contradiction_reason: str | None = Field(default=None)
    seeded_from: str | None = Field(default=None)
```

### Key Format

Keys are lowercase slugs with dots, hyphens, and underscores:

```python
import re

KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")

# Valid keys
valid_keys = [
    "project.language",
    "pattern.async-await",
    "convention.naming_style",
    "gotcha.mypy-strict-mode",
]

# Invalid keys
invalid_keys = [
    "Project.Language",   # uppercase
    ".leading-dot",       # starts with dot
    "",                   # empty
    "a" * 200,            # too long
]
```

## MCP Tool Interface

### tapps_memory Actions

```python
# Save a memory
await tapps_memory(
    action="save",
    key="convention.import-style",
    value="Use absolute imports, group by stdlib/third-party/local",
    tier="pattern",
    source="agent",
    tags=["imports", "style"],
)

# Retrieve a memory
await tapps_memory(action="get", key="convention.import-style")

# Search memories
await tapps_memory(action="search", query="import style convention")

# List all memories (with optional filters)
await tapps_memory(action="list", tier="architectural")

# Delete a memory
await tapps_memory(action="delete", key="obsolete.pattern")

# Reinforce a memory
await tapps_memory(action="reinforce", key="convention.import-style")
```

## RAG Safety on Writes

### Why Filter Memory Content?

Stored memories are injected into future expert consultations. Malicious
content could enable prompt injection attacks:

```python
from tapps_mcp.knowledge.rag_safety import check_content_safety

def safe_save(store: object, key: str, value: str) -> dict:
    """Save memory with RAG safety check."""
    safety = check_content_safety(value)

    if not safety.safe and safety.match_count >= 3:
        return {"error": "content_blocked", "patterns": safety.flagged_patterns}

    if not safety.safe and safety.sanitised_content:
        value = safety.sanitised_content

    return store.save(key=key, value=value)
```

## MCP-Native Memory Patterns (2025-2026)

### Cross-Session Persistence via MCP Tools

Modern AI agents use MCP tool calls for structured memory operations,
replacing ad-hoc file-based persistence. The MCP server manages storage,
decay, and retrieval centrally, ensuring all connected clients share a
consistent memory state.

```python
# MCP-native memory pattern: agent persists learnings via tool calls
# No direct file I/O needed - the MCP server handles persistence

# Save a cross-session memory
await tapps_memory(
    action="save",
    key="architecture.auth-pattern",
    value="Project uses OAuth2 with PKCE flow for all public clients",
    tier="architectural",
    scope="project",
    tags=["auth", "security", "oauth"],
)

# Auto-recall: memories injected before each turn via memory_hooks config
# In .tapps-mcp.yaml:
# memory_hooks:
#   auto_recall: true
#   auto_capture: true
#   recall_top_k: 5
#   recall_min_confidence: 0.5
```

### Memory Federation Across Projects

Shared-scope memories enable knowledge transfer between related projects
without manual export/import:

```python
# Save a memory visible to all projects in the workspace
await tapps_memory(
    action="save",
    key="convention.error-handling",
    value="All services use structured error responses with error code, message, and trace_id",
    tier="pattern",
    scope="shared",
    tags=["error-handling", "conventions"],
)

# Consolidate duplicate and overlapping memories
await tapps_memory(action="consolidate")
```

### Agent Team Memory Coordination

When multiple agents collaborate (via Claude Code Agent Teams), memory
coordination prevents conflicting decisions:

```python
# Agent 1 saves a decision
await tapps_memory(
    action="save",
    key="decision.api-versioning",
    value="Using URL-based versioning (/api/v2/) per team consensus",
    tier="architectural",
    source="agent",
    source_agent="architect-agent",
)

# Agent 2 queries before making related decisions
result = await tapps_memory(action="search", query="api versioning strategy")
# Uses the existing decision rather than making a conflicting one
```

## Anti-Patterns

### Unbounded Memory Growth

Without max entry limits and garbage collection, the store grows indefinitely.
Enforce per-project limits (e.g., 500 entries) with eviction.

### No Decay

Static confidence scores become stale. Always apply time-based decay
appropriate to the memory tier.

### Trusting All Sources Equally

Agent-created memories should start with lower confidence (0.6) than
human-created ones (0.95). Source-based defaults prevent over-trust.

### No Contradiction Handling

Conflicting memories confuse agents. Detect and flag contradictions,
then resolve based on source authority and recency.

## Quick Reference

| Aspect | Recommendation |
|---|---|
| Tier selection | architectural/pattern/context by content |
| Confidence default | Source-based (human=0.95, agent=0.6) |
| Decay model | Exponential with tier-specific rates |
| Max entries | 500 per project |
| Eviction | Lowest confidence first |
| GC schedule | Daily or on-demand |
| Key format | Lowercase slug, max 128 chars |
| Value limit | 4096 characters |
| RAG safety | Check on every write |
| Scope resolution | session > branch > project |

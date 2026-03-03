# Memory Retrieval Patterns

## Overview

Effective memory retrieval for AI agents requires ranked relevance scoring,
intelligent filtering, and lifecycle management. This guide covers BM25-based
ranked retrieval, stemming and stop-word filtering, memory reinforcement
and decay, auto-GC, capture hooks, seeding, context injection, and
import/export patterns.

## BM25 Scoring for Ranked Retrieval

### What is BM25?

BM25 (Best Matching 25) is a probabilistic ranking function that scores
documents by term frequency, inverse document frequency, and document
length normalization. It outperforms simple keyword matching because it
penalizes common terms and rewards rare, discriminating terms.

### Pure Python BM25 Implementation

```python
import math
from collections import Counter

class BM25Scorer:
    """BM25 scoring engine for memory retrieval."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1  # term frequency saturation
        self.b = b     # document length normalization
        self._corpus: list[list[str]] = []
        self._avg_dl: float = 0.0
        self._idf: dict[str, float] = {}

    def fit(self, documents: list[list[str]]) -> None:
        """Index a corpus of tokenized documents."""
        self._corpus = documents
        total_len = sum(len(doc) for doc in documents)
        self._avg_dl = total_len / len(documents) if documents else 1.0

        # Compute inverse document frequency
        n = len(documents)
        df: Counter[str] = Counter()
        for doc in documents:
            for term in set(doc):
                df[term] += 1

        for term, freq in df.items():
            self._idf[term] = math.log((n - freq + 0.5) / (freq + 0.5) + 1)

    def score(self, query_tokens: list[str], doc_index: int) -> float:
        """Score a single document against a query."""
        doc = self._corpus[doc_index]
        doc_len = len(doc)
        tf = Counter(doc)
        score = 0.0

        for term in query_tokens:
            if term not in self._idf:
                continue
            term_freq = tf.get(term, 0)
            numerator = term_freq * (self.k1 + 1)
            denominator = term_freq + self.k1 * (
                1 - self.b + self.b * doc_len / self._avg_dl
            )
            score += self._idf[term] * numerator / denominator

        return score
```

### Ranking Memories

```python
def rank_memories(
    scorer: BM25Scorer,
    query_tokens: list[str],
    memories: list[dict],
    top_k: int = 10,
) -> list[dict]:
    """Rank memories by BM25 relevance score."""
    scored = [
        (i, scorer.score(query_tokens, i))
        for i in range(len(memories))
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [memories[i] for i, s in scored[:top_k] if s > 0]
```

## Stemming and Stop-Word Filtering

### Stop-Word Removal

Remove common words that add noise without discrimination value:

```python
STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "can", "shall",
    "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "it", "this", "that", "and", "or", "not", "no", "but", "if",
})

def remove_stop_words(tokens: list[str]) -> list[str]:
    """Remove stop words from token list."""
    return [t for t in tokens if t.lower() not in STOP_WORDS]
```

### Lightweight Stemming

Use suffix stripping for common English patterns without requiring NLTK:

```python
def simple_stem(word: str) -> str:
    """Apply basic suffix stripping for English words."""
    w = word.lower()
    for suffix in ("ation", "tion", "ing", "ment", "ness", "able", "ible", "ed", "ly", "es", "s"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            return w[:-len(suffix)]
    return w
```

### Tokenization Pipeline

```python
def tokenize(text: str) -> list[str]:
    """Tokenize, stem, and filter text for BM25 indexing."""
    import re
    raw_tokens = re.findall(r"\w+", text.lower())
    filtered = remove_stop_words(raw_tokens)
    return [simple_stem(t) for t in filtered]
```

## Memory Reinforcement

### Access-Based Boosting

When a memory is accessed or explicitly reinforced, its confidence
increases and its decay clock resets:

```python
from datetime import datetime, UTC

def reinforce_memory(entry: dict) -> dict:
    """Boost confidence and reset decay on access."""
    now = datetime.now(tz=UTC).isoformat()
    entry["confidence"] = min(1.0, entry["confidence"] + 0.05)
    entry["last_reinforced"] = now
    entry["last_accessed"] = now
    entry["access_count"] = entry.get("access_count", 0) + 1
    entry["reinforce_count"] = entry.get("reinforce_count", 0) + 1
    return entry
```

### Decay Reset

Reinforcement resets the decay timer. Without reinforcement, confidence
decays over time (see Auto-GC section). The `reinforce` MCP action
provides explicit boosting:

```
tapps_memory(action="reinforce", key="pattern.async-testing")
```

This is useful when an agent confirms that a memory is still valid and
actively helpful.

## Time-Based Confidence Decay

### Decay Formula

Memories lose confidence over time if not accessed or reinforced:

```python
from datetime import datetime, timedelta, UTC

DECAY_RATE = 0.01  # confidence loss per day
DECAY_FLOOR = 0.1  # minimum confidence before GC eligibility

def apply_decay(entry: dict) -> float:
    """Calculate decayed confidence based on time since last access."""
    last_accessed = datetime.fromisoformat(entry["last_accessed"])
    days_idle = (datetime.now(tz=UTC) - last_accessed).days
    decayed = entry["confidence"] - (DECAY_RATE * days_idle)
    return max(DECAY_FLOOR, decayed)
```

## Auto-GC Triggers

### Capacity-Based Garbage Collection

Auto-GC triggers when memory count exceeds a threshold (default: 80%
of max entries). It archives low-confidence and decayed memories:

```python
MAX_ENTRIES = 500
GC_THRESHOLD = 0.8  # trigger at 80% capacity

def should_trigger_gc(entry_count: int) -> bool:
    """Check if garbage collection should run."""
    return entry_count >= int(MAX_ENTRIES * GC_THRESHOLD)

def run_gc(memories: dict[str, dict]) -> list[str]:
    """Archive memories below the decay floor."""
    archived: list[str] = []
    for key, entry in list(memories.items()):
        effective_confidence = apply_decay(entry)
        if effective_confidence <= DECAY_FLOOR:
            archived.append(key)
            del memories[key]
    return archived
```

### GC in Session Start

Auto-GC runs automatically during `tapps_session_start` when memory
exceeds the capacity threshold. This keeps the memory store lean without
requiring manual intervention:

```python
async def session_start() -> str:
    """Initialize session with automatic GC if needed."""
    store = get_memory_store()
    entry_count = store.count()

    if should_trigger_gc(entry_count):
        archived = store.gc()
        log.info("auto_gc_completed", archived=len(archived))

    return "Session started."
```

## Memory Capture Hooks

### Session-End Persistence

A Claude Code `Stop` hook captures quality metrics and decisions made
during the session and saves them as memories:

```bash
#!/usr/bin/env bash
# .claude/hooks/stop-memory-capture.sh
# Capture session quality data for cross-session persistence

QUALITY_DATA=$(cat .tapps-mcp/.session-quality.json 2>/dev/null)
if [ -n "$QUALITY_DATA" ]; then
    echo "Session quality data captured for memory persistence."
    echo "$QUALITY_DATA"
fi
```

### What to Capture

| Memory Type | Tier | Example |
|---|---|---|
| Architecture decisions | `architectural` | "Using repository pattern for data access" |
| Code patterns discovered | `pattern` | "Async context managers for DB connections" |
| Session-specific context | `context` | "Working on auth module refactor" |
| Quality baselines | `pattern` | "Module X baseline score: 78/100" |

## Memory Seeding

### Initial Population from Project Profiles

When `tapps_init` runs, it can seed the memory store with information
extracted from the project profile:

```python
def seed_from_profile(
    store: object,
    profile: dict,
) -> int:
    """Seed memory store with project profile data."""
    seeded = 0

    if profile.get("tech_stack"):
        store.save(
            key="project.tech-stack",
            value=f"Tech stack: {', '.join(profile['tech_stack'])}",
            tier="architectural",
            source="system",
            confidence=0.9,
        )
        seeded += 1

    if profile.get("test_framework"):
        store.save(
            key="project.test-framework",
            value=f"Test framework: {profile['test_framework']}",
            tier="pattern",
            source="system",
            confidence=0.9,
        )
        seeded += 1

    return seeded
```

### Seeding Best Practices

- Seed with `source="system"` to distinguish from agent-learned memories
- Use high initial confidence (0.9) for project facts
- Use `tier="architectural"` for decisions, `tier="pattern"` for conventions
- Do not re-seed if memories already exist (check before writing)

## Context Injection

### Enriching Expert Consultations

When an expert consultation runs, relevant memories are injected as
additional context to improve response quality:

```python
def inject_memory_context(
    query: str,
    store: object,
    top_k: int = 5,
) -> str:
    """Retrieve and format relevant memories for context injection."""
    results = store.search(query, top_k=top_k)
    if not results:
        return query

    context_lines = ["Relevant project context:"]
    for entry in results:
        context_lines.append(f"- [{entry['tier']}] {entry['value']}")

    context_block = "\n".join(context_lines)
    return f"{context_block}\n\nQuery: {query}"
```

### Injection Ordering

1. Retrieve memories ranked by BM25 relevance to the query
2. Filter by minimum confidence threshold (default: 0.3)
3. Limit to top-k results (default: 5) to avoid context bloat
4. Format as a structured context block prepended to the query

## Import/Export Patterns

### JSONL Format

Memories export as JSONL (one JSON object per line) for portability:

```python
import json
from pathlib import Path

def export_memories(store: object, output_path: Path) -> int:
    """Export all memories to JSONL for sharing or backup."""
    entries = store.list_all()
    with output_path.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return len(entries)

def import_memories(
    store: object,
    input_path: Path,
    overwrite: bool = False,
) -> int:
    """Import memories from JSONL, optionally overwriting existing."""
    imported = 0
    for line in input_path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
            if not overwrite and store.get(entry["key"]):
                continue  # skip existing
            store.save(**entry)
            imported += 1
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    return imported
```

### Cross-Project Sharing

Export architectural memories from one project and import into another
to bootstrap knowledge transfer:

```bash
# Export from project A
tapps_memory(action="list", tier="architectural")
# -> manually export to JSONL

# Import into project B
tapps_memory(action="save", key="...", value="...", tier="architectural", source="system")
```

## Best Practices

1. **Use BM25 over keyword matching** for ranked retrieval - it handles term frequency and document length naturally
2. **Always filter stop words** before indexing or querying to improve signal-to-noise ratio
3. **Reinforce valuable memories** explicitly to prevent decay from archiving useful knowledge
4. **Run GC during session start** to keep the store within capacity without manual intervention
5. **Seed on first init only** - check for existing memories before re-seeding
6. **Limit context injection** to 5 memories to avoid overwhelming the query context
7. **Export regularly** for backup and cross-project knowledge transfer

## Anti-Patterns

1. **No stemming**: Without stemming, "testing" and "tests" are treated as different terms
2. **Unbounded retrieval**: Returning all memories instead of top-k wastes context budget
3. **No decay**: Without decay, stale memories accumulate and degrade retrieval quality
4. **Seeding duplicates**: Re-seeding on every init creates duplicate entries
5. **Injecting low-confidence memories**: Filter by confidence threshold before injection
6. **Skipping GC**: Without periodic cleanup, the store fills with decayed entries

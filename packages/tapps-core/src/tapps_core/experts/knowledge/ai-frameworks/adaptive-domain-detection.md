# Adaptive Domain Detection

## Overview

Domain detection routes incoming queries to the most relevant expert domain
(e.g., security, performance, testing). A static keyword-based detector
provides a reliable baseline, while an adaptive layer learns from feedback
outcomes to improve routing accuracy over time. The two work together with
confidence thresholds and fallback strategies.

## Static Keyword-Based Detection

### Word-Boundary Matching

Static detection uses regex word-boundary matching (`\b`) to avoid false
positives from substring collisions. Without word boundaries, a keyword
like "ci" would match inside "injection" or "specification":

```python
import re
from collections import defaultdict

DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "security": ["vulnerability", "injection", "authentication", "csrf", "xss"],
    "testing-strategies": ["pytest", "unittest", "mock", "fixture", "coverage"],
    "performance-optimization": ["latency", "throughput", "cache", "bottleneck"],
    "development-workflow": ["ci", "cd", "pipeline", "deploy", "git"],
}

def detect_domain_static(query: str) -> dict[str, float]:
    """Score each domain by keyword hit count using word-boundary regex."""
    scores: dict[str, float] = defaultdict(float)
    query_lower = query.lower()

    for domain, keywords in DOMAIN_KEYWORDS.items():
        for keyword in keywords:
            pattern = rf"\b{re.escape(keyword)}\b"
            matches = re.findall(pattern, query_lower)
            scores[domain] += len(matches)

    return dict(scores)
```

### Why Word Boundaries Matter

| Query | Keyword | Without `\b` | With `\b` |
|---|---|---|---|
| "SQL injection attack" | "ci" | Match (false positive) | No match |
| "CI pipeline config" | "ci" | Match | Match |
| "specification document" | "ci" | Match (false positive) | No match |

Always use `\b` in keyword patterns to prevent short keywords from
producing spurious matches.

## Query Expansion

### Synonym Pairs for Improved Recall

Query expansion maps synonyms and related terms to canonical keywords,
improving recall when users phrase queries differently:

```python
SYNONYM_PAIRS: dict[str, str] = {
    "auth": "authentication",
    "authn": "authentication",
    "authz": "authorization",
    "perf": "performance",
    "speed": "performance",
    "slow": "latency",
    "test": "testing",
    "spec": "testing",
    "vuln": "vulnerability",
    "cve": "vulnerability",
    "deploy": "deployment",
    "ship": "deployment",
}

def expand_query(query: str) -> str:
    """Expand query tokens using synonym mapping."""
    tokens = query.lower().split()
    expanded = []
    for token in tokens:
        expanded.append(token)
        if token in SYNONYM_PAIRS:
            expanded.append(SYNONYM_PAIRS[token])
    return " ".join(expanded)
```

### Expansion Best Practices

- Keep synonym pairs directional (abbreviation -> full term)
- Limit to approximately 60 pairs to avoid over-expansion
- Include common abbreviations and slang used in developer queries
- Test that expansions do not introduce cross-domain ambiguity

## Adaptive Domain Detection

### Learning from Feedback

The adaptive detector learns from explicit feedback on consultation
quality. When a user reports that a consultation was helpful or unhelpful,
the system adjusts routing weights:

```python
from dataclasses import dataclass, field

@dataclass
class DomainWeight:
    """Learned routing weight for a domain-keyword pair."""
    domain: str
    keyword: str
    weight: float = 1.0
    positive_count: int = 0
    negative_count: int = 0

    def apply_feedback(self, helpful: bool) -> None:
        """Adjust weight based on feedback outcome."""
        if helpful:
            self.positive_count += 1
            self.weight = min(2.0, self.weight + 0.1)
        else:
            self.negative_count += 1
            self.weight = max(0.1, self.weight - 0.15)
```

### Confidence Threshold

The adaptive detector only overrides the static result when its
confidence exceeds a threshold (default: 0.4). Below this threshold,
the system falls back to static detection:

```python
ADAPTIVE_CONFIDENCE_THRESHOLD = 0.4

def detect_domain(
    query: str,
    adaptive_scores: dict[str, float],
    static_scores: dict[str, float],
) -> tuple[str, float]:
    """Route query using adaptive scores with static fallback."""
    if adaptive_scores:
        best_domain = max(adaptive_scores, key=adaptive_scores.get)
        confidence = adaptive_scores[best_domain]

        if confidence >= ADAPTIVE_CONFIDENCE_THRESHOLD:
            return best_domain, confidence

    # Fallback to static detection
    if static_scores:
        best_domain = max(static_scores, key=static_scores.get)
        return best_domain, static_scores[best_domain]

    return "code-quality-analysis", 0.0  # default domain
```

### Weight Persistence

Adaptive weights persist to SQLite so learning survives across sessions:

```python
import sqlite3

def save_weights(conn: sqlite3.Connection, weights: list[DomainWeight]) -> None:
    """Persist adaptive weights to SQLite."""
    conn.executemany(
        """INSERT OR REPLACE INTO domain_weights
           (domain, keyword, weight, positive_count, negative_count)
           VALUES (?, ?, ?, ?, ?)""",
        [(w.domain, w.keyword, w.weight, w.positive_count, w.negative_count)
         for w in weights],
    )
    conn.commit()

def load_weights(conn: sqlite3.Connection) -> list[DomainWeight]:
    """Load adaptive weights from SQLite."""
    rows = conn.execute("SELECT * FROM domain_weights").fetchall()
    return [DomainWeight(**dict(row)) for row in rows]
```

## Knowledge Freshness Warnings

### Stale Knowledge Detection

When retrieved knowledge chunks are older than 365 days, a freshness
warning is appended to the consultation response:

```python
from datetime import datetime, timedelta, UTC

FRESHNESS_THRESHOLD_DAYS = 365

def check_freshness(
    chunk_date: datetime,
    domain: str,
) -> str | None:
    """Return a freshness warning if the chunk is stale."""
    age = datetime.now(tz=UTC) - chunk_date
    if age > timedelta(days=FRESHNESS_THRESHOLD_DAYS):
        days_old = age.days
        return (
            f"Warning: {domain} knowledge is {days_old} days old. "
            f"Recommendations may not reflect current best practices."
        )
    return None
```

### Freshness in Practice

- Freshness metadata is stored per-chunk at ingestion time
- Warnings appear at the end of expert responses, not inline
- Consumers can filter or prioritize based on freshness scores
- Knowledge files should be periodically reviewed and updated

## Integration with Expert RAG

### Full Detection Pipeline

```
Query
  |
  v
Query Expansion (synonyms)
  |
  v
Static Detection (keyword + word-boundary)
  |
  v
Adaptive Detection (learned weights)
  |
  v
Confidence Check (>= 0.4?)
  |
  +-- Yes --> Use adaptive domain
  +-- No  --> Fall back to static domain
  |
  v
RAG Retrieval (knowledge chunks from selected domain)
  |
  v
Freshness Check (warn if > 365 days)
  |
  v
Format Response
```

### Feedback Loop

1. User invokes `tapps_consult_expert` with a question
2. Domain detection routes to the best-matching expert
3. RAG retrieves relevant knowledge chunks
4. Response is formatted and returned to the user
5. User provides feedback via `tapps_feedback`
6. Adaptive weights are updated based on the feedback
7. Future queries benefit from improved routing

## Fallback Strategies

### When Adaptive Confidence Is Low

- Fall back to static keyword detection
- If static detection also has low scores, use `code-quality-analysis` as default
- Log the low-confidence routing for later analysis

### When No Keywords Match

- Use the query's structural features (question words, code patterns)
- Check for programming language mentions to infer domain
- Default to a general-purpose domain rather than returning no result

### When Multiple Domains Tie

- Prefer the domain with more recent positive feedback
- If no feedback data, prefer domains with more keyword matches
- Break remaining ties alphabetically for determinism

## Best Practices

1. **Always use word boundaries** in keyword patterns to prevent substring matches
2. **Set conservative thresholds** (0.4) to avoid premature adaptive overrides
3. **Cap weight adjustments** (0.1 increase, 0.15 decrease) to prevent oscillation
4. **Persist weights** to SQLite so learning survives session restarts
5. **Log all routing decisions** for debugging and analysis
6. **Review synonym pairs** periodically to remove ambiguous mappings
7. **Test with adversarial queries** that contain embedded keywords (e.g., "specification")

## Anti-Patterns

1. **Substring matching without boundaries**: "ci" matching inside "injection"
2. **Unbounded weight growth**: Weights should be clamped to a range (e.g., 0.1-2.0)
3. **No fallback**: Always have a static fallback when adaptive confidence is low
4. **Overfitting to recent feedback**: Use smoothing or decay on weight adjustments
5. **Ignoring freshness**: Serving stale knowledge without warnings misleads users

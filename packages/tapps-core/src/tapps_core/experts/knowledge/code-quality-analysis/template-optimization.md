# Template Optimization

## Overview

Template optimization is the systematic process of improving instructional templates (such as AGENTS.md, platform rules, and coding guidelines) through data-driven analysis. By tracking versions, measuring impact on quality outcomes, and iteratively refining content, teams maximize the effectiveness of AI-assisted workflows.

## Template Version Tracking with SQLite

### Schema Design
```sql
CREATE TABLE template_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_name TEXT NOT NULL,
    version TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sections JSON NOT NULL,
    UNIQUE(template_name, version)
);

CREATE TABLE template_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id INTEGER REFERENCES template_versions(id),
    task_id TEXT NOT NULL,
    pass_rate REAL,
    avg_score REAL,
    measured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Why Track Versions
- Compare quality outcomes across template changes
- Roll back to proven templates when regressions occur
- Build an audit trail of what instructions produced which results

## TF-IDF and Jaccard Redundancy Scoring

Templates accumulate redundant content over time. Redundancy scoring identifies sections that repeat information, enabling consolidation.

### TF-IDF Scoring
Compute term frequency-inverse document frequency across template sections. High TF-IDF terms are distinctive to a section; low TF-IDF terms appear everywhere and indicate shared (potentially redundant) content.

### Jaccard Pairwise Redundancy
```python
def find_redundant_pairs(
    sections: dict[str, str], threshold: float = 0.6
) -> list[tuple[str, str, float]]:
    """Find section pairs with high content overlap."""
    redundant = []
    names = list(sections.keys())
    for i in range(len(names)):
        tokens_i = set(sections[names[i]].lower().split())
        for j in range(i + 1, len(names)):
            tokens_j = set(sections[names[j]].lower().split())
            similarity = len(tokens_i & tokens_j) / len(tokens_i | tokens_j)
            if similarity > threshold:
                redundant.append((names[i], names[j], similarity))
    return sorted(redundant, key=lambda x: -x[2])
```

Merge or consolidate section pairs with Jaccard similarity above 0.6.

## Section Ablation Analysis

Ablation removes one section at a time and measures impact on quality outcomes.

### Classification Criteria
- **Essential**: Removing the section causes a statistically significant quality drop (p < 0.05)
- **Neutral**: Removing the section produces no significant change
- **Harmful**: Removing the section actually improves quality scores

### Acting on Results
- **Essential sections**: Keep and protect from accidental removal
- **Neutral sections**: Candidates for consolidation or removal to reduce template size
- **Harmful sections**: Remove immediately and investigate why they cause regressions

### Ablation Runner
```python
def run_ablation(template: str, sections: dict[str, str],
                 eval_fn: Callable[[str], float], n_runs: int = 30) -> dict[str, str]:
    baseline = [eval_fn(template) for _ in range(n_runs)]
    classifications = {}
    for name, content in sections.items():
        ablated = [eval_fn(template.replace(content, "")) for _ in range(n_runs)]
        p = compute_significance(baseline, ablated)
        if p < 0.05:
            classifications[name] = "essential" if mean(ablated) < mean(baseline) else "harmful"
        else:
            classifications[name] = "neutral"
    return classifications
```

## Engagement Level Cost-Benefit Calibration

### Three-Tier Model
| Level | Quality Gain | Friction Cost | Best For |
|-------|-------------|---------------|----------|
| High | +35% | +40% time | Critical systems, security-sensitive |
| Medium | +28% | +15% time | Most production projects |
| Low | +12% | +5% time | Prototypes, experiments |

### Calibration Process
1. Run the full benchmark suite at each engagement level
2. Measure quality improvement and developer friction per level
3. Compute cost-benefit ratio: quality gain per unit of added friction
4. Set engagement level thresholds based on project risk profile

## Failure Pattern Analysis

### Collecting and Analyzing Failures
```python
def analyze_failures(results: list[dict], max_suggestions: int = 5) -> list[dict]:
    failures = [r for r in results if not r["passed"]]
    patterns = Counter(f.get("failure_category", "unknown") for f in failures)
    return [
        {"pattern": p, "frequency": c, "suggestion": generate_suggestion(p, failures)}
        for p, c in patterns.most_common(max_suggestions)
    ]
```

### Common Failure Patterns
- **Missing context**: Template lacks project-specific guidance
- **Conflicting instructions**: Two sections give contradictory advice
- **Over-specification**: Template constrains valid approaches too tightly
- **Stale references**: Template references outdated tools or APIs
- **Ambiguous phrasing**: Instructions with multiple interpretations

## Non-Regression Promotion Gates

A new template version is promoted only when:
1. Quality scores equal or exceed the current production version
2. No single category regresses by more than 5%
3. The improvement is statistically significant (p < 0.05) or at least non-regressing
4. The template has been evaluated on the full benchmark suite
5. No harmful sections detected by ablation analysis

```python
def can_promote(candidate: list[float], production: list[float]) -> tuple[bool, str]:
    if mean(candidate) < mean(production) * 0.95:
        return False, "Regression detected"
    p = compute_significance(production, candidate)
    if mean(candidate) > mean(production) and p < 0.05:
        return True, "Significant improvement"
    if mean(candidate) >= mean(production):
        return True, "Non-regressing"
    return False, f"Marginal regression (p={p:.3f})"
```

## A/B Testing in Production

- Randomly assign sessions to template variants
- Ensure equal sample sizes across variants
- Define primary metric (quality gate pass rate) and secondary metrics (completion time)
- Set minimum sample size for statistical power before analyzing results
- Monitor for anomalies during the test period

## Best Practices

1. **Track everything**: Version templates, record outcomes, persist raw data
2. **Ablate regularly**: Run ablation after every significant template change
3. **Cap suggestions**: Limit failure analysis to top 5 patterns to avoid noise
4. **Require non-regression**: Never promote a template that makes things worse
5. **Calibrate per project**: Different projects benefit from different engagement levels
6. **Consolidate redundancy**: Merge sections with Jaccard similarity above 0.6
7. **Iterate incrementally**: Change one section at a time to isolate effects

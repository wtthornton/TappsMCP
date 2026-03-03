# Tool Effectiveness Measurement

## Overview

Measuring the effectiveness of individual tools in a quality pipeline is critical for understanding which tools provide genuine value, which are redundant, and how to allocate enforcement effort. The ALL_MINUS_ONE methodology provides a rigorous approach to isolating each tool's contribution.

## ALL_MINUS_ONE Evaluation Methodology

### Concept
For each tool, run the complete evaluation suite with all tools enabled, then run it again with that one tool disabled. The difference reveals the tool's marginal contribution.

### Why ALL_MINUS_ONE Over Isolation
- Captures interaction effects between tools (tool A may compensate for tool B)
- Reveals redundancy when removing a tool causes no quality drop
- Identifies critical tools whose removal causes disproportionate regressions
- More realistic than evaluating tools in isolation

### Implementation
```python
def evaluate_all_minus_one(
    tools: list[str], tasks: list[dict],
    run_eval: Callable[[list[str], list[dict]], list[float]],
) -> dict[str, dict]:
    baseline = run_eval(tools, tasks)
    baseline_mean = sum(baseline) / len(baseline)
    results = {}
    for tool in tools:
        reduced = run_eval([t for t in tools if t != tool], tasks)
        reduced_mean = sum(reduced) / len(reduced)
        impact = baseline_mean - reduced_mean
        results[tool] = {
            "impact": impact,
            "impact_pct": (impact / baseline_mean) * 100,
            "is_critical": impact > 0.05 * baseline_mean,
        }
    return results
```

### Interpreting Results
- **High positive impact**: Tool is critical -- removing it causes significant quality drop
- **Near-zero impact**: Tool may be redundant or its value is captured by other tools
- **Negative impact**: Tool may be counterproductive -- investigate further

## Builtin Evaluation Tasks

### Task Categories
| Category | Example Tasks | Measures |
|----------|--------------|----------|
| Quality | Lint fix, type error correction | Static analysis effectiveness |
| Security | Vulnerability detection, secret scanning | Security tool coverage |
| Architecture | Circular dependency detection, coupling | Structural analysis depth |
| Debugging | Error diagnosis, root cause analysis | Diagnostic tool value |
| Refactoring | Complexity reduction, dead code removal | Improvement tool impact |

### Task Design Principles
- Each task has a single, unambiguous correct outcome
- Tasks range from easy to hard within each category
- Tasks are representative of real-world coding scenarios
- Include both detection tasks (find the problem) and fix tasks (resolve it)

## Call Pattern Analysis

### Efficiency Metrics
```python
def compute_efficiency(call_log: list[dict]) -> dict[str, float]:
    total = len(call_log)
    seen = set()
    redundant = 0
    for call in call_log:
        key = (call["tool_name"], call.get("input_hash", ""))
        if key in seen:
            redundant += 1
        seen.add(key)
    return {
        "total_calls": total,
        "unique_tools_used": len(set(c["tool_name"] for c in call_log)),
        "avg_duration_ms": sum(c["duration_ms"] for c in call_log) / max(total, 1),
        "redundant_call_rate": redundant / max(total, 1),
    }
```

### Optimal Call Patterns
- Minimize redundant calls to the same tool with identical inputs
- Front-load fast tools (linting) before slow tools (type checking)
- Use quick-check modes during iteration, full checks before completion
- Batch related checks when possible

## Data-Driven Checklist Calibration

### Engagement-Level Calibration
```python
def calibrate_checklist(
    impacts: dict[str, dict], level: str,
) -> dict[str, str]:
    """Assign tools to required/recommended/optional based on impact."""
    assignments = {}
    for tool, data in impacts.items():
        pct = data["impact_pct"]
        if level == "high":
            assignments[tool] = "required" if pct > 2.0 else "recommended"
        elif level == "medium":
            assignments[tool] = (
                "required" if pct > 5.0
                else "recommended" if pct > 1.0
                else "optional"
            )
        else:  # low
            assignments[tool] = "required" if data["is_critical"] else "optional"
    return assignments
```

### Calibration Cadence
- Re-calibrate after adding new tools to the pipeline
- Re-calibrate after significant template changes
- Re-calibrate quarterly to account for evolving codebases

## Expert System Effectiveness Tracking

### Metrics
- **Domain accuracy**: Was the query routed to the correct domain expert
- **Knowledge freshness**: Were retrieved knowledge chunks up to date
- **Actionability**: Did the consultation lead to a concrete improvement

### Improvement Actions
- Update knowledge files for domains with declining accuracy
- Add new knowledge files for frequently queried but poorly covered topics
- Tune domain detection keywords based on misrouting patterns

## Memory System Effectiveness Tracking

### What to Measure
- **Retrieval relevance**: Are recalled memories pertinent to the current task
- **Cross-session value**: Do memories from one session help in future sessions
- **Contradiction rate**: How often do saved memories conflict with each other
- **Decay accuracy**: Are decayed memories truly less relevant over time

### Impact Analysis
Compare task outcomes with and without the memory system enabled. A positive delta in quality scores indicates the memory system is providing value.

## Adaptive Feedback Loops

### Closing the Loop
1. **Measure**: Run evaluations and collect per-tool effectiveness data
2. **Analyze**: Identify tools with declining or improving effectiveness
3. **Adjust**: Update tool weights, checklist requirements, or thresholds
4. **Verify**: Re-run evaluations to confirm adjustments improved outcomes

### Weight Adjustment
```python
def adjust_weights(
    weights: dict[str, float], effectiveness: dict[str, float],
    learning_rate: float = 0.1,
) -> dict[str, float]:
    total_eff = sum(effectiveness.values())
    new = {
        t: w + learning_rate * (effectiveness.get(t, 0) / max(total_eff, 1e-6) - w)
        for t, w in weights.items()
    }
    total = sum(new.values())
    return {k: v / total for k, v in new.items()}
```

### Guardrails
- Set minimum and maximum weight bounds to prevent extreme adjustments
- Require minimum sample size before adjusting weights
- Use low learning rate (0.05-0.15) to prevent oscillation
- Implement confidence threshold (e.g., 0.4) below which adaptive routing falls back to static defaults

## Best Practices

1. **Use ALL_MINUS_ONE**: Measuring tools in isolation misses interaction effects
2. **Cover all categories**: Evaluation tasks must span security, complexity, style, architecture, debugging
3. **Track call patterns**: Efficiency matters as much as effectiveness
4. **Calibrate per engagement level**: Different projects need different tool requirements
5. **Close the feedback loop**: Connect evaluation results back to configuration
6. **Set guardrails on adaptation**: Prevent adaptive systems from making extreme adjustments
7. **Persist all measurements**: Historical data enables trend analysis and regression detection

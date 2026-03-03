# Benchmark Evaluation for AI Coding Tools

## Overview

AGENTBench-style evaluation provides a rigorous, reproducible methodology for measuring how effectively AI coding tools improve code quality. It combines curated datasets, controlled execution environments, and statistical analysis to produce actionable insights.

## Evaluation Methodology

### Core Principles
- **Reproducibility**: Every run must produce identical results given the same inputs
- **Isolation**: Evaluations run in sandboxed environments to prevent cross-contamination
- **Statistical rigor**: Use significance tests to distinguish real improvements from noise
- **Baseline comparison**: Always measure against a no-tool baseline

### Evaluation Pipeline
1. Load dataset of coding tasks with known ground truth
2. Inject context (tool configurations, project profiles) into each task
3. Execute tasks in isolated environments
4. Collect results and compute metrics
5. Aggregate scores and test for statistical significance
6. Persist results for trend analysis

## Dataset Loading Patterns

### HuggingFace Datasets
```python
dataset = load_dataset("code-quality/agentbench", split="test")
security_tasks = dataset.filter(lambda x: x["category"] == "security")
```

### Parquet and JSON
```python
# Parquet for offline evaluation
df = pd.read_parquet("benchmarks/tasks.parquet")

# JSON for hand-curated task definitions
tasks = [Task(**json.load(f)) for f in task_dir.glob("*.json")]
```

### Dataset Schema
- **task_id**: Unique identifier
- **category**: Quality category (security, complexity, style, architecture)
- **input_code**: Source code to evaluate or improve
- **expected_output**: Ground truth or expected improvements
- **difficulty**: Rating (easy, medium, hard)

## Context Injection with Redundancy Analysis

### Jaccard Similarity for Redundancy Detection
```python
def jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Compute Jaccard similarity between two token sets."""
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 1.0

def is_redundant(new_ctx: str, existing_ctx: str, threshold: float = 0.7) -> bool:
    """Check if new context is too similar to existing context."""
    new_tokens = set(new_ctx.lower().split())
    existing_tokens = set(existing_ctx.lower().split())
    return jaccard_similarity(new_tokens, existing_tokens) > threshold
```

### Injection Strategy
- Inject project configuration (linter rules, type checker settings)
- Inject relevant code context (imports, related modules)
- Deduplicate overlapping context sections before injection
- Track which context sections contributed to improved outcomes

## Docker-Isolated Evaluation Environments

### Container Configuration
```dockerfile
FROM python:3.12-slim
RUN pip install ruff mypy bandit radon vulture
WORKDIR /evaluation
COPY evaluator.py tasks/ /evaluation/
ENTRYPOINT ["python", "evaluator.py"]
```

### Execution Pattern
```python
def run_isolated(task_id: str, timeout: int = 300) -> dict:
    result = subprocess.run(
        ["docker", "run", "--rm", "--memory=512m", "--cpus=1.0",
         "--network=none", f"--env=TASK_ID={task_id}", "evaluator:latest"],
        capture_output=True, text=True, timeout=timeout,
    )
    return json.loads(result.stdout)
```

Key isolation properties: memory limits, CPU caps, no network access, automatic container cleanup.

## Results Aggregation with Statistical Significance

### McNemar's Test
Compares paired binary outcomes (pass/fail) between two configurations:

```python
def mcnemars_test(a_only: int, b_only: int) -> float:
    """Compute McNemar's test p-value with continuity correction."""
    if a_only + b_only == 0:
        return 1.0
    chi2_stat = (abs(a_only - b_only) - 1) ** 2 / (a_only + b_only)
    return 1 - chi2.cdf(chi2_stat, df=1)
```

### Aggregation Strategy
- Build contingency tables for pairwise comparison
- Apply McNemar's test with continuity correction
- Report effect size alongside p-values
- Use Bonferroni correction when comparing multiple configurations

## JSONL/CSV Persistence

### Storage Layout
```
benchmarks/results/
  raw/          # JSONL per-task results (append-only)
  summaries/    # CSV aggregated summaries (one row per run)
  comparisons/  # Pairwise statistical comparisons
```

- Use JSONL for detailed per-task results (append-friendly, line-oriented)
- Use CSV for aggregated summaries (easy to load into DataFrames or spreadsheets)
- Always include timestamps in UTC ISO format

## CLI Integration

```bash
benchmark run --dataset tasks.parquet --config default.yaml
benchmark analyze --run-id 2026-03-01-001 --format markdown
benchmark report --baseline run-001 --candidate run-002
```

- Support `--dry-run` for previewing what would execute
- Output structured data by default, with `--format` for human-readable
- Include `--timeout` to prevent runaway evaluations
- Log progress to stderr so stdout remains machine-parseable

## Best Practices

1. **Version your datasets**: Tag dataset releases so evaluations are reproducible
2. **Pin tool versions**: Record exact versions of all tools under evaluation
3. **Use warm-up runs**: Discard the first run to eliminate cold-start effects
4. **Separate dev and eval sets**: Never tune parameters on the evaluation set
5. **Track environment metadata**: Record OS, Python version, hardware specs per run
6. **Set meaningful timeouts**: Balance between allowing complex tasks and catching hangs
7. **Automate the full pipeline**: From dataset loading to report generation
8. **Archive raw results**: Keep per-task outputs for retrospective analysis

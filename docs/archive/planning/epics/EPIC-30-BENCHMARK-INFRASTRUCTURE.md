# Epic 30: Benchmark Infrastructure & AGENTBench Integration

> Build an evaluation harness that measures whether TappsMCP-generated AGENTS.md files
> actually help coding agents solve real GitHub issues — using the eth-sri/agentbench
> dataset and SWE-bench-compatible evaluation methodology.

**Status:** Complete
**Priority:** P1 — High (validates core product hypothesis: generated context files help agents)
**Estimated LOE:** ~3-4 weeks (1 developer)
**Dependencies:** Epic 8 (Pipeline Orchestration), Epic 18 (Engagement Levels), Epic 28 (Quality Remediation)
**Blocks:** Epic 31 (Template Self-Optimization Loop), Epic 32 (MCP Tool Effectiveness Benchmarking)

---

## Goal

Create a benchmark subsystem that answers the question: **"Do TappsMCP-generated AGENTS.md files improve or degrade coding agent performance on real-world tasks?"** The ETH Zurich study (arXiv 2602.11988, Feb 2026) found that LLM-generated context files reduce agent success by ~2% while human-written files improve it by ~4%. TappsMCP generates AGENTS.md via `tapps_init` — we need to know which camp our output falls into, and by how much.

## Rationale

| Consideration | Without Benchmark | With Benchmark |
|---------------|-------------------|----------------|
| **Template quality** | Assumed helpful; no measurement | Measured pass@1 against baseline |
| **Engagement levels** | High/medium/low chosen by feel | Calibrated to cost-benefit tradeoff |
| **Redundancy detection** | Manual review | Automated overlap scoring |
| **Regression prevention** | Template changes untested | CI-gated on resolution rate |
| **Product credibility** | "We think this helps" | "4.2% improvement on AGENTBench" |

## 2026 Best Practices Applied

- **AGENTBench dataset** (eth-sri, Feb 2026) — 138 instances from 12 Python repos where developers already wrote context files. The gold standard for evaluating AGENTS.md effectiveness.
- **SWE-bench evaluation methodology** — Docker-isolated patch application with both regression and instance-specific test validation. De facto standard for coding agent benchmarks.
- **MCPMark-style task format** — `meta.json` + `description.md` + `verify.py` per task for deterministic, reproducible evaluation (ICLR 2026 poster, arXiv 2509.24002).
- **Deterministic evaluation** — No LLM judging. Pass/fail determined by test execution, consistent with TappsMCP's no-LLM-in-the-toolchain principle.
- **Cost tracking** — Token usage and inference cost measured per run, enabling cost-benefit analysis per engagement level (critical finding from eth-sri: both human and LLM context files add 14-22% inference overhead).

## Acceptance Criteria

- [ ] Benchmark runner can load AGENTBench dataset (HuggingFace `eth-sri/agentbench`, 138 instances)
- [ ] Context injection: can inject TappsMCP-generated AGENTS.md into benchmark instances before agent execution
- [ ] Three-condition evaluation: NONE (baseline), TAPPS (TappsMCP-generated), HUMAN (developer-written)
- [ ] Docker-isolated evaluation: patches applied and tested in containers per SWE-bench methodology
- [ ] Metrics collected: resolution rate (pass@1), token usage, inference cost, step count, patch size
- [ ] Redundancy analyzer: scores overlap between generated AGENTS.md and existing repo documentation
- [ ] Results persisted in structured format (JSONL + summary CSV)
- [ ] Subset runner: can evaluate on N randomly sampled instances for fast iteration (default: 20)
- [ ] CLI entry point: `tapps-mcp benchmark run|analyze|report`
- [ ] All new code has unit tests; integration tests against a small fixture dataset (3-5 synthetic instances)

---

## Stories

### 30.1 — Benchmark Models & Configuration

**Points:** 3

Define the data models, configuration, and dataset schema for the benchmark subsystem.

**Source Files:**
- `src/tapps_mcp/benchmark/__init__.py` (new package)
- `src/tapps_mcp/benchmark/models.py`
- `src/tapps_mcp/benchmark/config.py`

**Tasks:**
- [ ] Create `benchmark/` package under `src/tapps_mcp/`
- [ ] Define Pydantic models:
  - `BenchmarkInstance` — mirrors AGENTBench HuggingFace schema: `instance_id`, `repo`, `problem_description`, `clean_pr_patch`, `test_commands`, `test_file_names`, `test_file_contents`, `docker_image`, `setup_commands`, `key_files`
  - `BenchmarkConfig` — `dataset_name` (HuggingFace ID or local path), `context_mode` (none/tapps/human), `engagement_level` (high/medium/low), `subset_size` (int, 0=all), `workers` (int), `output_dir` (Path), `docker_timeout` (int, seconds)
  - `BenchmarkResult` — `instance_id`, `context_mode`, `resolved` (bool), `token_usage` (int), `inference_cost` (float), `steps` (int), `patch_size` (int), `error` (str|None), `duration_ms` (int)
  - `BenchmarkSummary` — `total_instances`, `resolved_count`, `resolution_rate`, `avg_tokens`, `avg_cost`, `avg_steps`, per-repo breakdown
- [ ] Define `BenchmarkConfig` defaults: subset_size=20, workers=4, docker_timeout=300
- [ ] Write ~10 unit tests for model validation, serialization, config defaults

**Definition of Done:** All models validate correctly. Config handles defaults. Serialization round-trips.

---

### 30.2 — Dataset Loader

**Points:** 3

Load AGENTBench instances from HuggingFace or local Parquet files. Support filtering and random subset sampling.

**Source Files:**
- `src/tapps_mcp/benchmark/dataset.py`

**Tasks:**
- [ ] `load_dataset(config: BenchmarkConfig) -> list[BenchmarkInstance]`:
  - Load from HuggingFace `datasets` library (lazy import, optional dependency)
  - Fallback: load from local Parquet file path
  - Map HuggingFace columns to `BenchmarkInstance` fields
- [ ] `sample_subset(instances, n, seed)` — deterministic random sampling for fast iteration
- [ ] `filter_by_repo(instances, repo_names)` — filter to specific repositories
- [ ] Handle missing optional fields gracefully (some instances lack `risk_factors` or `rationale`)
- [ ] Write ~8 unit tests: HuggingFace load (mocked), local Parquet load (fixture file), subset sampling, filtering

**Definition of Done:** Dataset loads from both sources. Subset sampling is deterministic. Filtering works.

---

### 30.3 — Context Injection Engine

**Points:** 5

Generate and inject TappsMCP AGENTS.md files into benchmark repository checkouts before agent execution. This is the core mechanism that connects TappsMCP's template system to the evaluation harness.

**Source Files:**
- `src/tapps_mcp/benchmark/context_injector.py`

**Tasks:**
- [ ] `generate_tapps_context(repo_path: Path, engagement_level: str) -> str`:
  - Run TappsMCP's template generation pipeline against the target repo
  - Use `load_agents_template(engagement_level)` to get template content
  - Apply project-specific customization (detect test runner, package manager, key files from instance metadata)
  - Return the generated AGENTS.md content
- [ ] `inject_context(repo_path: Path, content: str, filename: str = "AGENTS.md")`:
  - Write the context file to the repository root
  - Handle existing AGENTS.md (backup as `.agents.md.bak` for HUMAN condition restore)
- [ ] `remove_context(repo_path: Path, filename: str = "AGENTS.md")`:
  - Remove injected context, restore backup if present
- [ ] `RedundancyAnalyzer`:
  - `score_redundancy(agents_md: str, repo_docs: list[str]) -> float` — 0.0 (unique) to 1.0 (fully redundant)
  - Extract text from README.md, CONTRIBUTING.md, pyproject.toml description, docstrings
  - Use token-level Jaccard similarity and section-level cosine similarity (TF-IDF, no external deps beyond scikit-learn)
  - Flag sections that repeat discoverable information
- [ ] Write ~12 unit tests: context generation, injection/removal, redundancy scoring, backup/restore

**Definition of Done:** TappsMCP templates injected into repos. Redundancy scored. Backup/restore for human context.

---

### 30.4 — Docker Evaluation Runner

**Points:** 8

Execute benchmark instances in Docker containers, apply agent-generated patches, run tests, and collect pass/fail results. Follows the SWE-bench evaluation methodology.

**Source Files:**
- `src/tapps_mcp/benchmark/evaluator.py`
- `src/tapps_mcp/benchmark/docker_runner.py`

**Tasks:**
- [ ] `DockerRunner`:
  - `prepare_container(instance: BenchmarkInstance) -> str` — pull/build image, return container ID
  - `apply_patch(container_id: str, patch: str) -> bool` — apply unified diff to repo in container
  - `run_tests(container_id: str, commands: list[str], timeout: int) -> TestResult` — execute test commands, capture stdout/stderr, return pass/fail
  - `cleanup(container_id: str)` — remove container and volumes
  - Error handling: timeout, OOM, docker daemon unavailable
- [ ] `Evaluator`:
  - `evaluate_instance(instance, context_mode, engagement_level) -> BenchmarkResult`:
    - For NONE: run agent with no context file
    - For TAPPS: inject TappsMCP AGENTS.md, run agent
    - For HUMAN: use developer-written context already in repo
    - Apply resulting patch in Docker, run both repo-level and instance-specific tests
    - Collect metrics: resolution, tokens, cost, steps, duration
  - `evaluate_batch(instances, config) -> list[BenchmarkResult]`:
    - Parallel execution with configurable worker count
    - Progress reporting via callback
    - Graceful handling of individual instance failures
- [ ] `TestResult` model: `passed` (bool), `total_tests` (int), `passed_tests` (int), `failed_tests` (int), `stdout`, `stderr`, `duration_ms`
- [ ] Write ~10 unit tests (Docker interactions mocked): patch application, test execution, timeout handling, batch parallelism

**Definition of Done:** Instances evaluate in Docker isolation. Patches applied and tested. Batch parallelism works. Failures handled gracefully.

---

### 30.5 — Results Aggregation & Reporting

**Points:** 5

Aggregate per-instance results into summary statistics, generate comparison reports across context modes, and persist results for trend analysis.

**Source Files:**
- `src/tapps_mcp/benchmark/analyzer.py`
- `src/tapps_mcp/benchmark/reporter.py`

**Tasks:**
- [ ] `ResultsAnalyzer`:
  - `aggregate(results: list[BenchmarkResult]) -> BenchmarkSummary` — compute resolution rate, averages, per-repo breakdown
  - `compare_conditions(baseline: list[BenchmarkResult], treatment: list[BenchmarkResult]) -> ComparisonReport`:
    - Delta in resolution rate (with confidence interval)
    - Delta in token usage and cost
    - Per-repo breakdown of improvements/regressions
    - Statistical significance test (McNemar's test for paired binary outcomes)
  - `engagement_comparison(results_by_level: dict[str, list[BenchmarkResult]]) -> EngagementReport`:
    - Side-by-side comparison of high/medium/low engagement levels
    - Cost-benefit analysis: resolution improvement per additional token spent
- [ ] `ResultsPersistence`:
  - `save_results(results, run_id, output_dir)` — JSONL per-instance + summary CSV
  - `load_results(run_id, output_dir) -> list[BenchmarkResult]`
  - `list_runs(output_dir) -> list[RunMetadata]`
- [ ] `ReportGenerator`:
  - `generate_markdown(comparison: ComparisonReport) -> str` — human-readable comparison report
  - `generate_csv(results) -> str` — machine-readable for external analysis
- [ ] Write ~10 unit tests: aggregation math, comparison deltas, persistence round-trip, report generation

**Definition of Done:** Results aggregated with statistical tests. Comparison reports generated. Results persisted for trend tracking.

---

### 30.6 — CLI Integration

**Points:** 3

Add benchmark commands to the TappsMCP CLI for running evaluations, analyzing results, and generating reports.

**Source Files:**
- `src/tapps_mcp/cli.py` (extend existing)
- `src/tapps_mcp/benchmark/cli_commands.py`

**Tasks:**
- [ ] `tapps-mcp benchmark run`:
  - `--dataset` — HuggingFace dataset name or local path (default: `eth-sri/agentbench`)
  - `--context-mode` — none, tapps, human, all (default: all)
  - `--engagement-level` — high, medium, low (default: medium)
  - `--subset` — number of instances to evaluate (default: 20)
  - `--workers` — parallel worker count (default: 4)
  - `--output-dir` — results directory (default: `.tapps-mcp/benchmark/`)
  - `--run-id` — experiment identifier (auto-generated if not provided)
- [ ] `tapps-mcp benchmark analyze`:
  - `--run-id` — specific run to analyze (default: latest)
  - `--compare` — comma-separated run IDs to compare
  - `--format` — markdown, csv, json (default: markdown)
- [ ] `tapps-mcp benchmark report`:
  - `--output` — file path for report (default: stdout)
  - `--include-redundancy` — include redundancy analysis in report
- [ ] Write ~5 unit tests for CLI argument parsing and command dispatch

**Definition of Done:** All three CLI commands work. Help text documents all options. Output is human-readable.

---

### 30.7 — Fixture Dataset & Integration Tests

**Points:** 3

Create a small synthetic benchmark dataset (3-5 instances) for integration testing without requiring Docker or API access. Establish the test patterns for Epics 31-32.

**Source Files:**
- `tests/fixtures/benchmark/` (new directory)
- `tests/integration/test_benchmark_pipeline.py`

**Tasks:**
- [ ] Create 3-5 synthetic benchmark instances:
  - Simple Python repos with known issues and patches
  - Each instance has: `problem_description`, `clean_pr_patch`, `test_commands`, `test_file_names`, `test_file_contents`
  - Include one instance with an existing AGENTS.md (for HUMAN condition testing)
- [ ] Integration tests (mark as `@pytest.mark.slow`):
  - Full pipeline: load → inject context → (mock) evaluate → aggregate → report
  - Context injection round-trip: inject → verify file exists → remove → verify cleaned
  - Redundancy analysis: score a known-redundant vs known-unique AGENTS.md
- [ ] Test helper: `MockEvaluator` that returns predetermined results for unit testing downstream code
- [ ] Write ~8 integration tests

**Definition of Done:** Fixture dataset created. Integration tests pass without Docker. MockEvaluator available for unit tests.

---

## Performance Targets

| Operation | Target | Notes |
|-----------|--------|-------|
| Dataset load (138 instances) | < 5s | HuggingFace cached after first download |
| Context generation (per instance) | < 500ms | Template rendering + project detection |
| Redundancy analysis (per instance) | < 2s | TF-IDF on <10 documents |
| Single instance evaluation | < 10 min | Docker + agent execution + test run |
| 20-instance subset (4 workers) | < 60 min | Parallel Docker execution |
| Full 138-instance run (8 workers) | < 6 hours | With API rate limits |
| Results aggregation | < 1s | In-memory statistics |

## File Layout

```
src/tapps_mcp/benchmark/
    __init__.py
    models.py              # BenchmarkInstance, Config, Result, Summary
    config.py              # Configuration and defaults
    dataset.py             # HuggingFace/Parquet loader
    context_injector.py    # AGENTS.md generation + injection + redundancy
    docker_runner.py       # Docker container management
    evaluator.py           # Instance evaluation orchestration
    analyzer.py            # Results aggregation and comparison
    reporter.py            # Markdown/CSV report generation
    cli_commands.py        # CLI command handlers

tests/fixtures/benchmark/  # Synthetic test dataset
tests/unit/test_benchmark_models.py
tests/unit/test_benchmark_dataset.py
tests/unit/test_benchmark_context.py
tests/unit/test_benchmark_evaluator.py
tests/unit/test_benchmark_analyzer.py
tests/integration/test_benchmark_pipeline.py
```

## Optional Dependencies

| Package | Purpose | Install |
|---------|---------|---------|
| `datasets` | HuggingFace dataset loading | `uv add datasets` |
| `docker` | Docker SDK for Python | `uv add docker` |
| `scikit-learn` | TF-IDF for redundancy analysis | `uv add scikit-learn` |

All are optional with graceful degradation (local Parquet fallback, mock evaluator, Jaccard-only redundancy).

## Key Design Decisions

1. **AGENTBench over SWE-bench** — AGENTBench instances come from repos with existing AGENTS.md files, making the HUMAN baseline meaningful. SWE-bench repos mostly lack context files.
2. **Subset-first design** — Default 20-instance subset enables fast iteration (< 1 hour). Full 138-instance runs reserved for CI/release validation.
3. **No LLM judging** — Evaluation is purely test-based (pass/fail), consistent with TappsMCP's deterministic principle.
4. **Statistical significance** — McNemar's test for paired binary outcomes (same instances, different conditions) is the correct test for this design.
5. **Cost tracking as first-class metric** — The eth-sri study found 14-22% cost overhead from context files. Cost-benefit ratio matters more than raw resolution rate.

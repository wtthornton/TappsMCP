# Epic 31: Template Self-Optimization Loop

> Close the feedback loop: use benchmark results from Epic 30 to iteratively refine
> TappsMCP's AGENTS.md templates, eliminating redundancy, calibrating engagement levels,
> and version-tracking every template iteration with measured improvement deltas.

**Status:** Complete
**Priority:** P1 — High (transforms TappsMCP from "generates context files" to "generates *validated* context files")
**Estimated LOE:** ~3-4 weeks (1 developer)
**Dependencies:** Epic 30 (Benchmark Infrastructure), Epic 18 (Engagement Levels), Epic 5 (Adaptive Learning)
**Blocks:** None (but informs future template changes)

---

## Goal

Build a closed-loop template optimization system that treats benchmark resolution rate as a fitness function. Each template variant is measured against the AGENTBench baseline, scored for redundancy, and compared against previous versions. Templates that improve agent success are promoted; templates that regress are rejected. This follows the self-evolving agent pattern (OpenAI Cookbook, Feb 2026; EvoAgentX EMNLP 2025 Demo) applied to prompt/template engineering rather than model weights.

## Rationale

| Problem | Current State | After Epic 31 |
|---------|--------------|---------------|
| **Redundancy** | Templates may repeat README/docstring content | Redundancy scored; sections above threshold flagged for removal |
| **Engagement calibration** | High/medium/low chosen by intuition | Each level's cost-benefit measured and optimized |
| **Template regression** | Changes to templates are unvalidated | Every template change measured against benchmark baseline |
| **Section value** | All sections assumed equally valuable | Per-section ablation identifies which sections drive resolution |
| **Version history** | Git commits only | Structured version tracking with benchmark scores per version |

## 2026 Best Practices Applied

- **Evaluation-driven prompt optimization** — The OpenAI Cookbook self-evolving agents pattern (Feb 2026): baseline -> feedback -> eval -> optimize -> updated prompt -> repeat. TappsMCP applies this to template engineering.
- **TextGrad-style natural language gradients** — EvoAgentX (EMNLP 2025 Demo) demonstrates backpropagation-like refinement of agent instructions. Template sections that correlate with failures get targeted rewrites.
- **Ablation testing** — Standard practice in ML evaluation: remove one component at a time to measure marginal contribution. Applied to AGENTS.md sections.
- **Redundancy as a measured metric** — The eth-sri study (Feb 2026) proved that redundant context actively degrades performance. Redundancy scoring becomes a quality gate for templates.
- **Version-tracked prompt iterations** — Following the `PromptVersionEntry` pattern from OpenAI Cookbook: version number, prompt text, eval scores, timestamp, metadata.

## Acceptance Criteria

- [ ] Template version tracker persists: version number, template content hash, benchmark scores, redundancy scores, timestamp, promotion status
- [ ] Redundancy analyzer flags sections with >60% overlap against discoverable repo documentation
- [ ] Section ablation runner: evaluates template with each section removed to measure per-section value
- [ ] Engagement-level calibrator: recommends optimal level based on resolution-improvement-per-token-cost ratio
- [ ] Template promotion gate: new template version must show >= 0% resolution delta (non-regression) to be promoted
- [ ] Optimization suggestions generated from benchmark failure analysis
- [ ] CLI: `tapps-mcp template optimize|ablate|compare|history`
- [ ] All new code has unit tests; integration tests use Mock evaluator from Epic 30

---

## Stories

### 31.1 — Template Version Tracker

**Points:** 5

Build a version-tracking system for AGENTS.md templates that records benchmark performance per version, enabling trend analysis and regression detection.

**Source Files:**
- `src/tapps_mcp/benchmark/template_versions.py`

**Tasks:**
- [ ] `TemplateVersion` Pydantic model:
  - `version: int` — auto-incremented
  - `content_hash: str` — SHA-256 of template content
  - `engagement_level: str` — high/medium/low
  - `benchmark_scores: BenchmarkSummary | None` — from Epic 30
  - `redundancy_score: float | None` — 0.0 (unique) to 1.0 (fully redundant)
  - `section_scores: dict[str, float] | None` — per-section ablation results
  - `created_at: str` — ISO-8601
  - `promoted: bool` — whether this version passed the promotion gate
  - `promotion_reason: str | None` — why promoted/rejected
  - `metadata: dict[str, str]` — freeform (e.g., "change_description": "removed redundant tool list")
- [ ] `TemplateVersionStore`:
  - SQLite persistence at `.tapps-mcp/benchmark/template_versions.db`
  - `record_version(content, engagement_level, metadata) -> TemplateVersion`
  - `record_scores(version_id, benchmark_scores, redundancy_score, section_scores)`
  - `get_latest(engagement_level) -> TemplateVersion | None`
  - `get_history(engagement_level, limit) -> list[TemplateVersion]`
  - `get_best(engagement_level) -> TemplateVersion | None` — highest resolution rate
  - `promote(version_id, reason) -> bool`
  - `compare(version_a, version_b) -> VersionComparison` — delta in all metrics
- [ ] Auto-version on template content change: hash comparison detects modifications
- [ ] Write ~10 unit tests: versioning, score recording, history retrieval, comparison, promotion

**Definition of Done:** Template versions tracked with benchmark scores. History queryable. Comparison works.

---

### 31.2 — Redundancy Analyzer (Enhanced)

**Points:** 5

Extend the basic redundancy scoring from Epic 30.3 into a comprehensive analysis tool that identifies specific redundant sections and suggests removals.

**Source Files:**
- `src/tapps_mcp/benchmark/redundancy.py`

**Tasks:**
- [ ] `SectionRedundancyReport` model:
  - `section_name: str`
  - `section_content: str`
  - `redundancy_score: float` — 0.0-1.0
  - `overlapping_sources: list[str]` — which repo docs overlap (e.g., "README.md lines 15-30")
  - `recommendation: str` — "keep", "reduce", "remove"
  - `unique_content: str` — the non-redundant portion
- [ ] `analyze_template_redundancy(template: str, repo_path: Path) -> TemplateRedundancyReport`:
  - Parse template into sections (split on `##` headers)
  - For each section:
    - Extract repo documentation: README.md, CONTRIBUTING.md, pyproject.toml [project.description], docstrings from key Python files, existing AGENTS.md or CLAUDE.md
    - Compute TF-IDF cosine similarity between section and each repo doc
    - Compute token-level Jaccard overlap
    - Combined score: 0.6 * cosine + 0.4 * Jaccard
    - Classify: >0.6 = "remove", 0.3-0.6 = "reduce", <0.3 = "keep"
  - Aggregate to overall template redundancy score
- [ ] `generate_reduced_template(report: TemplateRedundancyReport) -> str`:
  - Remove sections classified as "remove"
  - For "reduce" sections: strip content that overlaps with repo docs, keep unique portions
  - Preserve section structure and engagement-level language
- [ ] Redundancy gate: reject template versions with overall redundancy > 0.5
- [ ] Write ~10 unit tests: section parsing, redundancy scoring, recommendation classification, template reduction

**Definition of Done:** Per-section redundancy scored. Reduction suggestions generated. Gate enforced.

---

### 31.3 — Section Ablation Runner

**Points:** 5

Measure the marginal value of each AGENTS.md section by evaluating the template with one section removed at a time. Identifies which sections drive agent success and which are noise.

**Source Files:**
- `src/tapps_mcp/benchmark/ablation.py`

**Tasks:**
- [ ] `AblationConfig` model:
  - `base_template: str` — full template content
  - `sections: list[str]` — section names to ablate
  - `benchmark_config: BenchmarkConfig` — evaluation parameters (from Epic 30)
  - `baseline_results: list[BenchmarkResult] | None` — pre-computed full-template results
- [ ] `AblationResult` model:
  - `removed_section: str`
  - `resolution_rate: float` — with this section removed
  - `delta_vs_full: float` — change from full template (positive = section was harmful)
  - `delta_vs_none: float` — change from no-context baseline
  - `cost_delta: float` — token cost change
  - `recommendation: str` — "essential" (<-2% delta), "neutral" (-2% to +1%), "harmful" (>+1% improvement when removed)
- [ ] `run_ablation(config: AblationConfig, evaluator) -> list[AblationResult]`:
  - Run full template to establish baseline (or use provided baseline)
  - For each section: generate template-minus-section, evaluate, compute deltas
  - Rank sections by value (resolution delta when removed)
  - Total runs: N_sections + 1 (baseline)
- [ ] `AblationReport`:
  - Section value ranking (most valuable to most harmful)
  - Optimal template: full template minus harmful sections
  - Expected improvement from removing harmful sections
  - Cost savings from removing low-value sections
- [ ] Write ~8 unit tests (using MockEvaluator): ablation with known section values, ranking, report generation

**Definition of Done:** Ablation identifies per-section value. Optimal template suggested. Rankings correct.

---

### 31.4 — Engagement Level Calibrator

**Points:** 5

Determine the optimal engagement level (high/medium/low) for a given project profile by measuring the resolution-improvement-per-token-cost ratio for each level.

**Source Files:**
- `src/tapps_mcp/benchmark/engagement_calibrator.py`

**Tasks:**
- [ ] `EngagementCalibration` model:
  - `level: str` — high/medium/low
  - `resolution_rate: float`
  - `avg_token_cost: float`
  - `resolution_per_token: float` — efficiency ratio
  - `delta_vs_none: float` — improvement over no-context
  - `delta_vs_medium: float` — improvement over default (medium)
- [ ] `calibrate_engagement(benchmark_config, evaluator) -> EngagementCalibrationReport`:
  - Run evaluation for each engagement level: high, medium, low
  - Run no-context baseline
  - Compute resolution_per_token for each level
  - Recommend level with best efficiency ratio
  - Flag if any level performs worse than no-context (critical finding)
- [ ] `EngagementCalibrationReport`:
  - Per-level metrics table
  - Recommended default level with justification
  - Warning if any level degrades performance vs. no-context
  - Cost breakdown: additional tokens per level relative to baseline
- [ ] Integration with `tapps_set_engagement_level`:
  - Store calibration results in memory system (Epic 23)
  - Surface recommendation in `tapps_session_start` response when calibration data available
- [ ] Write ~8 unit tests: calibration with known level performance, recommendation logic, edge cases (all levels worse than baseline)

**Definition of Done:** Engagement levels compared by cost-benefit. Recommendation generated. Stored in memory for surfacing.

---

### 31.5 — Failure Analysis & Optimization Suggestions

**Points:** 5

Analyze benchmark failures to identify patterns and generate actionable template improvement suggestions. This closes the feedback loop by converting evaluation data into template engineering guidance.

**Source Files:**
- `src/tapps_mcp/benchmark/failure_analyzer.py`

**Tasks:**
- [ ] `FailurePattern` model:
  - `pattern_type: str` — "missing_convention", "wrong_tool_command", "redundant_distraction", "missing_dependency_info", "incorrect_test_runner"
  - `frequency: int` — how many instances exhibited this pattern
  - `affected_repos: list[str]`
  - `example_instance_ids: list[str]`
  - `suggested_fix: str` — natural language suggestion for template improvement
- [ ] `analyze_failures(results: list[BenchmarkResult], instances: list[BenchmarkInstance]) -> FailureAnalysisReport`:
  - Identify instances that failed with TAPPS context but succeeded with HUMAN or NONE
  - Correlate failures with:
    - Repo characteristics (test framework, package manager, project type)
    - Template section content vs. repo-specific needs
    - Token budget consumption (did context push out useful reasoning?)
  - Cluster failure patterns using keyword analysis on error logs
  - Generate per-pattern suggestions
- [ ] `generate_improvement_suggestions(analysis: FailureAnalysisReport, current_template: str) -> list[TemplateSuggestion]`:
  - `TemplateSuggestion`: `section`, `action` (add/modify/remove), `content`, `rationale`, `expected_impact`
  - Prioritize by frequency * severity
  - Cap at 5 suggestions per iteration (prevent over-optimization)
- [ ] Persist failure patterns in memory system for cross-session learning
- [ ] Write ~10 unit tests: failure identification, pattern clustering, suggestion generation

**Definition of Done:** Failures analyzed by pattern. Suggestions generated with rationale. Patterns persisted.

---

### 31.6 — Template Promotion Gate

**Points:** 3

Enforce quality gates on template changes: a new template version must demonstrate non-regression on the benchmark before being promoted to the active template set.

**Source Files:**
- `src/tapps_mcp/benchmark/promotion.py`

**Tasks:**
- [ ] `PromotionCriteria` model:
  - `min_resolution_delta: float` — minimum improvement vs. current active (default: 0.0, i.e., non-regression)
  - `max_redundancy: float` — maximum allowed redundancy score (default: 0.5)
  - `min_instances_evaluated: int` — minimum sample size for statistical validity (default: 20)
  - `significance_threshold: float` — p-value for McNemar's test (default: 0.1 — relaxed for small samples)
- [ ] `evaluate_promotion(candidate: TemplateVersion, current: TemplateVersion, criteria: PromotionCriteria) -> PromotionDecision`:
  - Check resolution delta meets minimum
  - Check redundancy below threshold
  - Check sample size sufficient
  - Check statistical significance if sample large enough
  - Return: `approved` (bool), `reason` (str), `warnings` (list[str])
- [ ] `auto_promote(candidate_version_id, store: TemplateVersionStore) -> bool`:
  - Evaluate candidate against current best
  - If approved: mark as promoted, update active template
  - If rejected: mark as rejected with reason
- [ ] Integration with `tapps_init` and `tapps_upgrade`:
  - When promoted template available, use it instead of default
  - Fall back to default template if no promoted version exists
- [ ] Write ~8 unit tests: promotion approval, rejection, edge cases (no current version, insufficient samples)

**Definition of Done:** Promotion gate enforces non-regression. Approved templates used by init/upgrade. Rejections documented.

---

### 31.7 — CLI Commands & MCP Tool

**Points:** 3

Expose the optimization pipeline through CLI commands and optionally as an MCP tool for LLM-driven optimization.

**Source Files:**
- `src/tapps_mcp/benchmark/cli_commands.py` (extend from Epic 30)
- `src/tapps_mcp/server_metrics_tools.py` (optional MCP tool)

**Tasks:**
- [ ] `tapps-mcp template optimize`:
  - `--engagement-level` — which level to optimize (default: all three)
  - `--iterations` — max optimization iterations (default: 3)
  - `--subset` — benchmark subset size (default: 20)
  - Pipeline: analyze redundancy -> run ablation -> generate suggestions -> apply -> evaluate -> promote/reject
- [ ] `tapps-mcp template ablate`:
  - `--engagement-level` — which level to ablate
  - `--subset` — benchmark subset size
  - Output: section value ranking table
- [ ] `tapps-mcp template compare`:
  - `--versions` — two version IDs to compare
  - `--format` — markdown, json
- [ ] `tapps-mcp template history`:
  - `--engagement-level` — filter by level
  - `--limit` — max versions to show (default: 10)
  - Output: version history with scores and promotion status
- [ ] Optional: `tapps_template_optimize` MCP tool (deferred — only add if benchmark infra proves stable)
- [ ] Write ~5 unit tests for CLI argument parsing

**Definition of Done:** CLI commands work end-to-end. History shows version progression with scores.

---

## Optimization Loop Diagram

```
                    +------------------+
                    | Current Template |
                    | (v3, medium)     |
                    +--------+---------+
                             |
                    +--------v---------+
                    | Redundancy Check |----> Flag: 2 sections > 0.6 overlap
                    +--------+---------+
                             |
                    +--------v---------+
                    | Section Ablation |----> Rank: section 4 is harmful (-1.3%)
                    +--------+---------+
                             |
                    +--------v---------+
                    | Failure Analysis |----> Pattern: missing test runner in 8/138 repos
                    +--------+---------+
                             |
                    +--------v---------+
                    | Generate v4      |----> Remove section 4, add test runner detection
                    +--------+---------+
                             |
                    +--------v---------+
                    | Benchmark v4     |----> Resolution: 48.2% (v3: 46.7%)
                    +--------+---------+
                             |
                    +--------v---------+
                    | Promotion Gate   |----> +1.5% delta, redundancy 0.31: PROMOTED
                    +--------+---------+
                             |
                    +--------v---------+
                    | v4 = Active      |
                    +------------------+
```

## Performance Targets

| Operation | Target | Notes |
|-----------|--------|-------|
| Redundancy analysis (per template) | < 5s | TF-IDF + Jaccard on < 20 documents |
| Full ablation (8 sections, 20 instances) | < 3 hours | 9 benchmark runs at ~20 min each |
| Engagement calibration (3 levels + baseline) | < 2 hours | 4 benchmark runs |
| Failure analysis | < 30s | In-memory pattern clustering |
| Promotion evaluation | < 1s | Comparison of pre-computed scores |
| Template generation (from suggestions) | < 1s | String manipulation |

## Key Design Decisions

1. **Non-regression gate, not improvement gate** — Requiring strict improvement would slow iteration. Non-regression (>= 0% delta) allows incremental changes that don't harm and accumulate small gains.
2. **Ablation before suggestion** — Removing harmful sections is more impactful than adding new content. The eth-sri study found that less content often works better.
3. **5-suggestion cap** — Over-optimization leads to overfitting to the benchmark. Small, validated changes compound better than large untested rewrites.
4. **Memory integration** — Failure patterns and calibration results persist in the memory system (Epic 23), enabling cross-session learning and multi-developer knowledge sharing.
5. **Engagement calibration as recommendation, not override** — The calibrator recommends a level but doesn't force it. Projects may have legitimate reasons to choose a specific level.

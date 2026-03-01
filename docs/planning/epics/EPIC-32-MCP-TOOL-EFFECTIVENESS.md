# Epic 32: MCP Tool Effectiveness Benchmarking

> Measure whether TappsMCP's MCP tools (scoring, gating, expert consultation, memory)
> actually improve coding agent task completion — using MCPMark-style deterministic
> evaluation and closed-loop tool recommendation tuning.

**Status:** Proposed
**Priority:** P2 — Improvement (validates tool-level value, not just template-level)
**Estimated LOE:** ~3-4 weeks (1 developer)
**Dependencies:** Epic 30 (Benchmark Infrastructure), Epic 7 (Metrics & Dashboard), Epic 5 (Adaptive Learning)
**Blocks:** None

---

## Goal

While Epic 30-31 evaluate whether TappsMCP's *generated context files* help agents, this epic evaluates whether TappsMCP's *MCP tools themselves* improve agent outcomes. When an agent calls `tapps_score_file` or `tapps_consult_expert` during a coding task, does it produce better patches? Which tools have the highest impact? Which are noise? This data feeds back into the checklist system (tool recommendations), adaptive scoring weights, and engagement-level tool requirements.

## Rationale

| Question | Current Answer | After Epic 32 |
|----------|---------------|---------------|
| Which tools improve outcomes? | Assumed all help | Measured per-tool impact |
| Are required tools truly required? | Engagement-level intuition | Data-driven tier classification |
| Does expert consultation help? | Assumed yes | Measured by domain and question type |
| Do agents over-call or under-call tools? | Unknown | Call pattern analysis vs. optimal |
| Does memory retrieval help? | Assumed yes | Measured by memory hit relevance |

## 2026 Best Practices Applied

- **MCPMark evaluation pattern** (ICLR 2026 poster, arXiv 2509.24002) — Deterministic `verify.py` scripts per task, no LLM judging. 127 tasks across 5 MCP services. TappsMCP adapts this for its own tool suite.
- **MCP-Universe metrics** (Salesforce, arXiv 2508.14704) — Success rate, evaluator score, average steps, cost tracking. Multi-track evaluation (ReAct, function calls, agent track).
- **AgentOps closed-loop monitoring** (2026 best practice) — Continuous production monitoring that closes the loop between deployment and development. Real-time feedback on tool effectiveness.
- **Self-evolving tool optimization** — EvoAgentX (EMNLP 2025) demonstrates tool mastery learning: agents improve at discovering and using tools through feedback. TappsMCP measures and improves its tool recommendations based on actual impact.
- **Pass@k stability metric** — MCPMark's contribution: measuring not just success but consistency. A tool that helps 50% of the time but hurts 50% of the time is worse than one that is neutral but consistent.

## Acceptance Criteria

- [ ] Task suite: 20+ deterministic evaluation tasks that exercise TappsMCP tools during coding workflows
- [ ] Tool impact measurement: per-tool delta in task resolution rate (with-tool vs. without-tool)
- [ ] Call pattern analyzer: identifies over-calling (wasteful) and under-calling (missed value) patterns
- [ ] Checklist calibrator: updates required/recommended/optional tool tiers based on measured impact
- [ ] Expert effectiveness tracker: measures which expert domains improve outcomes for which task types
- [ ] Memory effectiveness tracker: measures whether memory retrieval improves outcomes
- [ ] Adaptive weight feedback: feeds tool impact data into the adaptive scoring engine (Epic 5)
- [ ] Dashboard integration: tool effectiveness metrics visible in `tapps_dashboard`
- [ ] Results persist across sessions for trend analysis
- [ ] All new code has unit tests

---

## Stories

### 32.1 — Tool Evaluation Task Suite

**Points:** 8

Create a suite of deterministic evaluation tasks that exercise TappsMCP tools during realistic coding workflows. Each task has a problem, expected tool interactions, and deterministic verification.

**Source Files:**
- `src/tapps_mcp/benchmark/tool_tasks/` (new directory)
- `src/tapps_mcp/benchmark/tool_task_models.py`

**Tasks:**
- [ ] `ToolTask` model (MCPMark-inspired):
  - `task_id: str` — unique identifier
  - `category: str` — "quality", "security", "architecture", "debugging", "refactoring"
  - `description: str` — plain-language problem statement
  - `setup_files: dict[str, str]` — filename -> content for the test fixture
  - `expected_tools: list[str]` — tools an ideal agent would call
  - `verification: ToolTaskVerification` — deterministic success criteria
  - `difficulty: str` — "easy", "medium", "hard"
- [ ] `ToolTaskVerification`:
  - `check_type: str` — "file_content", "score_threshold", "test_pass", "no_security_issues"
  - `expected_file: str | None` — file to check
  - `expected_content_patterns: list[str] | None` — regex patterns that must be present
  - `min_quality_score: float | None` — minimum overall score
  - `custom_verify: str | None` — Python expression for custom verification
- [ ] Create 20+ tasks across categories:
  - **Quality tasks** (5): Fix lint issues, reduce complexity, improve maintainability
  - **Security tasks** (4): Fix SQL injection, remove hardcoded secrets, fix path traversal, secure API endpoint
  - **Architecture tasks** (4): Resolve circular import, extract shared module, implement interface, add error handling
  - **Debugging tasks** (4): Fix failing test, fix type error, fix race condition, fix off-by-one
  - **Refactoring tasks** (4): Rename across files, extract function, simplify conditional, modernize syntax
- [ ] Each task includes:
  - `meta.json` — task metadata
  - `description.md` — agent-facing problem statement
  - `verify.py` — deterministic verification script
  - `fixtures/` — source files for the task
- [ ] Write ~8 unit tests: task loading, verification execution, fixture setup

**Definition of Done:** 20+ tasks created with deterministic verification. Tasks cover all tool categories. Verification scripts pass on known-good solutions.

---

### 32.2 — Tool Impact Evaluator

**Points:** 8

Measure the causal impact of individual TappsMCP tools on task resolution by running tasks with and without specific tool access. This is the core measurement that determines tool value.

**Source Files:**
- `src/tapps_mcp/benchmark/tool_evaluator.py`

**Tasks:**
- [ ] `ToolCondition` enum:
  - `ALL_TOOLS` — agent has access to all TappsMCP tools
  - `NO_TOOLS` — agent works without TappsMCP (baseline)
  - `SINGLE_TOOL` — agent has access to only one specific tool
  - `ALL_MINUS_ONE` — agent has all tools except one specific tool
- [ ] `ToolImpactResult` model:
  - `task_id: str`
  - `condition: ToolCondition`
  - `tool_name: str | None` — the specific tool being tested
  - `resolved: bool`
  - `tools_called: list[str]` — which tools the agent actually called
  - `call_count: int` — total tool calls
  - `token_usage: int`
  - `duration_ms: int`
- [ ] `evaluate_tool_impact(task, tool_name, evaluator) -> ToolImpactReport`:
  - Run task with ALL_TOOLS → baseline resolution
  - Run task with ALL_MINUS_ONE (remove `tool_name`) → resolution without tool
  - Impact = baseline_resolution - without_tool_resolution
  - Positive impact = tool helps; negative impact = tool hurts; zero = tool is neutral
- [ ] `evaluate_all_tools(tasks, evaluator) -> ToolEffectivenessReport`:
  - For each tool in TappsMCP's tool set:
    - Run all tasks with and without this tool
    - Compute per-tool impact score
    - Compute per-category impact (tool X helps quality tasks but not security tasks)
  - Rank tools by aggregate impact
  - Identify tools that never get called (agent ignores recommendation)
  - Identify tools that get called but don't improve outcomes (noise)
- [ ] Pass@k stability: run each condition k times (default k=3), compute consistency
- [ ] Write ~12 unit tests: impact calculation, ranking, stability metrics, edge cases

**Definition of Done:** Per-tool impact measured. Tools ranked by effectiveness. Stability computed via pass@k.

---

### 32.3 — Call Pattern Analyzer

**Points:** 5

Analyze agent tool-calling patterns to identify over-calling (wasteful), under-calling (missed opportunities), and mis-ordering (calling tools in suboptimal sequence).

**Source Files:**
- `src/tapps_mcp/benchmark/call_patterns.py`

**Tasks:**
- [ ] `CallPattern` model:
  - `task_id: str`
  - `tools_called: list[tuple[str, int]]` — (tool_name, call_order) sequence
  - `tools_expected: list[str]` — optimal tool set from task definition
  - `overcalls: list[str]` — tools called but not in expected set
  - `undercalls: list[str]` — tools in expected set but not called
  - `call_efficiency: float` — len(expected & called) / len(called)
  - `sequence_optimal: bool` — whether tools were called in an effective order
- [ ] `analyze_call_patterns(results: list[ToolImpactResult], tasks: list[ToolTask]) -> CallPatternReport`:
  - Per-task analysis: compare actual calls to expected
  - Aggregate patterns:
    - Most over-called tools (agents call them but they don't help)
    - Most under-called tools (agents skip them but they would help)
    - Common call sequences that correlate with success
    - Common call sequences that correlate with failure
  - Efficiency metrics: average call efficiency across tasks
- [ ] `generate_call_recommendations(report: CallPatternReport) -> list[CallRecommendation]`:
  - `CallRecommendation`: `tool_name`, `recommendation` (increase/decrease/reorder), `rationale`, `expected_impact`
  - Feeds into checklist calibration (Story 32.4)
- [ ] Integration with existing `CallTracker` in `tools/checklist.py`:
  - Store optimal call patterns for comparison during live sessions
  - Surface pattern recommendations in checklist responses
- [ ] Write ~10 unit tests: pattern detection, efficiency calculation, recommendation generation

**Definition of Done:** Over/under-calling detected. Sequences analyzed. Recommendations generated.

---

### 32.4 — Checklist Calibrator

**Points:** 5

Use tool impact data to recalibrate which tools are required, recommended, or optional in the checklist system across engagement levels. Replaces intuition-based tier assignment with data-driven classification.

**Source Files:**
- `src/tapps_mcp/benchmark/checklist_calibrator.py`
- `src/tapps_mcp/tools/checklist.py` (update tier maps)

**Tasks:**
- [ ] `ToolTierClassification` model:
  - `tool_name: str`
  - `measured_impact: float` — average resolution delta
  - `measured_cost: float` — average token cost of using this tool
  - `call_frequency: float` — how often agents call this tool
  - `recommended_tier: str` — "required", "recommended", "optional"
  - `current_tier: str` — what the checklist currently says
  - `tier_change: str | None` — "promoted", "demoted", "unchanged"
  - `justification: str`
- [ ] `calibrate_tiers(tool_effectiveness: ToolEffectivenessReport, call_patterns: CallPatternReport) -> ChecklistCalibration`:
  - Classification rules:
    - Impact > 3% resolution improvement AND cost < 15% token overhead → "required"
    - Impact > 0% resolution improvement OR frequently called by successful agents → "recommended"
    - Impact <= 0% or rarely called → "optional"
  - Per-engagement-level adjustment:
    - High: more tools required (lower impact threshold: 1%)
    - Medium: balanced (default thresholds)
    - Low: fewer required (higher threshold: 5%)
  - Flag controversial changes (tool currently "required" being demoted)
- [ ] `apply_calibration(calibration: ChecklistCalibration, dry_run: bool = True) -> list[TierChange]`:
  - Generate updated `TASK_TOOL_MAP_HIGH`, `TASK_TOOL_MAP_MEDIUM`, `TASK_TOOL_MAP_LOW`
  - Dry run mode: show proposed changes without applying
  - Apply mode: update `tools/checklist.py` tier maps (requires confirmation)
- [ ] Store calibration in memory system for audit trail
- [ ] Write ~10 unit tests: tier classification logic, engagement-level adjustment, dry-run output

**Definition of Done:** Tiers recalibrated from data. Changes reviewable in dry-run. Tier maps updatable.

---

### 32.5 — Expert & Memory Effectiveness Trackers

**Points:** 5

Measure whether expert consultations and memory retrievals improve agent outcomes, broken down by domain and query type.

**Source Files:**
- `src/tapps_mcp/benchmark/expert_tracker.py`
- `src/tapps_mcp/benchmark/memory_tracker.py`

**Tasks:**
- [ ] `ExpertEffectiveness` model:
  - `domain: str` — expert domain (security, testing, etc.)
  - `consultations: int` — number of consultations
  - `resolution_with: float` — resolution rate when expert consulted
  - `resolution_without: float` — resolution rate when expert not consulted
  - `impact: float` — delta
  - `avg_confidence: float` — average expert confidence score
  - `high_confidence_impact: float` — impact when confidence > 0.7
  - `low_confidence_impact: float` — impact when confidence < 0.4
- [ ] `analyze_expert_effectiveness(results, tasks) -> ExpertEffectivenessReport`:
  - Per-domain impact analysis
  - Confidence-stratified analysis: do high-confidence answers help more?
  - Task-type correlation: which domains help for which task categories?
  - Identify domains that get consulted but don't improve outcomes
  - Identify task types that would benefit from consultation but agents skip
- [ ] `MemoryEffectiveness` model:
  - `memory_tier: str` — architectural, pattern, context
  - `retrievals: int`
  - `resolution_with_retrieval: float`
  - `resolution_without_retrieval: float`
  - `impact: float`
  - `relevance_score: float` — BM25 relevance of retrieved memories
  - `stale_retrieval_rate: float` — percentage of retrievals that returned stale data
- [ ] `analyze_memory_effectiveness(results, tasks) -> MemoryEffectivenessReport`:
  - Per-tier impact analysis
  - Relevance correlation: do higher-relevance retrievals help more?
  - Staleness impact: do stale memories hurt?
  - Memory seeding effectiveness: do pre-seeded memories help first-session agents?
- [ ] Feed expert effectiveness data into adaptive domain weights (Epic 5)
- [ ] Write ~10 unit tests: expert impact calculation, memory impact calculation, domain correlation

**Definition of Done:** Expert and memory effectiveness measured per domain/tier. Data feeds adaptive system.

---

### 32.6 — Adaptive Weight Feedback Loop

**Points:** 5

Close the loop between benchmark measurements and TappsMCP's adaptive scoring engine. Tool impact data from benchmarks feeds into the weight distribution system, improving scoring accuracy over time.

**Source Files:**
- `src/tapps_mcp/benchmark/adaptive_feedback.py`
- `src/tapps_mcp/adaptive/scoring_engine.py` (extend)

**Tasks:**
- [ ] `BenchmarkFeedback` model:
  - `tool_name: str`
  - `impact_score: float` — measured resolution impact
  - `cost_ratio: float` — token cost / resolution improvement
  - `category_impacts: dict[str, float]` — per-scoring-category impact
  - `source: str` — "benchmark" (vs "user_feedback" from existing system)
  - `sample_size: int` — number of instances in the measurement
  - `confidence: float` — statistical confidence in the measurement
- [ ] `generate_scoring_feedback(tool_effectiveness: ToolEffectivenessReport) -> list[BenchmarkFeedback]`:
  - For each scoring category (complexity, security, maintainability, test_coverage, performance, structure, devex):
    - Correlate category scores with task resolution rates
    - Compute weight adjustment suggestions
  - For tools that improve specific categories:
    - Link tool impact to category weight (e.g., `tapps_security_scan` impact correlates with security category weight)
- [ ] Extend `AdaptiveScoringEngine.adjust_weights()`:
  - Accept `benchmark_feedback: list[BenchmarkFeedback]` as additional input
  - Blend user feedback (existing) with benchmark feedback at configurable ratio (default: 0.6 benchmark, 0.4 user)
  - Require minimum sample sizes before benchmark feedback influences weights
- [ ] Weight audit log: record every weight adjustment with source (user vs. benchmark), before/after values, and justification
- [ ] Write ~10 unit tests: feedback generation, weight blending, minimum sample enforcement, audit logging

**Definition of Done:** Benchmark data feeds adaptive weights. Blending with user feedback works. Audit trail recorded.

---

### 32.7 — Dashboard Integration & Reporting

**Points:** 3

Surface tool effectiveness metrics in the existing dashboard system (Epic 7) and generate actionable reports for project maintainers.

**Source Files:**
- `src/tapps_mcp/benchmark/tool_report.py`
- `src/tapps_mcp/metrics/dashboard.py` (extend)

**Tasks:**
- [ ] New dashboard section: "Tool Effectiveness"
  - Per-tool impact ranking with sparkline trend
  - Call pattern efficiency score
  - Checklist calibration status (last calibrated, changes pending)
  - Expert domain effectiveness heatmap
  - Memory retrieval relevance trend
- [ ] `generate_tool_effectiveness_report(format: str) -> str`:
  - Markdown format for human review
  - JSON format for programmatic consumption
  - Sections: tool ranking, call patterns, expert effectiveness, memory effectiveness, calibration recommendations
- [ ] CLI: `tapps-mcp benchmark tools`:
  - `--report` — generate full effectiveness report
  - `--rank` — show tool impact ranking only
  - `--calibrate` — run checklist calibration
  - `--feedback` — apply adaptive weight feedback
- [ ] Integration with `tapps_stats`:
  - Add tool effectiveness metrics to stats output when benchmark data available
- [ ] Write ~5 unit tests: dashboard section rendering, report generation, CLI arguments

**Definition of Done:** Tool effectiveness visible in dashboard. Reports generated. CLI commands work.

---

## Evaluation Architecture

```
+-------------------+     +-------------------+     +-------------------+
|   Tool Task       |     |   Tool Impact     |     |   Call Pattern    |
|   Suite (20+)     |---->|   Evaluator       |---->|   Analyzer        |
|   (32.1)          |     |   (32.2)          |     |   (32.3)          |
+-------------------+     +-------------------+     +-------------------+
                                    |                         |
                                    v                         v
                          +-------------------+     +-------------------+
                          | Expert/Memory     |     | Checklist         |
                          | Trackers          |     | Calibrator        |
                          | (32.5)            |     | (32.4)            |
                          +-------------------+     +-------------------+
                                    |                         |
                                    v                         v
                          +-------------------+     +-------------------+
                          | Adaptive Weight   |     | Dashboard &       |
                          | Feedback Loop     |     | Reporting         |
                          | (32.6)            |     | (32.7)            |
                          +-------------------+     +-------------------+
                                    |                         |
                                    v                         v
                          +-------------------------------------------+
                          |          Improved TappsMCP Tools           |
                          | (better weights, calibrated checklists,   |
                          |  data-driven recommendations)             |
                          +-------------------------------------------+
```

## Performance Targets

| Operation | Target | Notes |
|-----------|--------|-------|
| Single task evaluation (all tools) | < 5 min | Agent + tool calls + verification |
| Single task evaluation (no tools) | < 3 min | Agent only + verification |
| Full tool impact (20 tasks, 28 tools) | < 24 hours | 20 * (28 ALL_MINUS_ONE + 1 baseline + 1 NO_TOOLS) = 600 runs |
| Subset impact (5 tasks, 10 tools) | < 2 hours | For fast iteration |
| Call pattern analysis | < 10s | In-memory analysis of stored results |
| Checklist calibration | < 5s | Statistical classification |
| Dashboard rendering | < 2s | Aggregation from stored metrics |

## File Layout

```
src/tapps_mcp/benchmark/
    tool_task_models.py        # ToolTask, ToolTaskVerification models
    tool_evaluator.py          # ToolImpactEvaluator, ToolCondition
    call_patterns.py           # CallPatternAnalyzer, CallRecommendation
    checklist_calibrator.py    # ChecklistCalibrator, ToolTierClassification
    expert_tracker.py          # ExpertEffectivenessAnalyzer
    memory_tracker.py          # MemoryEffectivenessAnalyzer
    adaptive_feedback.py       # BenchmarkFeedback, weight loop integration
    tool_report.py             # Report generation for dashboard

src/tapps_mcp/benchmark/tool_tasks/    # Task definitions
    quality/
        fix-lint-issues/
            meta.json
            description.md
            verify.py
            fixtures/
        reduce-complexity/
            ...
    security/
        fix-sql-injection/
            ...
    architecture/
        ...
    debugging/
        ...
    refactoring/
        ...

tests/unit/test_tool_evaluator.py
tests/unit/test_call_patterns.py
tests/unit/test_checklist_calibrator.py
tests/unit/test_expert_tracker.py
tests/unit/test_adaptive_feedback.py
tests/integration/test_tool_benchmark_pipeline.py
```

## Key Design Decisions

1. **ALL_MINUS_ONE over SINGLE_TOOL** — Removing one tool from a full suite measures realistic causal impact. Testing a single tool in isolation doesn't capture interactions (e.g., `tapps_score_file` is more useful when `tapps_quality_gate` is also available).
2. **Deterministic verification only** — No LLM judging for task success. `verify.py` scripts use file content checks, score thresholds, and test execution. Consistent with TappsMCP's no-LLM-in-toolchain principle.
3. **Pass@k for stability** — A tool that helps 50% of the time is worse than one that helps 30% consistently. Stability matters for trust and adoption.
4. **Conservative calibration thresholds** — Requiring >3% impact for "required" tier prevents noise-driven tier changes. The 15% cost threshold prevents recommending expensive-but-marginal tools.
5. **Blended feedback ratio** — 60% benchmark / 40% user feedback balances controlled measurement with real-world usage patterns. User feedback captures scenarios benchmarks miss.
6. **Audit trail** — Every weight adjustment and tier change is logged with justification. This supports debugging if scoring quality degrades after an automatic adjustment.

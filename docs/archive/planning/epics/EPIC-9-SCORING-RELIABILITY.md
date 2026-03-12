# Epic 9: Scoring Reliability & Actionable Feedback

**Status:** Complete (6 of 6 stories complete)
**Priority:** P0 - Critical (scoring accuracy directly impacts all tool value)
**Estimated LOE:** ~2-3 weeks (1 developer)
**Dependencies:** Epic 1 (Core Quality), Epic 7 (Metrics)
**Blocks:** None

---

## Goal

Make TappsMCP's scoring tools reliable, informative, and actionable. Users should get accurate scores, understand why they scored that way, and know exactly what to fix.

## Why This Epic Exists

After a self-review of TappsMCP's scoring tools during a codebase optimization effort, five reliability and UX issues were identified:

1. **Radon subprocess silently fails** in the MCP server's async context, causing all files to receive fallback scores (MI=50.0, AST-based complexity). This makes `tapps_quality_gate` unreliable.
2. **Test coverage heuristic is brittle** - only matches `test_{stem}.py` / `{stem}_test.py`, missing common patterns like `test_server_tools.py` for `server.py`.
3. **Complexity uses only max CC** - one outlier function tanks the entire file's score.
4. **Tool failures are silent** - `degraded=True` gives no explanation of why tools failed.
5. **No fallback scoring mode** - when subprocesses fail, there's no alternative.

## LLM Error Sources Addressed

| Error Source | How This Epic Helps |
|---|---|
| Inaccurate scoring | Fix radon subprocess + add direct mode = reliable scores |
| False test coverage gaps | Improved heuristic catches real test files |
| Misleading complexity | Blended CC reflects whole-file complexity, not just worst function |
| Silent degradation | Tool error details enable diagnosis and resolution |
| No remediation guidance | Actionable suggestions tell the LLM exactly what to fix |

## Acceptance Criteria

- [x] Radon produces real CC/MI values through the MCP server, or falls back to library-based analysis
- [x] Test coverage heuristic finds test files with non-standard naming patterns
- [x] Complexity score uses blended max/avg CC with function name details
- [x] Tool failures include human-readable error reasons per tool
- [x] `tapps_score_file(mode="direct")` bypasses subprocess execution entirely
- [x] Each scoring category generates actionable improvement suggestions
- [x] All changes covered by unit tests
- [x] Zero mypy/ruff errors

---

## Stories

### 9.1 - Fix Radon Subprocess in Async Context

**Points:** 5
**Priority:** Critical
**Status:** Complete

radon subprocess fails silently in the MCP server's async context. `run_radon_cc_async` and `run_radon_mi_async` return empty/fallback results, causing all files to score with MI=50.0 (fallback) and `_ast_complexity` (fallback). Radon works when called directly from Python (`asyncio.run()`).

**Source Files:**
- `src/tapps_mcp/tools/radon.py`
- `src/tapps_mcp/tools/parallel.py`
- `src/tapps_mcp/tools/subprocess_runner.py`

**Tasks:**
- [x] Add diagnostic logging in `tools/radon.py` when stdout is empty but returncode is 0
- [x] Add `stderr` capture and logging in `run_radon_cc_async` / `run_radon_mi_async`
- [x] Add `error_details` field to `ParallelResults` to surface per-tool failure reasons
- [x] Add fallback: try radon as Python library (`radon.complexity`, `radon.metrics`) when subprocess fails
- [x] Add `radon_errors` to `ScoreResult` or `ParallelResults` for diagnostics

**Implementation Notes:**
- Added `_is_radon_importable()` using `importlib.util.find_spec` with cached result
- Added `_radon_cc_direct()` using `radon.complexity.cc_visit()` for direct CC analysis
- Added `_radon_mi_direct()` using `radon.metrics.mi_visit()` for direct MI analysis
- Added `_read_source()` helper for safe file reading
- `run_radon_cc_async` and `run_radon_mi_async` now fall back to direct library on empty output or timeout
- Diagnostic logging includes returncode, stderr, and fallback method used
- Added `"radon", "radon.*"` to mypy `ignore_missing_imports` in pyproject.toml
- 10 new tests in `test_radon.py` (5 async fallback + 5 direct fallback)

**Definition of Done:** radon produces real CC/MI values when invoked through the MCP server, or falls back to library-based analysis with clear error reporting.

---

### 9.2 - Improve Test Coverage Heuristic

**Points:** 3
**Priority:** Critical
**Status:** Complete

Current heuristic only matches `test_{stem}.py` / `{stem}_test.py` in 4 directories. Misses common patterns like `test_server_tools.py` for `server.py`, `test_validators.py` for `dockerfile.py`.

**Source Files:**
- `src/tapps_mcp/scoring/scorer.py` (`_coverage_heuristic`)

**Tasks:**
- [x] Add glob-based fuzzy matching: `test_*{stem}*.py` in test directories
- [x] Add `details["test_files_found"]` list to the test_coverage CategoryScore
- [x] Implement graduated scoring: 0 (no tests), 3 (fuzzy match), 5 (exact match), 7 (multiple test files)

**Implementation Notes:**
- `_coverage_heuristic` rewritten with three-tier matching: exact -> fuzzy glob -> no match
- Graduated scoring: 7 (multiple test files), 5 (exact match), 3 (fuzzy match), 0 (no tests)
- Fuzzy glob pattern `test_*{stem}*.py` catches `test_server_tools.py` for `server.py`
- `details["test_files_found"]` populated with matched test file paths
- Reverse search not implemented (glob matching sufficient for all identified cases)
- 4 new tests in `test_scorer.py`

**Definition of Done:** Files with mismatched test names (e.g., `test_server_tools.py` for `server.py`) score > 0 for test_coverage without alias files.

---

### 9.3 - Use Average CC Alongside Max CC

**Points:** 3
**Priority:** Important
**Status:** Complete

Current `calculate_complexity_score` uses only `max_cc / 5.0`. One outlier function tanks the whole file. A file with 1 function at CC=19 scores the same as a file with 20 functions at CC=19.

**Source Files:**
- `src/tapps_mcp/tools/radon.py` (`calculate_complexity_score`)
- `src/tapps_mcp/scoring/scorer.py` (`_build_categories`)

**Tasks:**
- [x] Add `avg_cc` calculation in `calculate_complexity_score`
- [x] Use blended formula: `0.7 * max_cc + 0.3 * avg_cc` (still penalizes outliers but less harshly)
- [x] Add `details["max_cc"]`, `details["avg_cc"]`, `details["max_cc_function"]` to complexity CategoryScore
- [x] Update `_build_categories` in scorer.py to pass function-level details

**Implementation Notes:**
- `calculate_complexity_score` now computes `blended = 0.7 * max_cc + 0.3 * avg_cc`
- Module-level constants `_BLEND_MAX = 0.7` and `_BLEND_AVG = 0.3`
- `_build_categories` enriches complexity details with `max_cc`, `avg_cc`, `max_cc_function`
- 3 new tests in `TestBlendedComplexity` class (single entry, many low + one high, all same)
- Existing test updated from `test_uses_max_complexity` to `test_uses_blended_complexity`

**Definition of Done:** Complexity score reflects overall file complexity, not just worst function. Details include both max and avg CC with the function name.

---

### 9.4 - Surface Tool Failure Details

**Points:** 2
**Priority:** Important
**Status:** Complete

When tools fail, `degraded=True` and `missing_tools=["radon"]` are set, but no explanation of *why* the tool failed (timeout, not found, crash, empty output).

**Source Files:**
- `src/tapps_mcp/tools/parallel.py` (`ParallelResults`, `run_all_tools`)
- `src/tapps_mcp/scoring/models.py` (`ScoreResult`)
- `src/tapps_mcp/server.py` (`tapps_score_file`, `tapps_quality_gate`)

**Tasks:**
- [x] Add `tool_errors: dict[str, str]` field to `ParallelResults`
- [x] In `run_all_tools`, capture error reason per tool: "timeout", "not_found", "empty_output", "parse_error", exception message
- [x] Surface `tool_errors` in `ScoreResult` and in `tapps_score_file` / `tapps_quality_gate` responses
- [x] Log structured error details for debugging

**Implementation Notes:**
- `tool_errors: dict[str, str]` added to both `ParallelResults` and `ScoreResult`
- `_mark_missing()` helper records `"not_found"` per tool
- Exception errors captured as `"{ExcType}: {msg}"` format
- Gather timeout recorded as `"timeout after {N}s"`
- `tool_errors` surfaced in `tapps_score_file` and `tapps_quality_gate` MCP responses
- `_assign_result()` helper dispatches results to correct field
- 2 new tests in `test_parallel.py`

**Definition of Done:** When a tool fails, the response includes a human-readable reason per tool.

---

### 9.5 - Direct Scoring Mode

**Points:** 5
**Priority:** Important
**Status:** Complete

Bypass subprocess execution entirely by importing radon/ruff as Python libraries for in-process analysis. Avoids the entire subprocess reliability problem.

**Source Files:**
- `src/tapps_mcp/tools/radon_direct.py` (NEW)
- `src/tapps_mcp/tools/ruff_direct.py` (NEW)
- `src/tapps_mcp/tools/parallel.py`
- `src/tapps_mcp/scoring/scorer.py`
- `src/tapps_mcp/server.py`

**Tasks:**
- [x] Create `tools/radon_direct.py`: import `radon.complexity` and `radon.metrics` directly
- [x] Create `tools/ruff_direct.py`: use `ruff` as library if available (or keep subprocess as primary)
- [x] Add `mode: str = "subprocess"` parameter to `run_all_tools` ("subprocess" | "direct" | "auto")
- [x] "auto" mode: try subprocess first, fall back to direct import
- [x] Add `mode` parameter to `tapps_score_file` tool

**Implementation Notes:**
- `radon_direct.py`: `cc_direct()` uses `radon.complexity.cc_visit()`, `mi_direct()` uses `radon.metrics.mi_visit()` - pure library calls, no subprocess
- `ruff_direct.py`: ruff has no Python library API (Rust binary), uses `subprocess.run` in `asyncio.to_thread` for reliable sync execution in async contexts
- `parallel.py` `_run_direct()`: radon via library, ruff via sync subprocess in thread pool, mypy/bandit via `asyncio.to_thread` wrapping existing sync functions
- When radon library is unavailable in direct mode, falls back to async subprocess with `tool_errors["radon"] = "library_unavailable, using subprocess fallback"`
- `mode` parameter threaded through `server.py` -> `scorer.py` -> `parallel.py`
- 14 new tests in `test_radon_direct.py`, 6 new tests in `test_ruff_direct.py`, 8 new tests in `test_parallel.py` (TestDirectMode class)
- radon not installed in test venv - tests use `sys.modules` injection for mock radon modules

**Definition of Done:** `tapps_score_file(mode="direct")` produces accurate scores without subprocess execution.

---

### 9.6 - Actionable Suggestions Per Category

**Points:** 3
**Priority:** Nice to Have (implemented first as proof of concept)
**Status:** Complete

Each scoring category generates specific, actionable suggestions explaining what to fix and how to improve the score. Suggestions are surfaced in `tapps_score_file` and `tapps_quality_gate` responses.

**Source Files:**
- `src/tapps_mcp/scoring/models.py`
- `src/tapps_mcp/scoring/scorer.py`
- `src/tapps_mcp/server.py`
- `src/tapps_mcp/gates/evaluator.py`

**Tasks:**
- [x] Add `suggestions: list[str]` field to `CategoryScore` model
- [x] Enrich `details` dict with data needed for suggestion generation (max_cc_function, issues_found, stem)
- [x] Implement `_suggest_complexity()`, `_suggest_security()`, `_suggest_maintainability()`, `_suggest_test_coverage()`, `_suggest_performance()`, `_suggest_structure()`, `_suggest_devex()` helper functions
- [x] Wire suggestions into `tapps_score_file` and `tapps_quality_gate` responses
- [x] Add ~10 unit tests for suggestion generation

**Implementation Notes:**
- 7 `_suggest_*` functions with named threshold constants (`_CC_HIGH=10`, `_CC_MODERATE=5`, `_MI_VERY_LOW=20`, `_MI_LOW=40`, `_FILE_LONG_LINES=300`, `_SCORE_LOW=5`)
- Complexity suggestions reference specific function names and CC values from enriched details
- Performance suggestions reference detected issues (nested loops, deep nesting, large functions)
- Test coverage suggestions include expected test file path from `details["stem"]`
- `tapps_score_file` response includes per-category `suggestions` + top-level aggregated list
- `tapps_quality_gate` includes suggestions for failing categories
- `evaluator.py` adds category suggestions to warnings with `[category_name]` prefix
- 26 new tests across 9 test classes in `test_scorer.py`

**Definition of Done:** Every scored file includes actionable suggestions for categories scoring below thresholds. Suggestions reference specific functions, thresholds, and remediation steps.

---

## Performance Targets

| Tool | SLA |
|---|---|
| `tapps_score_file(quick=True)` | < 500 ms |
| `tapps_score_file` (full) | < 5 s |
| `tapps_score_file(mode="direct")` | < 2 s |
| `tapps_quality_gate` | < 6 s |

## Key Dependencies

- `radon` (Python library for CC/MI - already installed)
- `ruff` (linter - already installed)
- `mypy` (type checker - already installed)
- `bandit` (security scanner - already installed)

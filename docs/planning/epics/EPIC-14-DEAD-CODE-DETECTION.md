# Epic 14: Dead Code Detection (Vulture)

**Status:** Complete - 3 source files (vulture.py, dead_code.py + scorer integration), 39 tests, tapps_dead_code tool
**Priority:** P0 — Critical (AI assistants generate significant amounts of unused code)
**Estimated LOE:** ~2-3 weeks (1 developer)
**Dependencies:** Epic 0 (Foundation), Epic 1 (Core Quality)
**Blocks:** None

---

## Goal

Integrate Vulture for dead code detection — unused functions, classes, variables, imports, and unreachable code. Surface findings in scoring, provide a standalone `tapps_dead_code` tool, and feed results into the maintainability/structure scoring categories.

## Why This Epic Exists

AI coding assistants routinely generate dead code:

1. **Unused imports** — added "just in case" during generation
2. **Orphaned functions** — refactored code leaves behind the old implementation
3. **Unreachable branches** — code after return/raise/break that can never execute
4. **Unused variables** — intermediate variables from earlier reasoning steps
5. **Stale exports** — `__all__` entries or re-exports for deleted symbols

Studies show AI-generated code contains **1.7x more total issues** than human-written code, with dead code being a leading category. TappsMCP currently has **no dead code detection capability** — this is a genuine gap.

Vulture is the most mature Python dead code detector (5,300+ GitHub stars, actively maintained, confidence scoring per finding). Its confidence scores (60-100%) align perfectly with TappsMCP's scoring model.

## LLM Error Sources Addressed

| Error Source | How This Epic Helps |
|---|---|
| Unused imports | Vulture detects imports never referenced in the module |
| Orphaned functions | Vulture finds functions/classes with zero call sites |
| Unreachable code | Vulture flags code after return/raise/break/continue |
| Stale variables | Vulture finds assigned-but-never-read variables |
| Code bloat | Dead code inflates file size, reduces maintainability score |

## Acceptance Criteria

- [ ] Vulture integration follows existing tool wrapper pattern (`tools/vulture.py`)
- [ ] `tapps_dead_code` tool: standalone dead code scan with confidence thresholds
- [ ] Dead code findings feed into `maintainability` and `structure` scoring categories
- [ ] Graceful degradation when vulture is not installed (`degraded: true`)
- [ ] Configurable confidence threshold (default 80%)
- [ ] Whitelist support for intentional "unused" code (test fixtures, CLI entry points)
- [ ] Findings include file path, line number, name, type (function/class/import/variable), confidence
- [ ] Added to `tools/parallel.py` for concurrent execution
- [ ] Added to `tools/tool_detection.py` for auto-discovery
- [ ] All changes covered by unit tests
- [ ] Zero mypy/ruff errors

---

## Stories

### 14.1 — Vulture Tool Wrapper

**Points:** 5
**Priority:** Critical
**Status:** Planned

Create the async subprocess wrapper for vulture, following the same pattern as `tools/ruff.py`, `tools/bandit.py`, and `tools/radon.py`.

**Source Files:**
- `src/tapps_mcp/tools/vulture.py` (NEW)
- `src/tapps_mcp/tools/tool_detection.py`

**Tasks:**
- [ ] Create `tools/vulture.py` with `run_vulture_async(file_path, min_confidence=80, whitelist_paths=None) -> list[DeadCodeFinding]`
- [ ] Define `DeadCodeFinding` dataclass: `file_path`, `line`, `name`, `finding_type` (function/class/import/variable/unreachable_code/attribute), `confidence`, `message`
- [ ] Parse vulture's `--json` output format (available since vulture 2.x)
- [ ] If vulture lacks `--json`, parse line-based output: `path:line: unused {type} '{name}' (confidence: XX%)`
- [ ] Handle timeout (default 30s), not-installed, and empty-output cases
- [ ] Add `"vulture"` to `tool_detection.py` discovery
- [ ] Add vulture to optional dependencies in `pyproject.toml`

**Implementation Notes:**
- Vulture CLI: `vulture path/ --min-confidence 80`
- Output format per line: `path.py:42: unused function 'helper' (60% confidence)`
- Parse with regex: `^(.+):(\d+): unused (\w[\w\s]*) '([^']+)' \((\d+)% confidence\)$`
- Subprocess pattern matches `run_bandit_check_async` — use `asyncio.create_subprocess_exec`
- `shutil.which("vulture")` for detection

**Definition of Done:** `run_vulture_async()` returns parsed dead code findings with confidence scores. Graceful degradation when vulture is not installed.

---

### 14.2 — Parallel Execution Integration

**Points:** 3
**Priority:** Critical
**Status:** Planned

Add vulture to the parallel tool execution pipeline so dead code analysis runs concurrently with ruff, mypy, bandit, and radon.

**Source Files:**
- `src/tapps_mcp/tools/parallel.py`
- `src/tapps_mcp/scoring/models.py`

**Tasks:**
- [ ] Add `dead_code: list[DeadCodeFinding]` field to `ParallelResults`
- [ ] Add vulture to `run_all_tools()` — runs concurrently with other tools via `asyncio.gather`
- [ ] Handle vulture not-installed: set `degraded=True`, add to `missing_tools`, record in `tool_errors`
- [ ] Add `dead_code_findings: list[DeadCodeFinding]` field to `ScoreResult`
- [ ] Thread dead code results through scorer to `ScoreResult`

**Implementation Notes:**
- Vulture is optional — its absence should NOT block scoring
- Add alongside existing gather: `ruff_task, mypy_task, bandit_task, radon_cc_task, radon_mi_task, vulture_task`
- Direct mode: vulture has a Python API (`vulture.core.Vulture`) — could add `vulture_direct.py` later

**Definition of Done:** `run_all_tools()` includes vulture in the parallel execution. Missing vulture degrades gracefully.

---

### 14.3 — Scoring Integration

**Points:** 5
**Priority:** Critical
**Status:** Planned

Feed vulture findings into the existing 7-category scoring model, enhancing the `maintainability` and `structure` categories.

**Source Files:**
- `src/tapps_mcp/scoring/scorer.py`
- `src/tapps_mcp/scoring/constants.py`

**Tasks:**
- [ ] Add dead code penalty to `maintainability` category: each high-confidence finding (>=80%) reduces score
- [ ] Add dead code penalty to `structure` category: unused imports and unreachable code indicate poor structure
- [ ] Define penalty constants: `DEAD_CODE_PENALTY_PER_FINDING = 2`, `DEAD_CODE_MAX_PENALTY = 20`, `UNREACHABLE_CODE_PENALTY = 5`
- [ ] Add `details["dead_code_count"]`, `details["dead_code_types"]` to affected category scores
- [ ] Generate suggestions: "Remove unused function 'helper' at line 42 (90% confidence)"
- [ ] Weight by confidence: findings at 60% penalize less than findings at 100%

**Implementation Notes:**
- Penalty formula: `sum(finding.confidence / 100 * DEAD_CODE_PENALTY_PER_FINDING)`, capped at `DEAD_CODE_MAX_PENALTY`
- Split penalty: 60% to maintainability, 40% to structure
- Unreachable code gets an extra `UNREACHABLE_CODE_PENALTY` since it indicates logic errors
- Suggestions reference specific line numbers and symbol names

**Definition of Done:** Dead code findings reduce maintainability and structure scores proportionally. Suggestions are actionable with line numbers.

---

### 14.4 — Standalone `tapps_dead_code` Tool

**Points:** 3
**Priority:** Important
**Status:** Planned

Expose a dedicated MCP tool for on-demand dead code scanning, separate from the full scoring pipeline.

**Source Files:**
- `src/tapps_mcp/server.py`

**Tasks:**
- [ ] Register `tapps_dead_code(file_path, min_confidence=80)` as an MCP tool
- [ ] Return findings grouped by type (functions, classes, imports, variables, unreachable)
- [ ] Include confidence score, line number, and suggested action per finding
- [ ] Add `_ANNOTATIONS_READ_ONLY` tool annotations (read-only, idempotent)
- [ ] Support directory scanning (run vulture on a directory path)
- [ ] Return structured output if Epic 13 is complete

**Implementation Notes:**
- Tool annotation: read-only, idempotent, closed-world
- Response format: summary line + per-type grouped findings
- Example: "Found 7 dead code items (3 unused functions, 2 unused imports, 1 unreachable block, 1 unused variable)"

**Definition of Done:** `tapps_dead_code` tool is callable via MCP and returns grouped, actionable findings.

---

### 14.5 — Whitelist and Configuration

**Points:** 3
**Priority:** Important
**Status:** Planned

Support whitelisting intentionally "unused" code — test fixtures, CLI entry points, `__all__` exports, plugin hooks.

**Source Files:**
- `src/tapps_mcp/config/settings.py`
- `src/tapps_mcp/tools/vulture.py`

**Tasks:**
- [ ] Add `dead_code_whitelist_patterns: list[str]` to settings (default: `["test_*", "conftest.py"]`)
- [ ] Add `dead_code_min_confidence: int` to settings (default: 80)
- [ ] Support vulture whitelist files (`--whitelist path`)
- [ ] Auto-exclude common false positives: `__init__`, `__all__`, pytest fixtures, click commands
- [ ] Add `TAPPS_MCP_DEAD_CODE_MIN_CONFIDENCE` env var override

**Implementation Notes:**
- Vulture supports `--ignore-names` for patterns and `--whitelist` for explicit whitelist files
- Common false positives in Python: `__init__`, `__str__`, `__repr__`, pytest fixtures, Flask/Django routes
- Auto-generate a default whitelist from project type detection (Flask routes, Django views, etc.)

**Definition of Done:** Users can configure confidence thresholds and whitelist patterns. Common false positives are auto-excluded.

---

### 14.6 — Tests

**Points:** 3
**Priority:** Important
**Status:** Planned

Comprehensive tests for vulture integration, scoring impact, and edge cases.

**Source Files:**
- `tests/unit/test_vulture.py` (NEW)
- `tests/unit/test_dead_code_scoring.py` (NEW)

**Tasks:**
- [ ] Test `run_vulture_async` with mock subprocess output
- [ ] Test output parsing for all finding types (function, class, import, variable, unreachable)
- [ ] Test graceful degradation when vulture not installed
- [ ] Test timeout handling
- [ ] Test confidence threshold filtering
- [ ] Test whitelist exclusion
- [ ] Test scoring integration: dead code findings reduce maintainability/structure scores
- [ ] Test suggestion generation with specific line numbers and names
- [ ] Test `tapps_dead_code` tool handler
- [ ] Test parallel execution with vulture included

**Definition of Done:** ~40 new tests covering all vulture integration paths. Zero mypy/ruff errors.

---

## Performance Targets

| Tool | SLA |
|---|---|
| `run_vulture_async` (single file) | < 2 s |
| `run_vulture_async` (directory) | < 10 s |
| `tapps_dead_code` tool | < 3 s |
| Scoring overhead from dead code | < 50 ms (just penalty calculation) |

## Key Dependencies

- `vulture>=2.14` (optional dependency — graceful degradation when absent)
- Epic 1 (scoring infrastructure, parallel execution framework)
- Epic 13 (structured outputs — optional, for `tapps_dead_code` structured response)

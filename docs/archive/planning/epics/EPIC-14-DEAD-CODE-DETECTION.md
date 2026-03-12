# Epic 14: Dead Code Detection (Vulture)

**Status:** Complete — vulture.py, dead_code.py, scorer integration, tapps_dead_code tool, whitelist patterns, 45 tests
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

- [x] Vulture integration follows existing tool wrapper pattern (`tools/vulture.py`)
- [x] `tapps_dead_code` tool: standalone dead code scan with confidence thresholds
- [x] Dead code findings feed into `maintainability` and `structure` scoring categories
- [x] Graceful degradation when vulture is not installed (returns empty list)
- [x] Configurable confidence threshold (default 80%) — `dead_code_min_confidence` in settings
- [x] Whitelist support for intentional "unused" code (test fixtures, CLI entry points)
- [x] Findings include file path, line number, name, type (function/class/import/variable), confidence
- [x] Added to `tools/parallel.py` for concurrent execution
- [x] Added to `tools/tool_detection.py` for auto-discovery
- [x] All changes covered by unit tests (test_vulture.py, test_dead_code_scoring.py)
- [x] Zero mypy/ruff errors

---

## Stories

### 14.1 — Vulture Tool Wrapper

**Points:** 5
**Priority:** Critical
**Status:** Complete

Create the async subprocess wrapper for vulture, following the same pattern as `tools/ruff.py`, `tools/bandit.py`, and `tools/radon.py`.

**Source Files:**
- `src/tapps_mcp/tools/vulture.py`
- `src/tapps_mcp/tools/tool_detection.py`

**Tasks:**
- [x] Create `tools/vulture.py` with `run_vulture_async(file_path, min_confidence=80, ...) -> list[DeadCodeFinding]`
- [x] Define `DeadCodeFinding` dataclass: `file_path`, `line`, `name`, `finding_type`, `confidence`, `message`
- [ ] Parse vulture's `--json` output (current implementation uses line-based parsing)
- [x] Parse line-based output: `path:line: unused {type} '{name}' (confidence: XX%)`
- [x] Handle timeout (default 30s), not-installed, and empty-output cases
- [x] Add `"vulture"` to `tool_detection.py` discovery
- [ ] Add vulture to optional dependencies in `pyproject.toml` (not present; degrades gracefully)

**Implementation Notes:**
- Vulture CLI: `vulture path/ --min-confidence 80`
- Output format per line: `path.py:42: unused function 'helper' (60% confidence)`
- Parse with regex: `^(.+):(\d+): unused (\w[\w\s]*) '([^']+)' \((\d+)% confidence\)$`
- Subprocess pattern matches `run_command_async` (via `subprocess_runner`)

**Definition of Done:** `run_vulture_async()` returns parsed dead code findings with confidence scores. Graceful degradation when vulture is not installed. whitelist_paths not implemented.

---

### 14.2 — Parallel Execution Integration

**Points:** 3
**Priority:** Critical
**Status:** Complete

Add vulture to the parallel tool execution pipeline so dead code analysis runs concurrently with ruff, mypy, bandit, and radon.

**Source Files:**
- `src/tapps_mcp/tools/parallel.py`
- `src/tapps_mcp/scoring/models.py`

**Tasks:**
- [x] Add `dead_code: list[DeadCodeFinding]` field to `ParallelResults`
- [x] Add vulture to `run_all_tools()` — runs concurrently with other tools via `asyncio.gather`
- [x] Handle vulture not-installed: returns empty list, degrades gracefully (no degraded flag for vulture)
- [x] Add `dead_code_count` to ScoreResult; dead code results threaded through scorer
- [x] Thread dead code results through scorer to maintainability/structure penalties

**Implementation Notes:**
- Vulture is optional — its absence returns empty findings, does not block scoring

**Definition of Done:** `run_all_tools()` includes vulture in the parallel execution. Missing vulture degrades gracefully.

---

### 14.3 — Scoring Integration

**Points:** 5
**Priority:** Critical
**Status:** Complete

Feed vulture findings into the existing 7-category scoring model, enhancing the `maintainability` and `structure` categories.

**Source Files:**
- `src/tapps_mcp/scoring/scorer.py`
- `src/tapps_mcp/scoring/dead_code.py`

**Tasks:**
- [x] Add dead code penalty to `maintainability` category: confidence-weighted penalties
- [x] Add dead code penalty to `structure` category: unused imports and unreachable code
- [x] Define penalty constants in `dead_code.py` (DEAD_CODE_PENALTY_PER_FINDING, etc.)
- [x] Add `details["dead_code_count"]`, `details["dead_code_penalty"]` to maintainability
- [x] Generate suggestions via `suggest_dead_code_fixes()` with line numbers and names
- [x] Weight by confidence: findings at 60% penalize less than at 100%

**Implementation Notes:**
- Penalty split: 60% maintainability, 40% structure
- Unreachable code gets extra penalty

**Definition of Done:** Dead code findings reduce maintainability and structure scores proportionally. Suggestions are actionable with line numbers.

---

### 14.4 — Standalone `tapps_dead_code` Tool

**Points:** 3
**Priority:** Important
**Status:** Complete

Expose a dedicated MCP tool for on-demand dead code scanning, separate from the full scoring pipeline.

**Source Files:**
- `src/tapps_mcp/server.py`

**Tasks:**
- [x] Register `tapps_dead_code(file_path, min_confidence=80)` as an MCP tool
- [x] Return findings grouped by type (functions, classes, imports, variables, unreachable)
- [x] Include confidence score, line number, and suggested action per finding
- [x] Add `_ANNOTATIONS_READ_ONLY` tool annotations (read-only, idempotent)
- [x] Support file path (vulture accepts file or directory; single-file use case implemented)
- [ ] Return structured output (Epic 13 partial — structuredContent not wired for tapps_dead_code)

**Definition of Done:** `tapps_dead_code` tool is callable via MCP and returns grouped, actionable findings.

---

### 14.5 — Whitelist and Configuration

**Points:** 3
**Priority:** Important
**Status:** Complete

Support whitelisting intentionally "unused" code — test fixtures, CLI entry points, `__all__` exports, plugin hooks.

**Source Files:**
- `src/tapps_mcp/config/settings.py`
- `src/tapps_mcp/tools/vulture.py`

**Tasks:**
- [x] Add `dead_code_whitelist_patterns: list[str]` to settings (default: `["test_*", "conftest.py"]`)
- [x] Add `dead_code_min_confidence: int` to settings (default: 80)
- [x] Filter findings by whitelist patterns (fnmatch on file basename) in `run_vulture_async`
- [ ] Support vulture native `--whitelist` file (optional enhancement)
- [ ] Auto-exclude common false positives: `__init__`, `__all__` (optional enhancement)
- [x] pydantic-settings provides `TAPPS_MCP_DEAD_CODE_*` env var overrides

**Implementation Notes:**
- Filtering done in Python after vulture output (fnmatch on file basename)
- Default patterns: `test_*`, `conftest.py` exclude test files from findings

**Definition of Done:** Users can configure confidence thresholds and whitelist patterns.

---

### 14.6 — Tests

**Points:** 3
**Priority:** Important
**Status:** Complete

Comprehensive tests for vulture integration, scoring impact, and edge cases.

**Source Files:**
- `tests/unit/test_vulture.py`
- `tests/unit/test_dead_code_scoring.py`

**Tasks:**
- [x] Test `run_vulture_async` with mock subprocess output
- [x] Test output parsing for all finding types (function, class, import, variable, unreachable, attribute)
- [x] Test graceful degradation when vulture not installed
- [x] Test timeout handling
- [x] Test confidence threshold filtering
- [ ] Test whitelist exclusion (not implemented yet)
- [x] Test scoring integration: dead code findings reduce maintainability/structure scores
- [x] Test suggestion generation with specific line numbers and names
- [ ] Test `tapps_dead_code` tool handler (indirectly via tool annotation tests)
- [ ] Test parallel execution with vulture included (indirect coverage)

**Definition of Done:** ~40 new tests covering vulture integration paths. Zero mypy/ruff errors. Whitelist tests pending implementation.

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

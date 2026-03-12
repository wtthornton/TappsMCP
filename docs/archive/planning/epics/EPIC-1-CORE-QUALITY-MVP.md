# Epic 1: Core Quality MVP

**Status:** Complete
**Priority:** P0 — Critical Path (first user-facing value)
**Estimated LOE:** ~2-3 weeks (1 developer)
**Dependencies:** Epic 0 (Foundation & Security)
**Blocks:** Epic 6 (Distribution)

---

## Goal

Deliver a working MCP server with four tools that address 6 of the 13 identified LLM error sources: `tapps_score_file`, `tapps_security_scan`, `tapps_quality_gate`, and `tapps_checklist`. This is the MVP — the minimum set of tools that provides meaningful quality enforcement for any LLM writing code.

## LLM Error Sources Addressed

| Error Source | Tool |
|---|---|
| Skipped edge cases | `tapps_score_file` |
| Missed tests | `tapps_quality_gate` |
| Security blindspots | `tapps_security_scan` |
| Inconsistent quality | `tapps_quality_gate` |
| Self-review bias | `tapps_score_file` |
| Misinterpreted tool output | All (structured JSON) |

## 2026 Best Practices Applied

- **Parallel subprocess execution**: Run ruff, mypy, bandit, radon concurrently via `asyncio.create_subprocess_exec`. No sequential external tool calls.
- **`elapsed_ms` in all responses**: Every tool response includes execution time for client-side performance monitoring.
- **Graceful degradation with `degraded: true`**: When external tools are missing, return partial results with clear signals — never fail silently.
- **Append-only response schemas**: Once released, response fields are never removed or renamed. New fields may be added (minor version bump).
- **MCP tool annotations**: Use `readOnlyHint: true` for scoring/scanning tools (they don't modify files), `destructiveHint: false`. Use `openWorldHint: false` since tools operate on local files only.
- **FastMCP `@mcp.tool()` pattern**: Register tools with type-annotated parameters — `Annotated[str, Field(description="Path to file")]` auto-generates JSON schemas. Use `ToolError` for user-visible errors.
- **Async tool handlers**: Use `async def` for tool handlers that invoke subprocesses. MCP SDK is async-native via `anyio`. Sync handlers auto-run in threadpool.
- **Progress tracking**: Long-running tools (`tapps_score_file` full mode, `tapps_quality_gate`) should use `ctx.report_progress()` to show incremental progress to MCP clients.

## Acceptance Criteria

- [ ] `tapps_score_file` scores Python files across 7 categories with objective metrics
- [ ] `tapps_score_file` with `quick: true` returns ruff-only results in < 500ms (p95)
- [ ] `tapps_score_file` with `quick: true, fix: true` applies ruff auto-fixes
- [ ] `tapps_score_file` full mode runs in < 3s (p95) via parallel execution
- [ ] `tapps_security_scan` returns OWASP-categorized findings with severity
- [ ] `tapps_security_scan` detects hardcoded secrets when `scan_secrets: true`
- [ ] `tapps_quality_gate` evaluates pass/fail against configurable thresholds
- [ ] `tapps_quality_gate` supports standard/strict/framework presets
- [ ] `tapps_checklist` tracks tool call history per session and reports missing tools
- [ ] All `file_path` inputs validated against project root boundary
- [ ] All tools return structured JSON matching the defined response schemas
- [ ] Missing external tools (ruff, mypy, bandit) degrade gracefully with `install_hint`
- [ ] Unit tests ported: ~190 tests (scoring ~120, gates ~45, security ~25)
- [ ] Integration tests: MCP tool call → structured response
- [ ] Cross-platform: Windows + Linux + macOS

---

## Stories

### 1.1 — Extract Scoring Engine

**Points:** 8

Extract the full scoring engine from `agents/reviewer/` — this is the largest extraction in the epic.

**Tasks:**
- Extract `scoring.py` → `tapps_mcp/scoring/scorer.py`
  - Decouple from `ProjectConfig` + `Language` — accept config as dict/Pydantic model
  - Replace framework logging with structlog
- Copy standalone modules directly:
  - `score_constants.py` → `constants.py`
  - `validation.py` → `validation.py`
  - `scorer_registry.py` → `registry.py`
  - `maintainability_scorer.py` → `maintainability.py`
  - `performance_scorer.py` → `performance.py`
  - `typescript_scorer.py` → `typescript.py`
  - `react_scorer.py` → `react.py`
  - `pattern_detector.py` → `pattern_detector.py`
  - `context_detector.py` → `context_detector.py`
  - `score_validator.py` → `score_validator.py`
  - `metric_strategies.py` → `metric_strategies.py`
  - `library_patterns.py` → `library_patterns.py`
  - `library_detector.py` → `library_detector.py`
  - `output_enhancer.py` → `output_enhancer.py`
  - `report_generator.py` → `report_generator.py`
  - `aggregator.py` → `aggregator.py`
- Extract `adaptive_scorer.py` → `adaptive.py` — remove agent base dependency
- Port ~120 unit tests, adapt import paths and fixtures
- Verify scoring results match TappsCodingAgents output on reference files

**Definition of Done:** Scoring engine produces identical results to TappsCodingAgents. ~120 tests pass.

---

### 1.2 — Extract Tool Integrations

**Points:** 3

Extract the external tool wrappers (ruff, mypy, bandit, radon).

**Tasks:**
- Extract `tools/ruff_grouping.py` → `tapps_mcp/tools/ruff.py` — ruff output parsing and grouping
- Extract `tools/scoped_mypy.py` → `tapps_mcp/tools/mypy.py` — scoped mypy execution
- Extract `tools/parallel_executor.py` → `tapps_mcp/tools/parallel.py` — concurrent tool execution
- All subprocess calls use `wrap_windows_cmd_shim()` from Epic 0
- All subprocess calls use `asyncio.create_subprocess_exec` for non-blocking execution
- Each tool wrapper handles graceful degradation when tool is not installed

**Definition of Done:** Tool wrappers invoke ruff/mypy/bandit/radon correctly on Windows + Linux. Graceful degradation when missing.

---

### 1.3 — Extract Quality Gates

**Points:** 5

Extract the quality gate system from `quality/`.

**Tasks:**
- Extract `quality_gates.py` → `tapps_mcp/gates/quality_gates.py` — decouple from framework
- Extract `enforcement.py` → `tapps_mcp/gates/enforcement.py` — minimal coupling
- Copy standalone modules:
  - `gates/base.py` → `base.py` — `BaseGate`, `GateResult`, `GateSeverity`
  - `gates/registry.py` → `registry.py` — pluggable gate registry
  - `gates/exceptions.py` → `exceptions.py`
- Extract `gates/security_gate.py` → `security_gate.py` — extract with governance dependency
- Evaluate `gates/policy_gate.py` coupling — extract if standalone, defer if heavily coupled
- Extract `coverage_analyzer.py` → `coverage_analyzer.py` — required for test_coverage gate
- Implement preset system: standard (70+), strict (80+), framework (75+ with 8.5 security)
- Port ~45 unit tests

**Definition of Done:** Quality gates evaluate pass/fail with configurable thresholds. Preset system works. ~45 tests pass.

---

### 1.4 — Extract Security Scanning

**Points:** 3

Extract the security scanning tools for the `tapps_security_scan` tool.

**Tasks:**
- Extract `quality/secret_scanner.py` → `tapps_mcp/security/secret_scanner.py`
- Extract `core/security_scanner.py` → `tapps_mcp/security/security_scanner.py` (standalone Bandit wrapper)
- Wire secret detection + Bandit into unified security scan
- Map findings to OWASP categories
- Return severity levels (critical, high, medium, low, info)
- Port ~25 unit tests

**Definition of Done:** Security scan returns OWASP-categorized findings. Secret detection catches hardcoded credentials. ~25 tests pass.

---

### 1.5 — Wire MCP Tools

**Points:** 5

Wire all four tools into the MCP server with proper request/response handling.

**Tasks:**
- Implement `tapps_score_file` MCP tool handler:
  - Full mode: parallel ruff + mypy + bandit + radon → 7-category score
  - Quick mode (`quick: true`): ruff only, < 500ms target
  - Fix mode (`quick: true, fix: true`): apply ruff auto-fixes, return `fixes_applied` count
  - Path validation before any file I/O
  - Graceful degradation for missing tools
- Implement `tapps_security_scan` MCP tool handler:
  - Bandit scan + secret detection
  - `scan_secrets` parameter (default: true)
  - Path validation before any file I/O
- Implement `tapps_quality_gate` MCP tool handler:
  - Run full scoring + gate evaluation
  - Support `preset` parameter (standard/strict/framework)
  - Return pass/fail with specific failures and recommendations
- Implement `tapps_checklist` MCP tool handler:
  - Server-side call log tracking per session
  - `task_type` parameter determines recommended tool set
  - Return called/missing/optional_missing tools with reasons
- All tools return `elapsed_ms` in response
- All tools return standard error schema on failure

**Definition of Done:** All four tools callable via MCP protocol. Responses match defined schemas. Path validation enforced.

---

### 1.6 — Unit Tests

**Points:** 3

Comprehensive unit test coverage for all extracted modules.

**Tasks:**
- Port scoring tests (~120 tests)
- Port gate tests (~45 tests)
- Port security tests (~25 tests)
- Add new tests for MCP-specific logic (quick mode, fix mode, checklist)
- Mock at subprocess boundary — don't require ruff/mypy/bandit installed for unit tests
- Target: ≥80% coverage on all extracted modules

**Definition of Done:** ~190+ unit tests pass. Coverage ≥80%.

---

### 1.7 — Integration Tests

**Points:** 3

MCP protocol integration tests — verify the full request/response lifecycle.

**Tasks:**
- Test: `tools/call` for `tapps_score_file` on a Python file
- Test: `tools/call` for `tapps_score_file` with `quick: true`
- Test: `tools/call` for `tapps_security_scan` on a file with known vulnerabilities
- Test: `tools/call` for `tapps_quality_gate` with passing and failing files
- Test: `tools/call` for `tapps_checklist` after calling/not-calling tools
- Test: path validation rejects files outside project root
- Test: graceful degradation when external tools are missing

**Definition of Done:** Integration tests pass end-to-end on all platforms.

---

### 1.8 — Cross-Platform Validation

**Points:** 2

Ensure everything works on Windows, Linux, and macOS.

**Tasks:**
- CI matrix: Windows + Linux + macOS × Python 3.12 + 3.13
- Verify subprocess_utils handles Windows `.cmd` shims
- Verify path validation works with Windows backslash paths
- Verify temp file handling works cross-platform (no `fcntl`)
- Fix any platform-specific failures

**Definition of Done:** CI green on all 6 platform/version combinations.

---

### 1.9 — MVP Documentation

**Points:** 2

README with setup instructions for Claude Code and Cursor.

**Tasks:**
- README.md: what TappsMCP is, what problems it solves, quick start
- Claude Code setup: `~/.claude/settings.json` snippet
- Cursor setup: `.cursor/mcp.json` snippet
- Minimal system prompt (10-line version for MVP with 4 tools)
- Troubleshooting: common issues (missing tools, path validation, Windows)

**Definition of Done:** A developer can go from `pip install tapps-mcp` to working MCP server in < 5 minutes following the README.

---

## Cross-References

- **Metrics recording:** All tool handlers in this epic will be automatically instrumented by [Epic 7](EPIC-7-METRICS-DASHBOARD.md) (Story 7.7) with a metrics decorator that records `ToolCallMetric` for every invocation. Design tool handlers to return `elapsed_ms` and structured status codes to support this.
- **Outcome tracking:** `tapps_score_file` and `tapps_quality_gate` results feed into Epic 7's `OutcomeTracker` for adaptive learning (initial scores → final scores → iterations to quality).
- **Quality aggregation:** `tapps_score_file` results feed into Epic 7's `QualityAggregator` for multi-file dashboards.

## Performance Targets

| Tool | Target (p95) | Notes |
|---|---|---|
| `tapps_score_file` (quick) | < 500ms | Ruff only |
| `tapps_score_file` (full) | < 3s | Parallel ruff + mypy + bandit + radon |
| `tapps_security_scan` | < 2s | Bandit + secret scanner |
| `tapps_quality_gate` | < 5s | Full scoring + gate evaluation |
| `tapps_checklist` | < 100ms | Server-side state lookup |

## Key Dependencies
- `ruff` — linting (required for any scoring)
- `radon` — complexity metrics
- `bandit` — security scanning (optional, graceful degradation)
- `mypy` — type checking (optional, graceful degradation)
- `coverage` — test coverage (optional, graceful degradation)

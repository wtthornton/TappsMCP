# Epic 13: Structured Tool Outputs (MCP 2025-11-25)

**Status:** Partial — 6 tools wired (score_file, quality_gate, quick_check, security_scan, validate_changed, validate_config); outputSchema not in registration; remaining tools open
**Priority:** P0 — Critical (enables programmatic score consumption by all MCP clients)
**Estimated LOE:** ~1-2 weeks (1 developer)
**Dependencies:** Epic 0 (Foundation), Epic 1 (Core Quality)
**Blocks:** None

---

## Goal

Adopt the MCP 2025-11-25 `outputSchema` + `structuredContent` feature so every scoring and analysis tool returns both human-readable markdown AND machine-parseable JSON. Clients can programmatically act on scores without text parsing.

## Why This Epic Exists

Today, all TappsMCP tools return plain-text markdown. MCP clients (Claude Code, Cursor, VS Code Copilot) must parse free-form text to extract scores, pass/fail status, and issue lists. This is:

1. **Fragile** — any formatting change breaks downstream consumers
2. **Lossy** — structured data (score breakdowns, issue arrays, confidence values) is flattened into prose
3. **Slow** — LLMs re-parse text that was generated from structured data in the first place

The MCP 2025-11-25 spec introduces `outputSchema` (tool-level JSON schema declaration) and `structuredContent` (per-response JSON blob alongside text content). Adopting this is the single highest-leverage protocol upgrade available.

## LLM Error Sources Addressed

| Error Source | How This Epic Helps |
|---|---|
| Score misinterpretation | Clients read `{"overall_score": 72}` instead of parsing "Overall: 72/100" |
| Lost issue details | Full issue arrays with line numbers, severity, and codes preserved in JSON |
| Inconsistent gate logic | `{"passed": false, "threshold": 70, "actual": 68}` is unambiguous |
| Context window waste | Clients can skip markdown rendering and consume compact JSON |
| Integration brittleness | JSON schemas are versioned contracts; markdown is not |

## Acceptance Criteria

- [x] All scoring tools (`tapps_score_file`, `tapps_quality_gate`, `tapps_quick_check`) return `structuredContent` alongside text
- [x] `tapps_validate_changed` returns structured per-file results
- [x] `tapps_security_scan` returns structured findings with severity, line, and CWE
- [ ] All tools declare `outputSchema` in their tool registration
- [x] Backward-compatible — text content unchanged for clients that don't support structured outputs
- [x] Pydantic models define output schemas (single source of truth)
- [x] Unit tests validate schema models and serialization (test_output_schemas.py)
- [ ] Unit tests validate tool handlers return both text and structuredContent
- [x] Zero mypy/ruff errors

---

## Stories

### 13.1 — Define Output Schema Models

**Points:** 3
**Priority:** Critical
**Status:** Complete

Create Pydantic v2 models for each tool's structured output. These models serve as the single source of truth for both `outputSchema` declarations and runtime `structuredContent` serialization.

**Source Files:**
- `src/tapps_mcp/common/output_schemas.py`

**Tasks:**
- [x] Create `ScoreFileOutput` model: overall_score, categories (dict of name -> score/suggestions), degraded, tool_errors, suggestions
- [x] Create `QualityGateOutput` model: passed, preset, threshold, actual_score, failing_categories, warnings
- [x] Create `QuickCheckOutput` model: score, gate_result (pass/fail), security_summary, suggestions
- [x] Create `SecurityScanOutput` model: findings (list of severity/line/code/message/cwe), secret_findings, summary
- [x] Create `ValidateChangedOutput` model: files (list of per-file results), overall_passed, summary
- [x] Add `ExpertOutput`, `ImpactOutput`, `ChecklistOutput` models
- [x] Add `.to_output_schema()` class method that returns the JSON schema dict for MCP tool registration
- [x] Add `.to_structured_content()` instance method that returns the serialized JSON for MCP responses
- [x] Create `ValidateConfigOutput` model

**Implementation Notes:**
- Use Pydantic v2 `model_json_schema()` for automatic JSON schema generation
- All models inherit from a `StructuredOutput` base with common serialization logic
- Keep models lean — only data that clients need to act on programmatically

**Definition of Done:** Output schema models exist with full type annotations, JSON schema export, and serialization. All models pass mypy --strict. ValidateConfigOutput still missing.

---

### 13.2 — Wire Structured Outputs to Scoring Tools

**Points:** 5
**Priority:** Critical
**Status:** Complete

Add `outputSchema` to tool registration and return `structuredContent` alongside existing text content for `tapps_score_file`, `tapps_quality_gate`, and `tapps_quick_check`.

**Source Files:**
- `src/tapps_mcp/server_scoring_tools.py`
- `src/tapps_mcp/common/output_schemas.py`

**Tasks:**
- [ ] Research FastMCP's `outputSchema` support — determine if `@mcp.tool()` accepts it as a kwarg or if it requires low-level registration
- [ ] Add `outputSchema` to tool registration (get_output_schema exists but not wired to @mcp.tool)
- [x] Build `ScoreFileOutput` instance from existing `ScoreResult` data in the handler
- [x] Return both text content and `structuredContent` in the tool response
- [x] Repeat for `tapps_quality_gate` with `QualityGateOutput`
- [x] Repeat for `tapps_quick_check` with `QuickCheckOutput`
- [x] Ensure backward compatibility — text content is identical to current output

**Implementation Notes:**
- FastMCP may require using `mcp.types.CallToolResult` directly instead of returning a plain string
- The `structuredContent` field is optional per spec — clients that don't support it simply ignore it
- Test with both structured-aware and plain-text clients

**Definition of Done:** All three scoring tools return structured JSON alongside text. Clients that support `structuredContent` can extract scores programmatically. outputSchema still not declared at registration.

---

### 13.3 — Wire Structured Outputs to Security & Validation Tools

**Points:** 3
**Priority:** Important
**Status:** Complete

Add structured outputs to `tapps_security_scan`, `tapps_validate_changed`, and `tapps_validate_config`.

**Source Files:**
- `src/tapps_mcp/server.py`
- `src/tapps_mcp/server_pipeline_tools.py`
- `src/tapps_mcp/common/output_schemas.py`

**Tasks:**
- [x] Add `outputSchema` + `structuredContent` to `tapps_security_scan` using `SecurityScanOutput`
- [x] Add `outputSchema` + `structuredContent` to `tapps_validate_changed` using `ValidateChangedOutput`
- [x] Create `ValidateConfigOutput` model and wire to `tapps_validate_config`
- [x] Ensure per-file results in `tapps_validate_changed` include individual scores and gate results

**Definition of Done:** Security and validation tools return structured JSON. `tapps_validate_changed` returns a parseable array of per-file results.

---

### 13.4 — Wire Structured Outputs to Remaining Tools

**Points:** 3
**Priority:** Important
**Status:** Open

Add structured outputs to the remaining tools: `tapps_consult_expert`, `tapps_research`, `tapps_impact_analysis`, `tapps_project_profile`, `tapps_session_start`, `tapps_checklist`.

**Source Files:**
- `src/tapps_mcp/server.py`
- `src/tapps_mcp/server_metrics_tools.py`
- `src/tapps_mcp/server_pipeline_tools.py`
- `src/tapps_mcp/common/output_schemas.py`

**Tasks:**
- [x] Create output models: `ExpertOutput`, `ImpactOutput`, `ChecklistOutput` (in OUTPUT_SCHEMA_REGISTRY)
- [ ] Create output models: `ResearchOutput`, `ProfileOutput`, `SessionStartOutput` (still missing)
- [ ] Wire `outputSchema` + `structuredContent` to each tool handler (none wired yet)
- [ ] Prioritize tools where structured output is most valuable (expert confidence scores, impact blast radius)
- [ ] Tools that return simple text (e.g., `tapps_session_notes`) can skip structured outputs

**Definition of Done:** All tools that produce structured data return `structuredContent`. Simple text-only tools are explicitly excluded with a comment explaining why.

---

### 13.5 — Tests and Documentation

**Points:** 3
**Priority:** Important
**Status:** Partial

Comprehensive tests for structured output correctness and schema validation.

**Source Files:**
- `tests/unit/test_output_schemas.py`
- `tests/unit/test_structured_scoring.py` (not created)

**Tasks:**
- [x] Test each output model's JSON schema generation matches expected structure
- [x] Test each output model's serialization round-trips correctly
- [ ] Test that tool handlers return both text and structuredContent
- [ ] Test backward compatibility — text content unchanged
- [ ] Test that structuredContent validates against the declared outputSchema
- [ ] Add integration test: call tool via MCP client, verify structured response
- [ ] Document structured output usage in AGENTS.md for consuming projects

**Definition of Done:** All output schemas have round-trip tests. Tool responses validate against declared schemas. ~30 new tests. Schema tests complete (~48); tool-handler tests not added.

---

## Performance Targets

| Tool | SLA Impact |
|---|---|
| All tools | < 5 ms overhead for structured serialization |
| Schema generation | One-time at startup (cached) |

## Key Dependencies

- MCP Python SDK `>=1.26.0` (already pinned) — verify `outputSchema` and `structuredContent` support
- FastMCP support for structured outputs — may need direct `CallToolResult` construction
- Pydantic v2 `model_json_schema()` for schema generation

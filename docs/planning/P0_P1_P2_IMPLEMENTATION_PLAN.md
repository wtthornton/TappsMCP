# P0, P1, P2 Tool Tier Promotion — Implementation Plan

**Date:** 2026-02-25
**Sequence:** P2 (smallest) → P0 (medium) → P1 (largest)

---

## P2: Always-On Docs + File Context in `tapps_research`

### Files to Modify
- `src/tapps_mcp/server_metrics_tools.py` — `tapps_research` (line ~277)
- `src/tapps_mcp/common/output_schemas.py` — `ResearchOutput` model

### Changes
1. Increase question max from 2000 → 5000 chars
2. Add `file_context: str = ""` parameter
3. Remove `_MIN_CONFIDENCE_FOR_DOCS = 0.5` gate — always fetch docs
4. When `file_context` provided, use `extract_external_imports()` to infer library
5. When library still empty, use project profile tech stack instead of defaulting to "python"
6. Add `file_context` field to `ResearchOutput`

### Test Plan
- Docs always fetched regardless of confidence level
- `file_context` with imports infers correct library
- `file_context` with invalid path = graceful fallback
- Tech stack inference when no file context
- Final fallback to "python"
- Question length 5000 accepted, >5000 truncated

---

## P0: Security + Impact in `tapps_validate_changed`

### Files to Modify
- `src/tapps_mcp/server_pipeline_tools.py` — `tapps_validate_changed`
- `src/tapps_mcp/common/output_schemas.py` — `ValidateChangedOutput`
- `src/tapps_mcp/tools/batch_validator.py` — `format_batch_summary()`
- `src/tapps_mcp/project/impact_analyzer.py` — add optional `graph` param

### Changes
1. Add `security_depth: str = "basic"` param (basic/full)
2. Add `include_impact: bool = False` param
3. Change security gate: `security_depth="full"` overrides `quick` gate
4. Add basic secret-scan-only path for `quick=True` + `include_security=True`
5. After scoring, optionally run impact analysis (pre-build graph once, share across files)
6. Add `impact_summary` to response and structured output

### Test Plan
- `security_depth="basic"` + `quick=True` = SecretScanner only
- `security_depth="full"` + `quick=True` = full bandit+secrets
- `include_impact=True` returns impact_summary
- `include_impact=False` omits impact_summary
- Impact graph built once and shared
- Impact failure on one file doesn't block others
- Backward compat: no new params = identical output shape

---

## P1: Make `tapps_checklist` Execute Validations

### Files to Modify
- `src/tapps_mcp/server.py` — `tapps_checklist` (line ~840)
- `src/tapps_mcp/common/output_schemas.py` — `ChecklistOutput`

### Changes
1. Convert `def tapps_checklist` → `async def tapps_checklist`
2. Add `auto_run: bool = False` parameter
3. When `auto_run=True` and missing required tools:
   - Missing score/gate/security → run `tapps_validate_changed`
   - Missing security for security/feature task → run security scan
4. Re-evaluate checklist after auto-running
5. Add `auto_run_results` to response

### Test Plan
- `auto_run=False` = identical to current behavior
- `auto_run=True` with missing tools triggers validate_changed
- `auto_run=True` with all tools called = no auto-runs
- Auto-run failure = graceful degradation
- Re-evaluation shows tools as called after auto-run

### Risks
- Latency: auto-run can take 10-60s
- MCP timeouts: may need progress notifications
- No changed files: skip gracefully

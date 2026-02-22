# Critical and High Items — Review, Update, and Finalization Plan

**Created:** 2026-02-22  
**Purpose:** Systematically review, implement (where gaps remain), and update documentation for all critical and high-priority items from `INIT_AND_UPGRADE_FEATURE_LIST.md` and `SELF_REVIEW_FINDINGS.md`.  
**Audience:** TappsMCP maintainers

---

## Phase 1: Code Verification (Review) — ✅ COMPLETE (2026-02-22)

Verified current implementation status by inspecting the codebase. Findings recorded below.

### 1.1 INIT_AND_UPGRADE_FEATURE_LIST — Critical Items

| # | Area | Doc Claim | Code Verification | Evidence |
|---|------|-----------|-------------------|----------|
| 1 | **CLI exit codes** | Never calls sys.exit | ✅ **Implemented** | `cli.py:94-95` — `raise SystemExit(1)` when `not success`; `run_init()` returns `False` on `_check_config` failure or `_generate_config` failure; CLI propagates to exit 1 |
| 2 | **Invalid JSON in host config** | Overwrites file, loses other servers | ✅ **Implemented** | `setup_generator.py:207-217` — on `JSONDecodeError`, echoes error, returns `False`; does **not** overwrite; merged config never written |
| 3 | **Cache warming failures hidden** | Exception swallowed, no error in result | ✅ **Implemented** | `init.py:440-461` — `_run_cache_warming` sets `error` in result on exception; `init.py:287-289` — appends `f"Cache warming failed: {cache_result['error']}"` to `state.errors` |

### 1.2 INIT_AND_UPGRADE_FEATURE_LIST — High Items

| # | Area | Doc Claim | Code Verification | Evidence |
|---|------|-----------|-------------------|----------|
| 4 | **Checker install environment** | Uses `pip install` not `sys.executable -m pip` | ✅ **Implemented** | `init.py:342-344` — `subprocess.run([sys.executable, "-m", "pip", "install", pkg], ...)` |
| 5 | **Cursor platform rules never refresh** | No overwrite option | ✅ **Implemented** | `init.py:40, 108, 232, 253` — `overwrite_platform_rules` in `BootstrapConfig`; passed to `_bootstrap_claude` and `_bootstrap_cursor` |
| 6 | **Expert RAG warming errors not surfaced** | No failed_domains or errors | ⚠️ **Partial** | `rag_warming.py:177-182` — returns `failed_domains`; `init.py:297-309` — stores in `expert_rag_warming` but does **not** append to `state.errors` |
| 7 | **No dry-run / preview** | Missing | ❌ **Not implemented** | No `dry_run` param in `bootstrap_pipeline` or `run_init`; no `--dry-run` in CLI |
| 8 | **Success vs subsystem failure** | success=True when warming fails | ⚠️ **Partial** | Cache warming: errors append to `state.errors` → `success=False`. Expert RAG: `failed_domains` in result only → `success` can stay `True` |
| 9 | **CLI init overwrite non-interactive** | No --force | ✅ **Implemented** | `cli.py:61-62` — `--force`; `setup_generator.py:227` — `if not force and not click.confirm(...)` skips prompt when `force=True` |

### 1.3 SELF_REVIEW_FINDINGS — Critical

| # | Area | Doc Claim | Code Verification | Evidence |
|---|------|-----------|-------------------|----------|
| 1 | **server.py split** | Still monolithic | ✅ **Implemented** | `server_scoring_tools.py`, `server_pipeline_tools.py`, `server_metrics_tools.py`, `server_helpers.py` exist; server.py delegates tool handlers to these modules |

### 1.4 SELF_REVIEW_FINDINGS — High

| # | Area | Doc Claim | Code Verification | Evidence |
|---|------|-----------|-------------------|----------|
| 2 | **Feedback loop disconnected** | AdaptiveScoringEngine doesn't use feedback | ❌ **Not implemented** | `scoring_engine.py` uses only `OutcomeTrackerProtocol` and `CodeOutcome`; no `FeedbackTracker` import; `hot_rank.py` uses `get_by_tool()` for ranking only |
| 3 | **Checklist state not persisted** | Module-level state, resets on restart | ⚠️ **Partial** | `checklist.py:155-195` — `set_persist_path`, `_load_persisted`, `_persist_record` exist; **no caller** — `set_persist_path` never invoked; server never configures persist path |
| 4 | **Expert RAG relevance poor** | No BM25/TF-IDF, no threshold | ❌ **Not implemented** | `vector_rag.py` has hybrid fusion; no BM25/TF-IDF; no relevance threshold filtering |

### 1.5 SELF_REVIEW_FINDINGS — Medium (in scope for doc updates)

| # | Area | Doc Claim | Code Verification | Evidence |
|---|------|-----------|-------------------|----------|
| 5 | **validate_changed cap 10 files** | Too low | ✅ **Implemented** | `batch_validator.py:17-19` — `MAX_BATCH_FILES = 50` with comment "Raised from 10 to 50" |
| 6 | **pipeline/init CC=30, no BootstrapConfig** | Needs refactor | ⚠️ **Partially** | `init.py:29-43` — `BootstrapConfig` dataclass; `_warm_caches`, `_run_server_verification` extracted; `bootstrap_pipeline` still has 11+ params passed to config |

### 1.6 Phase 1 Summary

| Status | Count | Items |
|--------|-------|-------|
| ✅ Implemented | 9 | C1, C2, C3, H4, H5, H9, SR1, SR5, SR6 (partial) |
| ⚠️ Partial | 3 | H6 (expert RAG failed_domains), H8 (success vs subsystem), SR3 (checklist wiring), SR6 (BootstrapConfig) |
| ❌ Not implemented | 3 | H7 (dry-run), SR2 (feedback loop), SR4 (expert RAG relevance) |

**Next:** Phase 2 (Implementation) and Phase 3 (Document Updates).

---

## Phase 2: Implementation Tasks (Update)

Prioritized list of remaining implementation work.

### 2.1 Critical — None

All critical items from INIT_AND_UPGRADE and SELF_REVIEW are implemented.

### 2.2 High — Remaining Work

| Task | Effort | Description |
|------|--------|-------------|
| **H1. Dry-run** | 1–2 days | Add `dry_run: bool` to `tapps_init` and `--dry-run` to `tapps-mcp init`; compute and return structure without writing |
| **H2. Checklist persistence wiring** | 0.5 day | In server startup (or first tool call), call `CallTracker.set_persist_path(metrics_dir / "sessions" / "checklist_calls.jsonl")` |
| **H3. Expert RAG failed_domains → errors** | 0.25 day | In `_warm_caches`, when `expert_rag_warming` has `failed_domains`, append to `state.errors` (e.g. "Expert RAG failed for domains: x, y") |
| **H4. Feedback → AdaptiveScoringEngine** | 1–2 days | Wire `FeedbackTracker.get_by_tool()` into `AdaptiveScoringEngine` so negative feedback influences weight recalibration |

### 2.3 Medium (Optional for this plan)

| Task | Effort | Notes |
|------|--------|-------|
| M1. Expert RAG BM25/TF-IDF + relevance threshold | 2–3 days | Significant change; defer to separate epic |
| M2. tapps_calibrate tool | 1 day | Defer |
| M3. tapps_report asyncio.gather + max_files | 1 day | Defer |
| M4. Quick check AST complexity heuristic | 1 day | Defer |

---

## Phase 3: Document Updates (Finalize)

Update documents to reflect verified code state and any new implementations.

### 3.1 INIT_AND_UPGRADE_FEATURE_LIST.md

| Section | Action |
|---------|--------|
| **Critical #1 (CLI exit codes)** | Add status: ✅ Implemented (cli.py raises SystemExit(1) on failure) |
| **Critical #2 (Invalid JSON)** | Add status: ✅ Implemented (setup_generator aborts, no overwrite) |
| **Critical #3 (Cache warming hidden)** | Add status: ✅ Implemented (error field + state.errors append) |
| **High #4 (Checker install)** | Add status: ✅ Implemented (sys.executable -m pip) |
| **High #5 (Platform rules refresh)** | Add status: ✅ Implemented (overwrite_platform_rules) |
| **High #6 (Expert RAG errors)** | Add status: ⚠️ Partially — failed_domains in result; add H3 to append to errors |
| **High #7 (Dry-run)** | Keep as open; add "Planned" or link to CRITICAL_HIGH_REVIEW_PLAN |
| **High #8 (Success vs subsystem)** | Update: cache errors append to errors; expert RAG gap noted (H3) |
| **High #9 (--force)** | Add status: ✅ Implemented |

Add a **"Verification (2026-02-22)"** subsection that summarizes the table and points to this plan.

### 3.2 SELF_REVIEW_FINDINGS.md

| Section | Action |
|---------|--------|
| **#1 server.py split** | Update: ✅ Implemented (server_scoring_tools, server_pipeline_tools, server_metrics_tools) |
| **#2 Feedback loop** | Keep as open; add "Planned (H4)" |
| **#3 Checklist persistence** | Update: Infrastructure exists; wiring (H2) needed — `set_persist_path` never called |
| **#4 Expert RAG relevance** | Keep as open; defer BM25/TF-IDF to separate epic |
| **#5 validate_changed cap** | Update: ✅ Implemented (MAX_BATCH_FILES = 50) |
| **#6 pipeline/init refactor** | Update: BootstrapConfig exists; partial refactor done; CC may still be high |

Add a **"Re-verification (2026-02-22)"** section with the table and link to this plan.

### 3.3 FEEDBACK_ISSUES_PLAN.md

No changes needed — checklist shows all items complete; code verification confirms resilience, JSON handling, docs, migration, and --force.

### 3.4 New: STATUS.md or doc index

Consider adding a single source of truth that links:

- `INIT_AND_UPGRADE_FEATURE_LIST.md` (init/upgrade recommendations)
- `SELF_REVIEW_FINDINGS.md` (self-review enhancements)
- `CRITICAL_HIGH_REVIEW_PLAN.md` (this plan)

---

## Phase 4: Execution Order

1. **Phase 1 (Review)** — Complete verification table; confirm no critical gaps.
2. **Phase 3.1–3.2 (Docs)** — Update INIT_AND_UPGRADE and SELF_REVIEW with verified status and "Planned" for open items.
3. **Phase 2.2 (Implementation)** — Implement H2 (checklist wiring) and H3 (expert RAG errors) first (low effort). Then H1 (dry-run), then H4 (feedback loop).
4. **Phase 3 (Finalize)** — After each implementation, update the relevant doc section and mark the task complete in this plan.

---

## Verification Commands

```bash
# Confirm CLI exit codes
tapps-mcp init --check --host cursor
echo $?  # Expect 0 if config valid, 1 if not

# Confirm cache warming error surfacing
# (Run tapps_init in project without Context7 key; check result["cache_warming"]["error"] and result["errors"])

# Confirm checker install uses sys.executable
rg "sys.executable.*pip" src/tapps_mcp/pipeline/init.py

# Confirm CallTracker persistence
rg "set_persist_path" src/
# If no callers, H2 is needed

# Confirm MAX_BATCH_FILES
rg "MAX_BATCH_FILES" src/tapps_mcp/tools/batch_validator.py
```

---

## Checklist for Plan Closure

- [x] Phase 1 verification table completed and reviewed (2026-02-22)
- [x] INIT_AND_UPGRADE_FEATURE_LIST.md updated with status column and verification note (2026-02-22)
- [x] SELF_REVIEW_FINDINGS.md updated with re-verification section (2026-02-22)
- [x] H2 (Checklist persistence wiring) implemented
- [x] H3 (Expert RAG failed_domains → errors) implemented
- [x] H1 (Dry-run) implemented
- [x] H4 (Feedback → AdaptiveScoringEngine) implemented (metrics_dir param, _merge_feedback_outcomes)
- [ ] CHANGELOG updated for any code changes

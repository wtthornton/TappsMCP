# Epic 28: Quality Review Remediation

> Full-project review conducted 2026-02-28 using TappsMCP self-review with
> 5 parallel agent team (quality, security, architecture, testing, docs).

## Review Summary

| Dimension | Rating | Key Finding |
|-----------|--------|-------------|
| **Quality Scores** | C+ | 6 files fail gate (<70), worst = 46.05 |
| **Security** | B+ | No CVEs, 3 low-severity B110 patterns |
| **Architecture** | B | No circular deps, but singleton fragility + coupling |
| **Test Coverage** | B- | 4 server/pipeline modules have zero dedicated tests |
| **Documentation** | B | Module map drift in CLAUDE.md, some tools undocumented |

### Files Failing Quality Gate (score < 70)

| File | Score | Primary Issue |
|------|------:|---------------|
| `pipeline/platform_generators.py` | **46.05** | 2047 lines, MI=23, no tests |
| `server_pipeline_tools.py` | **59.73** | CC=42 (`tapps_validate_changed`), 12 lint, no tests |
| `server_scoring_tools.py` | **62.40** | CC=24 (`tapps_quick_check`), no tests |
| `adaptive/voting_engine.py` | **65.12** | No tests, nested loops |
| `scoring/scorer.py` | **65.62** | CC=15 (`_build_categories`), 822 lines |
| `server.py` | **66.62** | 1893 lines, MI=11, CC=16 (`tapps_lookup_docs`) |

### Files At Risk (70-78)

| File | Score | Primary Issue |
|------|------:|---------------|
| `pipeline/init.py` | **71.82** | CC=19, 767 lines, 2 security findings |
| `experts/engine.py` | **76.78** | CC=21 (`consult_expert`) |
| `tools/checklist.py` | **78.42** | CC=16, 2 lint issues |

---

## Epic 28a: Critical File Remediation (Bug Fixes)

**Priority**: P0 - These files fail the project's own quality gate.

### Story 28a.1: Split `platform_generators.py` (2047 lines -> ~4 files)
**Score**: 46.05 (FAIL) | **LOE**: ~1 day

**Problem**: Largest file in project at 2047 lines, MI=23 (very low maintainability),
deeply nested functions, no dedicated test file.

**Acceptance Criteria**:
- [ ] Split into: `platform_hooks.py`, `platform_agents.py`, `platform_skills.py`, `platform_rules.py`
- [ ] Each file < 600 lines
- [ ] Score > 70 on each split file
- [ ] Create `tests/unit/test_platform_generators.py` with coverage of public API
- [ ] Existing tests still pass

### Story 28a.2: Reduce `tapps_validate_changed` complexity (CC=42)
**Score**: 59.73 (FAIL) | **LOE**: ~0.5 day

**Problem**: `server_pipeline_tools.py::tapps_validate_changed` has cyclomatic complexity 42,
12 lint issues (3x `try-except-pass`, unsorted imports, long lines), 3 security warnings (B110).

**Acceptance Criteria**:
- [ ] Extract file discovery, per-file validation, and result aggregation into helpers
- [ ] CC < 15 for `tapps_validate_changed`
- [ ] Fix all 12 lint issues (replace `try-except-pass` with `contextlib.suppress` or logging)
- [ ] Fix 3 B110 security warnings
- [ ] Create `tests/unit/test_server_pipeline_tools.py`
- [ ] Score > 70

### Story 28a.3: Reduce `tapps_quick_check` complexity (CC=24)
**Score**: 62.40 (FAIL) | **LOE**: ~0.5 day

**Problem**: `server_scoring_tools.py::tapps_quick_check` has CC=24, very deep nesting (>6),
nested loops. No dedicated test file.

**Acceptance Criteria**:
- [ ] Extract scoring enrichment, security check, and gate evaluation into helpers
- [ ] CC < 12 for `tapps_quick_check`
- [ ] Create `tests/unit/test_server_scoring_tools.py`
- [ ] Score > 70

### Story 28a.4: Add tests for `voting_engine.py`
**Score**: 65.12 (FAIL) | **LOE**: ~0.5 day

**Problem**: `adaptive/voting_engine.py` has zero tests (test_coverage score = 0).

**Acceptance Criteria**:
- [ ] Create `tests/unit/test_voting_engine.py`
- [ ] Cover `VotingEngine.vote()`, weight distribution, edge cases
- [ ] Score > 70

### Story 28a.5: Reduce `scorer.py` complexity (CC=15, 822 lines)
**Score**: 65.62 (FAIL) | **LOE**: ~0.5 day

**Problem**: `_build_categories` has CC=15, file has 822 lines, very deep nesting (>6).

**Acceptance Criteria**:
- [ ] Extract category builders into per-category methods
- [ ] CC < 10 for `_build_categories`
- [ ] Score > 70

### Story 28a.6: Reduce `server.py` size and complexity
**Score**: 66.62 (FAIL) | **LOE**: ~1 day

**Problem**: 1893 lines, MI=11 (very low), `tapps_lookup_docs` CC=16. Still the largest
core module despite prior split into server_*_tools.py files.

**Acceptance Criteria**:
- [ ] Extract `tapps_lookup_docs` branches into helper functions
- [ ] Move resource/prompt registration to `server_resources.py`
- [ ] Target < 1200 lines for `server.py`
- [ ] CC < 10 for all functions
- [ ] Score > 70

---

## Epic 28b: Architecture Improvements (Enhancements)

**Priority**: P1 - Structural improvements for long-term maintainability.

### Story 28b.1: Decouple memory from knowledge/rag_safety
**LOE**: ~0.5 day

**Problem**: `memory/store.py` imports `knowledge/rag_safety.py` for content validation.
This couples episodic memory to the expert/knowledge subsystem unnecessarily.

**Acceptance Criteria**:
- [ ] Extract `check_content_safety()` to `security/content_safety.py`
- [ ] `memory/store.py` imports from `security/` instead of `knowledge/`
- [ ] Memory subsystem works without knowledge layer present
- [ ] All existing tests pass

### Story 28b.2: Create unified feature flags for optional dependencies
**LOE**: ~0.5 day

**Problem**: Scattered `try: import faiss except ImportError` patterns throughout
`experts/vector_rag.py`, `tools/radon.py`, `tools/parallel.py`.

**Acceptance Criteria**:
- [ ] Create `config/feature_flags.py` with `FeatureFlags` class
- [ ] Detect optional deps once at startup (faiss, sentence_transformers, numpy, radon)
- [ ] Replace scattered try/except imports with feature flag checks
- [ ] Add tests for feature flag detection

### Story 28b.3: Improve singleton cache test safety
**LOE**: ~0.5 day

**Problem**: 4 module-level singletons rely on autouse fixture discipline.
No enforcement mechanism if new caches are added or new tests skip the fixture.

**Acceptance Criteria**:
- [ ] Add CI check that all test modules use the conftest with cache reset
- [ ] Document cache reset pattern in CLAUDE.md (already partially done)
- [ ] Consider context-manager-based cache isolation for critical tests
- [ ] Verify conftest resets all 4 caches: settings, scorer, memory_store, tools

### Story 28b.4: Reduce `experts/engine.py` complexity (CC=21)
**LOE**: ~0.5 day

**Problem**: `consult_expert` has CC=21, function exceeds 100 lines.

**Acceptance Criteria**:
- [ ] Extract domain detection, knowledge retrieval, and response formatting into helpers
- [ ] CC < 12 for `consult_expert`
- [ ] Score > 80

### Story 28b.5: Reduce `pipeline/init.py` complexity (CC=19)
**LOE**: ~0.5 day

**Problem**: `_render_tech_stack_md` has CC=19, file has 767 lines, 2 security findings
(B404/B603 subprocess usage).

**Acceptance Criteria**:
- [ ] Extract tech stack section renderers into per-section helpers
- [ ] CC < 12 for `_render_tech_stack_md`
- [ ] Score > 78

---

## Epic 28c: Security Hardening (Enhancements)

**Priority**: P1 - Low severity but worth addressing.

### Story 28c.1: Replace try-except-pass with proper error handling
**LOE**: ~0.25 day

**Problem**: 3 instances of `try-except-pass` in `server_pipeline_tools.py` flagged as
B110 by bandit. Silent exception swallowing masks real errors.

**Files**: `server_pipeline_tools.py` lines 90, 194, 466

**Acceptance Criteria**:
- [ ] Replace with `contextlib.suppress()` for expected errors
- [ ] Add `structlog` logging for unexpected errors
- [ ] Zero B110 findings

### Story 28c.2: Audit subprocess usage in pipeline/init.py
**LOE**: ~0.25 day

**Problem**: B404/B603 findings for subprocess usage. While low severity (tool detection),
should verify no untrusted input reaches subprocess calls.

**Acceptance Criteria**:
- [ ] Verify all subprocess args are hardcoded tool paths (not user input)
- [ ] Add input validation if any dynamic paths are used
- [ ] Document subprocess usage rationale

---

## Epic 28d: Test Coverage Gaps (Enhancements)

**Priority**: P1 - Critical for regression prevention.

### Story 28d.1: Create `test_server_pipeline_tools.py`
**LOE**: ~1 day

**Problem**: `server_pipeline_tools.py` (796 lines, 6 MCP tools) has zero dedicated tests.

**Acceptance Criteria**:
- [ ] Test `tapps_validate_changed` with mock file changes
- [ ] Test `tapps_init` dry-run mode
- [ ] Test `tapps_upgrade` dry-run mode
- [ ] Test `tapps_doctor` diagnostics
- [ ] Test `tapps_set_engagement_level`
- [ ] Test `tapps_session_start` initialization
- [ ] Minimum 20 tests

### Story 28d.2: Create `test_server_scoring_tools.py`
**LOE**: ~0.5 day

**Problem**: `server_scoring_tools.py` (549 lines, 3 MCP tools) has zero dedicated tests.

**Acceptance Criteria**:
- [ ] Test `tapps_score_file` with mock files
- [ ] Test `tapps_quality_gate` pass/fail scenarios
- [ ] Test `tapps_quick_check` with fix mode
- [ ] Minimum 15 tests

### Story 28d.3: Create `test_platform_generators.py`
**LOE**: ~1 day

**Problem**: `platform_generators.py` (2047 lines) has zero dedicated tests.

**Acceptance Criteria**:
- [ ] Test hook generation for Claude Code
- [ ] Test agent/skill generation
- [ ] Test platform rules generation per engagement level
- [ ] Test CI workflow generation
- [ ] Minimum 20 tests

### Story 28d.4: Create `test_voting_engine.py`
**LOE**: ~0.5 day

**Problem**: `adaptive/voting_engine.py` has zero tests (covered in Story 28a.4).

*Same as Story 28a.4 — merged.*

---

## Epic 28e: Documentation Drift (Enhancements)

**Priority**: P2 - Accuracy and developer experience.

### Story 28e.1: Update CLAUDE.md module map
**LOE**: ~0.25 day

**Problem**: Module map in CLAUDE.md is missing several modules added in recent epics.

**Missing from module map**:
- `common/elicitation.py`, `common/utils.py`
- `experts/hot_rank.py`, `experts/rag_warming.py`, `experts/retrieval_eval.py`
- `knowledge/content_normalizer.py`
- `knowledge/providers/deepcon_provider.py`, `knowledge/providers/docfork_provider.py`
- `tools/dependency_scan_cache.py`
- `project/vulnerability_impact.py`
- `memory/decay.py`, `memory/reinforcement.py`, `memory/contradictions.py`,
  `memory/gc.py`, `memory/retrieval.py`, `memory/injection.py`,
  `memory/seeding.py`, `memory/io.py`
- `diagnostics.py`

**Acceptance Criteria**:
- [ ] Update module map to include all 162 modules
- [ ] Verify server module split description is accurate (6 files)
- [ ] Update memory subsystem description with Epic 24-25 modules

### Story 28e.2: Verify all MCP tools documented in README/AGENTS.md
**LOE**: ~0.25 day

**Problem**: Need to verify all 31 MCP tools appear in README.md tools reference
and AGENTS.md template.

**Acceptance Criteria**:
- [ ] Cross-reference `@mcp.tool()` decorators with README tools table
- [ ] Ensure AGENTS.md EXPECTED_TOOLS list matches actual tools
- [ ] Document any new tools from Epics 26-27

### Story 28e.3: Add `tapps_report` file exclusion for `.venv*` directories
**LOE**: ~0.25 day

**Problem**: `tapps_report` with `max_files=20` picked up `.venv-pyinstaller/` files,
inflating results with irrelevant scores (pywin32_postinstall.py at 56.14).

**Acceptance Criteria**:
- [ ] Add `.venv*`, `node_modules`, `dist`, `build` to default exclusions in report tool
- [ ] Verify `tapps_report` only scores project source files
- [ ] Same fix for `tapps_dead_code` project scope if affected

---

## Epic 28f: Lint and Code Style Cleanup (Enhancements)

**Priority**: P2 - Polish.

### Story 28f.1: Fix lint issues in `tools/checklist.py`
**LOE**: ~0.1 day

**Problem**: 2 E501 (line too long) at lines 78 and 138.

**Acceptance Criteria**:
- [ ] Fix both long lines
- [ ] Zero lint issues

### Story 28f.2: Fix lint issues in `server_pipeline_tools.py`
**LOE**: ~0.25 day

**Problem**: 12 lint issues including ANN401 (Any types), SIM105 (contextlib.suppress),
UP041 (aliased errors), I001 (import sorting), E501 (long lines).

*Overlap with Story 28a.2 and 28c.1 — partially merged.*

**Acceptance Criteria**:
- [ ] Fix all 12 lint issues
- [ ] Zero lint issues

### Story 28f.3: Fix ANN401 warnings in `server.py`
**LOE**: ~0.1 day

**Problem**: 4 ANN401 warnings for `Any` typed parameters.

**Acceptance Criteria**:
- [ ] Replace `Any` types with proper typed alternatives or narrow the types
- [ ] Zero ANN401 warnings

---

## Implementation Order

| Phase | Stories | LOE | Gate |
|-------|---------|-----|------|
| **Phase 1**: Critical fixes | 28a.1, 28a.2, 28a.3, 28a.6 | ~3 days | All 6 failing files > 70 |
| **Phase 2**: Test coverage | 28d.1, 28d.2, 28d.3, 28a.4 | ~3 days | 4 new test files, 70+ tests |
| **Phase 3**: Architecture | 28b.1, 28b.2, 28b.3, 28b.4, 28b.5 | ~2.5 days | All flagged files > 78 |
| **Phase 4**: Security + Lint | 28c.1, 28c.2, 28f.1-3 | ~1 day | Zero B110, zero lint |
| **Phase 5**: Docs + Polish | 28e.1, 28e.2, 28e.3 | ~0.75 day | Module map current |
| **Total** | 22 stories (4 merged) | ~10 days | All files > 70, zero lint |

---

## Metrics Targets

| Metric | Current | Target |
|--------|---------|--------|
| Files failing gate | 6 | 0 |
| Worst file score | 46.05 | > 70 |
| Average project score | ~79.89 | > 82 |
| Modules without tests | 4 | 0 |
| Total lint issues | 219* | < 20 |
| Security findings (B110) | 3 | 0 |

*\*219 includes .venv files; actual project lint issues ~18*
